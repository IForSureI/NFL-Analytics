"""02 Fourth-Down Bot: who leaves wins on the table?

Inspired by Brett Kollmann, "Are analytics ruining football?" (decision vs execution), and
Michael MacKelvie, "Passing is better...so, why run?" (coaches lag the math).
Steps:
  1. Train a win-probability model (2006-2023), test it on 2024-2025 against nflfastR's WP.
  2. Fit conversion, field-goal and punt models. Test each on held-out seasons: fit on 2016-2023, score on 2024 on.
  3. Score every 4th down 2018-present: WP if you go vs the best kick.
  4. Track how often coaches go when the math says go, and grade each team's 4th-down calls.
  5. Refit the three component models on the training seasons only and count how many recommendations change.
Run: python -m projects.fourth_down_bot
"""
from __future__ import annotations

import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot
from nflan.wp import WPModel, training_frame, add_features, brier, calibration_table, PBP_COLUMNS, FEATURES
from nflan.fourth import FourthDownBot, fg_range, convert_frame, fg_frame, punt_frame, grade_calls
from nflan.holdout import (split_seasons, brier_rows, log_loss_rows, bin_rate, paired_scores, calibration_by,
                           flip_share, headline_moves)
from nflan.stats import wilson

OUT = Path("reports/02-fourth-down-bot")
N_BOOT = 30  # game-bootstrap refits used for the uncertainty on every call
LAST = data.latest_season_available()
TRAIN_LAST = 2023  # component models: fit on 2016-2023, tested on 2024 on (the same cut as the win-probability test)
FIRST_MODERN = 2016
YTG_EDGES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 99]      # distance-only conversion table
FG_EDGES = [0, 29, 34, 39, 44, 49, 54, 99]                  # distance-only field-goal table
SPOT_EDGES = [34, 45, 55, 65, 75, 85, 99]                   # punt spot (yards from the end zone)
COLS = sorted(set(PBP_COLUMNS + ["play_id", "week", "yards_gained", "touchdown", "td_team", "field_goal_attempt",
                                 "field_goal_result", "kick_distance", "roof", "punt_attempt", "home_coach", "away_coach",
                                 "desc", "penalty", "qb_kneel", "qb_spike"]))


def kickoff_starts(pbp: pd.DataFrame) -> pd.Series:
    """Average yardline_100 of the receiving team's first snap after a kickoff, by season."""
    k = pbp[pbp["play_type"] == "kickoff"][["game_id", "play_id", "season", "posteam"]]
    s = pbp[pbp["play_type"].isin(["run", "pass"]) & pbp["down"].eq(1)][["game_id", "play_id", "posteam", "yardline_100"]]
    m = pd.merge_asof(k.sort_values("play_id"), s.sort_values("play_id").rename(columns={"posteam": "t2"}),
                      on="play_id", by="game_id", direction="forward", allow_exact_matches=False)
    m = m[m["t2"] == m["posteam"]]
    return m.groupby("season")["yardline_100"].mean()


class _FlatPunt:
    """A punt model that returns one opponent start for every spot: the league average."""
    def __init__(self, start): self.start = start
    def predict(self, X): return np.full(len(X), self.start)


def _r(v, k=4):
    """Round nested score dicts for findings.json."""
    if isinstance(v, dict):
        return {a: _r(b, k) for a, b in v.items()}
    if isinstance(v, (list, tuple)):
        return [_r(b, k) for b in v]
    return round(float(v), k)


def _binary_scores(p, y, games, base_rate, table_pred):
    """Held-out Brier and log loss for a probability model against the league-average rate and a distance-only table."""
    y = np.asarray(y, float); const = np.full(len(y), base_rate)
    out = {"n": int(len(y)), "games": int(pd.Series(np.asarray(games)).nunique()),
           "actual": round(float(y.mean()), 4), "predicted": round(float(np.mean(p)), 4), "league_avg_rate": round(float(base_rate), 4)}
    for name, rows in (("brier", brier_rows), ("log_loss", log_loss_rows)):
        out[name] = _r(paired_scores({"model": rows(p, y), "league_avg": rows(const, y), "distance_table": rows(table_pred, y)}, games), 5)
    return out


def holdout_figure(cal: pd.DataFrame, train: str, test: str, path):
    """Three panels from the saved calibration table: predicted against actual on the held-out seasons."""
    conv4, fgd, pc = (cal[cal.component == k].reset_index(drop=True) for k in ("convert_4th", "fg_by_distance", "punt_by_spot"))
    fig = plt.figure(figsize=(12.5, 5.6))
    gs = fig.add_gridspec(2, 3, height_ratios=[0.01, 1], hspace=0.16, wspace=0.3, left=0.06, right=0.985, top=0.86, bottom=0.17)
    head = fig.add_subplot(gs[0, :]); head.axis("off")
    axes = [fig.add_subplot(gs[1, i]) for i in range(3)]
    for ax_, name in zip(axes, ("Conversion, 4th downs", "Field goals", "Punts")):
        ax_.set_title(name, fontsize=10.5, fontweight="semibold", loc="left", pad=6)
    a = axes[0]
    a.plot([0, 1], [0, 1], color=plot.MUTED, ls="--", lw=1)
    lo_hi = np.array([wilson(r_.actual * r_.n, r_.n) for r_ in conv4.itertuples()])
    a.errorbar(conv4.pred, conv4.actual, yerr=[conv4.actual - lo_hi[:, 0], lo_hi[:, 1] - conv4.actual], fmt="o", color=plot.ACCENT, ecolor=plot.SOFT, lw=1, ms=5)
    nxt = conv4.actual.shift(-1)
    for r_, crowded in zip(conv4.itertuples(), (nxt - conv4.actual).abs() < 0.04):   # a neighbour at the same height: label on the other side
        a.annotate(f"{r_.n:,}", (r_.pred, r_.actual), textcoords="offset points", xytext=(-9, 3) if crowded else (9, -4),
                   ha="right" if crowded else "left", fontsize=8, color=plot.MUTED)
    a.set_xlim(0, 1); a.set_ylim(0, 1); a.set_xlabel("Predicted chance to convert"); a.set_ylabel("Share converted")
    b = axes[1]
    x = np.arange(len(fgd)); lo_hi = np.array([wilson(r_.actual * r_.n, r_.n) for r_ in fgd.itertuples()])
    b.plot(x, 100 * fgd.pred, color=plot.ACCENT2, lw=2, label="Predicted")
    b.errorbar(x, 100 * fgd.actual, yerr=[100 * (fgd.actual - lo_hi[:, 0]), 100 * (lo_hi[:, 1] - fgd.actual)], fmt="o", color=plot.ACCENT, ecolor=plot.SOFT, lw=1, ms=5, label="Made")
    for i, r_ in enumerate(fgd.itertuples()):
        b.annotate(f"{r_.n:,}", (i, 100 * lo_hi[i, 0]), textcoords="offset points", xytext=(0, -12), ha="center", fontsize=8, color=plot.MUTED)
    b.set_xticks(x); b.set_xticklabels(["<30", "30-34", "35-39", "40-44", "45-49", "50-54", "55+"][:len(fgd)], fontsize=9)
    b.set_xlim(-0.5, len(fgd) - 0.5); b.set_ylim(40, 103); b.set_xlabel("Field-goal distance (yards)"); b.set_ylabel("Made (%)"); b.legend(loc="lower left", fontsize=9)
    c_ = axes[2]
    x = np.arange(len(pc))
    c_.plot(x, 100 - pc.pred, color=plot.ACCENT2, lw=2, label="Predicted")
    c_.plot(x, 100 - pc.actual, "o", color=plot.ACCENT, ms=6, label="Actual")
    for i, r_ in enumerate(pc.itertuples()):
        c_.annotate(f"{r_.n:,}", (i, 100 - r_.actual), textcoords="offset points", xytext=(8, -11), ha="left", fontsize=8, color=plot.MUTED)
    c_.set_xticks(x); c_.set_xticklabels(["35-45", "46-55", "56-65", "66-75", "76-85", "86-99"][:len(pc)], fontsize=9)
    c_.set_xlim(-0.5, len(pc) - 0.3); c_.set_ylim(0, 55)
    c_.set_xlabel("Punt spot (yards from the end zone)"); c_.set_ylabel("Opponent's next snap (own yard line)"); c_.legend(loc="upper left", fontsize=9)
    with warnings.catch_warnings():   # the panel grid is placed by hand, so the automatic layout in finish() has nothing to do
        warnings.simplefilter("ignore", UserWarning)
        plot.finish(fig, head, "The component models on seasons they never saw",
                    f"Fit on {train}, scored on {test}. Small numbers are plays; bars are 95% intervals on the made and converted rates.", path)


def component_holdout(modern: pd.DataFrame, pbp_modern: pd.DataFrame, fourth_all: pd.DataFrame, out_dir: Path):
    """Fit the conversion, field-goal and punt models on 2016-TRAIN_LAST only and score them on the later seasons.

    Returns the findings and the training-only pieces (conversion model, extra-yards table, field-goal model,
    punt model, field-goal range), which the flip test below puts into a second bot."""
    tr, te = split_seasons(modern, TRAIN_LAST)
    tr_pbp = split_seasons(pbp_modern, TRAIN_LAST)[0]
    conv, gain = FourthDownBot.fit_convert(tr)
    fg = FourthDownBot.fit_fg(tr)
    punt = FourthDownBot.fit_punt(tr, tr_pbp)
    fg_max = fg_range(split_seasons(fourth_all, TRAIN_LAST)[0])
    h = {"train": f"{FIRST_MODERN}-{TRAIN_LAST}", "test": f"{TRAIN_LAST + 1}-{LAST}", "fg_max_dist_train": int(fg_max)}
    cal = []

    # conversion: every 3rd and 4th down, then 4th downs alone (the bot only ever asks about 4th downs)
    Xa, ya, da = convert_frame(tr); Xt, yt, dt = convert_frame(te)
    pt = conv.predict_proba(Xt)[:, 1]
    for key, mtr, mte in (("convert", np.ones(len(da), bool), np.ones(len(dt), bool)),
                          ("convert_4th", (da.down == 4).values, (dt.down == 4).values)):
        table = bin_rate(da.ydstogo[mtr], ya[mtr], YTG_EDGES)
        h[key] = _binary_scores(pt[mte], yt[mte], dt.game_id[mte], ya[mtr].mean(), table(dt.ydstogo[mte]))
        c = calibration_by(pt[mte], pt[mte], yt[mte], np.linspace(0, 1, 11)); c.insert(0, "component", key); cal.append(c)
    conv4 = calibration_by(pt[(dt.down == 4).values], pt[(dt.down == 4).values], yt[(dt.down == 4).values], np.linspace(0, 1, 11))
    # extra yards past the sticks on a conversion: training median (what the bot uses) against the test seasons
    st = dt[(yt == 1) & (dt.yards_gained >= dt.ydstogo)]
    st = st.assign(extra=(st.yards_gained - st.ydstogo).clip(0, 40), bucket=pd.cut(st.ydstogo, [0, 1, 2, 4, 7, 10, 99]))
    ex = gain.merge(st.groupby("bucket", observed=True).extra.agg(test_median="median", n_test="size").reset_index(), on="bucket", how="left")
    h["extra_yards"] = [[str(b), float(a), float(m), int(n)] for b, a, m, n in zip(ex.bucket, ex.extra, ex.test_median, ex.n_test)]

    # field goals: every attempt, then the attempts inside the range the bot offers
    Xk, mk, kk = fg_frame(tr); Xf, mf, kf = fg_frame(te)
    pf = fg.predict_proba(Xf)[:, 1]
    table = bin_rate(kk.kick_distance, mk, FG_EDGES)
    h["fg"] = _binary_scores(pf, mf, kf.game_id, mk.mean(), table(kf.kick_distance))
    inr = (kf.kick_distance <= fg_max).values
    h["fg_in_range"] = _binary_scores(pf[inr], mf[inr], kf.game_id[inr], mk[(kk.kick_distance <= fg_max).values].mean(),
                                      bin_rate(kk.kick_distance[(kk.kick_distance <= fg_max).values], mk[(kk.kick_distance <= fg_max).values], FG_EDGES)(kf.kick_distance[inr]))
    c = calibration_by(pf, pf, mf, np.linspace(0, 1, 11)); c.insert(0, "component", "fg"); cal.append(c)
    fgd = calibration_by(kf.kick_distance, pf, mf, FG_EDGES)
    c = fgd.copy(); c.insert(0, "component", "fg_by_distance"); cal.append(c)

    # punts: the opponent's next start. The bot uses the expected spot, so the score is squared error (RMSE) and the bias.
    ma = punt_frame(tr, tr_pbp); mt = punt_frame(te, split_seasons(pbp_modern, TRAIN_LAST)[1])
    pp = punt.predict(mt[["yardline_100"]])
    mean_start = float(ma.next_yl.mean())
    net = float((ma.next_yl - (100 - ma.yardline_100)).mean())            # average net yards of a training-season punt
    avg_net = np.minimum(100 - mt.yardline_100 + net, 80.0)                # that net from the spot, a touchback at the 20
    sq = lambda q: (np.asarray(q, float) - mt.next_yl.to_numpy(float)) ** 2
    h["punt"] = {"n": int(len(mt)), "games": int(mt.game_id.nunique()), "actual": round(float(mt.next_yl.mean()), 2),
                 "predicted": round(float(pp.mean()), 2), "avg_net_train": round(net, 2),
                 "rmse": _r(paired_scores({"model": sq(pp), "league_avg": sq(np.full(len(mt), mean_start)), "avg_net": sq(avg_net)}, mt.game_id, root=True), 3),
                 "bias": _r(paired_scores({"model": pp - mt.next_yl.to_numpy(float)}, mt.game_id)["model"], 3)}
    pc = calibration_by(mt.yardline_100, pp, mt.next_yl, SPOT_EDGES)
    c = pc.copy(); c.insert(0, "component", "punt_by_spot"); cal.append(c)
    pd.concat(cal, ignore_index=True).round(4).to_csv(out_dir / "holdout_calibration.csv", index=False)

    rows = []
    for key in ("convert", "convert_4th", "fg", "fg_in_range"):
        for metric in ("brier", "log_loss"):
            for who, v in h[key][metric].items():
                rows.append(dict(component=key, n=h[key]["n"], metric=metric, score_of=who, value=v[0], ci_low=v[1], ci_high=v[2]))
    for who, v in h["punt"]["rmse"].items():
        rows.append(dict(component="punt", n=h["punt"]["n"], metric="rmse_yards", score_of=who, value=v[0], ci_low=v[1], ci_high=v[2]))
    rows.append(dict(component="punt", n=h["punt"]["n"], metric="bias_yards", score_of="model", **dict(zip(("value", "ci_low", "ci_high"), h["punt"]["bias"]))))
    pd.DataFrame(rows).to_csv(out_dir / "holdout_scores.csv", index=False)

    holdout_figure(pd.read_csv(out_dir / "holdout_calibration.csv"), h["train"], h["test"], out_dir / "holdout_components.png")
    return h, (conv, gain, fg, punt, fg_max)


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pbp = data.load_pbp(range(2006, LAST + 1), columns=COLS)
    find = {}

    # 1. WP model: train 2006-2023, test 2024-2025
    tf = training_frame(pbp)
    train, test = tf[tf.season <= 2023], tf[tf.season.isin([2024, 2025])]
    m = WPModel.fit(train)
    p = m.predict(test)
    find["wp_test_plays"] = len(test)
    find["brier_ours"] = brier(p, test.y)
    ok = test.vegas_wp.notna()
    find["brier_nflfastR_vegas_wp"] = brier(test.vegas_wp[ok], test.y[ok])
    find["brier_ours_same_rows"] = brier(p[ok.values], test.y[ok])
    find["corr_with_nflfastR"] = float(np.corrcoef(p[ok.values], test.vegas_wp[ok])[0, 1])
    cal = calibration_table(p, test.y)
    cal.to_csv(OUT / "wp_calibration_2024_2025.csv", index=False)
    fig, ax = plt.subplots(figsize=(6.4, 6))
    ax.plot([0, 1], [0, 1], color=plot.MUTED, ls="--", lw=1)
    ax.scatter(cal.pred, cal.actual, s=np.sqrt(cal.n) / 2, color=plot.ACCENT)
    ax.set_xlabel("Predicted win probability"); ax.set_ylabel("Share of those teams that won")
    plot.finish(fig, ax, "The win-probability model is honest",
                f"Out of sample: {len(test):,} plays from 2024-25. Brier {find['brier_ours']:.3f} vs nflfastR {find['brier_nflfastR_vegas_wp']:.3f}",
                OUT / "wp_calibration.png")

    # production model on everything through the last full season
    full = WPModel.fit(tf[tf.season <= LAST - 1] if LAST >= 2026 else tf)

    # 2. components (2016+ so rules and kicking are modern)
    pbp_modern = pbp[pbp.season >= FIRST_MODERN]
    modern = add_features(pbp_modern)
    conv, gain = FourthDownBot.fit_convert(modern)
    fg = FourthDownBot.fit_fg(modern)
    punt = FourthDownBot.fit_punt(modern, pbp_modern)
    ko = kickoff_starts(pbp_modern)
    ko.to_csv(OUT / "kickoff_start_by_season.csv")
    fourth_all = modern[(modern.down == 4) & modern.play_type.isin(["run", "pass", "punt", "field_goal"]) & (modern.half_seconds_remaining > 120)]
    fg_max = fg_range(fourth_all)
    find["fg_max_dist"] = fg_max
    k_ = modern[(modern.field_goal_attempt == 1) & modern.kick_distance.notna()]
    find["fg_attempts_beyond_range"] = int((k_.kick_distance > fg_max).sum()); find["fg_attempts_total"] = int(len(k_))
    bot = FourthDownBot(full, conv, fg, punt, gain, float(ko.iloc[-1]), fg_max_dist=fg_max)
    # held-out test of the component models: fit on 2016-TRAIN_LAST, scored on the seasons after
    hold, (conv_t, gain_t, fg_t, punt_t, fg_max_t) = component_holdout(modern, pbp_modern, fourth_all, OUT)
    hold["test_last_week"] = int(pbp[(pbp.season == LAST) & (pbp.season_type == "REG")].week.max())
    with open(OUT / "model_summary.txt", "w") as f:
        f.write(f"Win-probability test (2024-2025): Brier {find['brier_ours']:.4f} vs nflfastR {find['brier_nflfastR_vegas_wp']:.4f}\n"
                f"Longest field goal the bot considers: {fg_max} yards\n"
                f"Component models fit on {hold['train']}, scored on {hold['test']}: see holdout_scores.csv\n\nConversion extra-yards table:\n{gain}\n\nKickoff start yardline_100 by season:\n{ko.round(1)}\n")

    # sanity states (also used by tests): 4th-and-1 at midfield, tied, first quarter, even teams
    sanity = pd.DataFrame([dict(score_differential=0, game_seconds_remaining=3000, half_seconds_remaining=1200,
                                yardline_100=50, down=4, ydstogo=1, posteam_timeouts_remaining=3,
                                defteam_timeouts_remaining=3, receive_2h_ko=1, posteam_spread=0, is_second_half=0,
                                roof_indoor=0, season=LAST),
                           dict(score_differential=0, game_seconds_remaining=3000, half_seconds_remaining=1200,
                                yardline_100=80, down=4, ydstogo=10, posteam_timeouts_remaining=3,
                                defteam_timeouts_remaining=3, receive_2h_ko=1, posteam_spread=0, is_second_half=0,
                                roof_indoor=0, season=LAST)])
    sv = bot.evaluate(sanity)
    find["sanity_4th1_midfield_go_boost"] = float(sv.go_boost[0])
    find["sanity_4th10_own20_go_boost"] = float(sv.go_boost[1])

    # 3. every 4th down since 2018
    df = add_features(pbp[(pbp.season >= 2018) & (pbp.down == 4) & (pbp.qtr <= 4)])
    df = df[df.play_type.isin(["run", "pass", "punt", "field_goal"]) & (df.qb_kneel != 1) & (df.qb_spike != 1)]
    df = df.dropna(subset=FEATURES)
    df["roof_indoor"] = df.roof.isin(["dome", "closed"]).astype(int)
    df["choice"] = np.select([df.play_type.isin(["run", "pass"]), df.play_type.eq("field_goal")], ["go", "fg"], "punt")
    parts = []
    for season, g in df.groupby("season"):
        bot.kickoff_start = float(ko.get(season, ko.iloc[-1]))
        bot.wp = full  # in-sample for 2018-2025, out of sample for the season in progress
        parts.append(pd.concat([g.reset_index(drop=True), bot.evaluate(g)], axis=1))
    ev = pd.concat(parts, ignore_index=True)
    # the same fourth downs in the test seasons, scored by two bots that never saw them:
    #   held-out components: conversion, field-goal and punt models (and the field-goal range) from 2016-TRAIN_LAST, production WP
    #   all held out: those components plus the win-probability model trained through 2023 (the model `m` tested above)
    test_idx = ev.index[ev.season > TRAIN_LAST]
    def score_test(b):
        outs = []
        for season, g in ev.loc[test_idx].groupby("season", sort=False):
            b.kickoff_start = float(ko.get(season, ko.iloc[-1]))
            o = b.evaluate(g); o.index = g.index; outs.append(o)
        return pd.concat(outs).loc[test_idx]
    # what the punt correction changed: the same bot with one opponent start for every punt spot (the league average,
    # which is what the punt model returned before its monotone constraint was fixed), against the corrected bot
    flat = FourthDownBot(full, conv, fg, _FlatPunt(float(punt_frame(modern, pbp_modern).next_yl.mean())), gain, float(ko.iloc[-1]), fg_max_dist=fg_max)
    fo = []
    for season, g in ev.groupby("season", sort=False):
        flat.kickoff_start = float(ko.get(season, ko.iloc[-1]))
        o = flat.evaluate(g); o.index = g.index; fo.append(o)
    fo = pd.concat(fo).loc[ev.index]
    ch = (fo.rec != ev.rec).values
    find["punt_fix"] = {"n": int(len(ev)), "share_recs_changed": round(float(ch.mean()), 4),
                        "go_to_punt": int(((fo.rec == "go") & (ev.rec == "punt")).sum()), "punt_to_go": int(((fo.rec == "punt") & (ev.rec == "go")).sum()),
                        "other": int(ch.sum() - ((fo.rec == "go") & (ev.rec == "punt")).sum() - ((fo.rec == "punt") & (ev.rec == "go")).sum()),
                        "go_share_before": round(float((fo.rec == "go").mean()), 4), "go_share_after": round(float((ev.rec == "go").mean()), 4),
                        "flat_start": round(float(flat.punt_net.start), 1)}
    held = score_test(FourthDownBot(full, conv_t, fg_t, punt_t, gain_t, float(ko.iloc[-1]), fg_max_dist=fg_max_t))
    held_all = score_test(FourthDownBot(m, conv_t, fg_t, punt_t, gain_t, float(ko.iloc[-1]), fg_max_dist=fg_max_t))
    ev["coach"] = np.where(ev.posteam == ev.home_team, ev.home_coach, ev.away_coach)

    # uncertainty: refit the win-probability, conversion, field-goal and punt models on resampled games and rescore every 4th down
    rng = np.random.default_rng(7)
    tr_full = tf[tf.season <= LAST - 1] if LAST >= 2026 else tf
    gid_wp = {g: i.values for g, i in tr_full.reset_index(drop=True).groupby("game_id").groups.items()}
    trw = tr_full.reset_index(drop=True)
    mod = modern.reset_index(drop=True); gid_c = {g: i.values for g, i in mod.groupby("game_id").groups.items()}
    keys_w, keys_c = list(gid_wp), list(gid_c)
    boots, boots_held, boots_flat = [], [], []
    for b_ in range(N_BOOT):
        w = WPModel.fit(trw.loc[np.concatenate([gid_wp[k] for k in rng.choice(keys_w, len(keys_w))])], seed=b_)
        mc_ = mod.loc[np.concatenate([gid_c[k] for k in rng.choice(keys_c, len(keys_c))])]
        cb, gb = FourthDownBot.fit_convert(mc_); fb = FourthDownBot.fit_fg(mc_); pb = FourthDownBot.fit_punt(mc_, pbp_modern)
        bb = FourthDownBot(w, cb, fb, pb, gb, float(ko.iloc[-1]), fg_max_dist=fg_max)
        outs = []
        for season, g in ev.groupby("season", sort=False):
            bb.kickoff_start = float(ko.get(season, ko.iloc[-1]))
            o = bb.evaluate(g); o.index = g.index; outs.append(o[["wp_go", "wp_fg", "wp_punt", "go_boost"]])
        boots.append(pd.concat(outs).loc[ev.index])
        # the same refit with the punt model as it was before the correction: one opponent start for every spot
        bf = FourthDownBot(w, cb, fb, _FlatPunt(float(punt_frame(mc_, pbp_modern).next_yl.mean())), gb, float(ko.iloc[-1]), fg_max_dist=fg_max)
        outs = []
        for season, g in ev.groupby("season", sort=False):
            bf.kickoff_start = float(ko.get(season, ko.iloc[-1]))
            o = bf.evaluate(g); o.index = g.index; outs.append(o[["wp_go", "wp_fg", "wp_punt", "go_boost"]])
        boots_flat.append(pd.concat(outs).loc[ev.index])
        # the same resampled games, training seasons only, for the held-out bot (no new random draws, so the
        # production refits above are unchanged by this test)
        mt_ = mc_[mc_.season <= TRAIN_LAST]
        ct, gt = FourthDownBot.fit_convert(mt_); ft = FourthDownBot.fit_fg(mt_); pt_ = FourthDownBot.fit_punt(mt_, pbp_modern)
        boots_held.append(score_test(FourthDownBot(w, ct, ft, pt_, gt, float(ko.iloc[-1]), fg_max_dist=fg_max_t))[["wp_go", "wp_fg", "wp_punt", "go_boost"]])
        print("boot", b_, flush=True)
    chosen_col = np.select([ev.choice.eq("go"), ev.choice.eq("fg")], [0, 1], 2)
    def gap_of(o):
        v = o[["wp_go", "wp_fg", "wp_punt"]].values
        ch = v[np.arange(len(v)), chosen_col]
        return 100 * (np.nanmax(v, axis=1) - ch)
    gaps = np.column_stack([gap_of(o) for o in boots]); boosts = np.column_stack([o.go_boost.values for o in boots])
    chosen = np.select([ev.choice.eq("go"), ev.choice.eq("fg")], [ev.wp_go, ev.wp_fg], ev.wp_punt)
    best = ev[["wp_go", "wp_fg", "wp_punt"]].max(axis=1)
    ev["gap"] = 100 * (best - chosen)
    ev["gap_se"] = np.nanstd(gaps, axis=1, ddof=1); ev["go_boost_se"] = np.nanstd(boosts, axis=1, ddof=1)
    ev["gap_lo"] = np.nanpercentile(gaps, 5, axis=1)
    # A call is charged only when it misses the best option by 1+ point AND the miss holds up when the models are refit:
    # the gap is at least 1 point in 95% of the refits' lower tail (5th percentile above zero).
    ev["clear_miss"] = (ev["gap"] >= 1.0) & (ev["gap_lo"] > 0)
    ev["wp_lost"] = np.where(ev["clear_miss"], ev["gap"], 0.0)
    ev["clear_go"] = (ev.go_boost >= 2) & (np.nanpercentile(boosts, 5, axis=1) > 0)
    ev["close"] = ev.score_differential.abs() <= 16
    lost_chk, go_chk = grade_calls(ev, boots, chosen_col)                # the shared rule must give the same grades
    assert np.allclose(lost_chk, ev.wp_lost.values) and (go_chk == ev.clear_go.values).all()
    lost_flat, go_flat = grade_calls(fo, boots_flat, chosen_col)         # the same fourth downs graded as before the punt correction
    ev.to_parquet(OUT / "fourth_downs_scored.parquet", index=False)
    find["n_boot"] = N_BOOT
    find["median_go_boost_se"] = round(float(ev.go_boost_se.median()), 2)
    find["share_1pt_gaps_that_hold_up"] = round(float(ev.clear_miss.sum() / max((ev.gap >= 1).sum(), 1)), 3)
    find["share_2pt_go_spots_that_hold_up"] = round(float(ev.clear_go.sum() / max((ev.go_boost >= 2).sum(), 1)), 3)

    # held-out bot, graded by the same rule: a miss is charged and a go spot counted only when it survives the refits
    tcol = chosen_col[test_idx]
    def gap_held(o):
        v = o[["wp_go", "wp_fg", "wp_punt"]].values
        return 100 * (np.nanmax(v, axis=1) - v[np.arange(len(v)), tcol])
    gaps_h = np.column_stack([gap_held(o) for o in boots_held]); boosts_h = np.column_stack([o.go_boost.values for o in boots_held])
    hv = pd.DataFrame({"rec": held.rec, "rec_all": held_all.rec, "go_boost": held.go_boost, "go_boost_all": held_all.go_boost,
                       "p_convert": held.p_convert, "p_make": held.p_make, "gap": gap_held(held)}, index=test_idx)
    hv["clear_miss"] = (hv.gap >= 1.0) & (np.nanpercentile(gaps_h, 5, axis=1) > 0)
    hv["wp_lost"] = np.where(hv.clear_miss, hv.gap, 0.0)
    hv["clear_go"] = (hv.go_boost >= 2) & (np.nanpercentile(boosts_h, 5, axis=1) > 0)
    tv = ev.loc[test_idx]
    tv[["game_id", "play_id", "season", "week", "posteam", "yardline_100", "ydstogo", "choice", "rec", "go_boost", "wp_lost", "clear_go"]].join(
        hv[["rec", "rec_all", "go_boost", "go_boost_all", "wp_lost", "clear_go"]].add_suffix("_held_out")).to_parquet(OUT / "holdout_fourth_downs.parquet", index=False)
    fl = {"n": int(len(tv)), "games": int(tv.game_id.nunique()),
          "components": _r(flip_share(tv.rec, hv.rec, tv.game_id), 4), "components_and_wp": _r(flip_share(tv.rec, hv.rec_all, tv.game_id), 4)}
    flipped = (tv.rec != hv.rec).values
    fl["by_season"] = {int(k): [round(float(v.mean()), 4), int(v.size)] for k, v in pd.Series(flipped, index=tv.season.values).groupby(level=0)}
    fl["n_flips"] = int(flipped.sum())
    fl["flips_go_vs_kick"] = int((flipped & ((tv.rec == "go").values != (hv.rec == "go").values)).sum())
    fl["flips_fg_vs_punt"] = fl["n_flips"] - fl["flips_go_vs_kick"]
    margin = tv.go_boost.abs().values                                   # the production bot's go-versus-kick margin
    fl["median_margin_flipped"] = round(float(np.median(margin[flipped])), 2) if flipped.any() else 0.0
    fl["median_margin_all"] = round(float(np.median(margin)), 2)
    fl["flips_margin_1plus"] = int((flipped & (margin >= 1)).sum()); fl["flips_margin_2plus"] = int((flipped & (margin >= 2)).sum())
    fl["calls_margin_2plus"] = int((margin >= 2).sum())
    counted = (tv.clear_go | tv.clear_miss).values                      # the calls the headline numbers are built from
    fl["counted_calls"] = int(counted.sum()); fl["counted_calls_flipped"] = int((flipped & counted).sum())
    fl["mean_abs_go_boost_shift"] = round(float((hv.go_boost - tv.go_boost).abs().mean()), 2)
    fl["mean_abs_p_convert_shift"] = round(float(100 * (hv.p_convert - tv.p_convert).abs().mean()), 2)
    in_rng = (tv.p_make > 0) & (hv.p_make > 0)
    fl["mean_abs_p_make_shift"] = round(float(100 * (hv.p_make - tv.p_make)[in_rng].abs().mean()), 2)
    hold["flips"] = fl

    # 4a. compliance trend: in clear go spots (go_boost >= 2 WP points), how often did coaches go?
    clear = ev[ev.clear_go & ev.close & (ev.game_seconds_remaining > 300)]
    tr = clear.groupby("season").agg(spots=("choice", "size"), n_went=("choice", lambda c: (c == "go").sum()), went=("choice", lambda c: (c == "go").mean()))
    ci = [wilson(k, n) for k, n in zip(tr.n_went, tr.spots)]
    tr["lo"], tr["hi"] = [c[0] for c in ci], [c[1] for c in ci]
    tr.to_csv(OUT / "go_rate_when_math_says_go.csv")
    find["go_rate_clear_spots"] = tr.went.round(3).to_dict()
    find["go_rate_ci"] = {int(k): [round(float(a_), 3), round(float(b_), 3)] for k, a_, b_ in zip(tr.index, tr.lo, tr.hi)}
    find["go_rate_spots"] = {int(k): int(v) for k, v in tr.spots.items()}
    bt = ev[go_flat & ev.close.values & (ev.game_seconds_remaining > 300).values].groupby("season").choice.agg(spots="size", went=lambda c: (c == "go").mean())
    find["punt_fix"]["go_rate_before"] = {int(k): [round(float(v), 3), int(n)] for k, v, n in zip(bt.index, bt.went, bt.spots)}
    # the trend should not depend on the 2-point line: go rate first vs last full season at several thresholds
    sens = {}
    for th in [0.5, 1, 2, 3, 5]:
        c_ = ev[(ev.go_boost >= th) & ev.close & (ev.game_seconds_remaining > 300)].groupby("season").choice.apply(lambda c: (c == "go").mean())
        sens[str(th)] = [round(float(c_.iloc[0]), 3), round(float(c_.iloc[-2]), 3)]
    find["go_rate_first_vs_last_full_by_threshold"] = sens
    fig, ax = plt.subplots()
    ax.plot(tr.index, 100 * tr.went, marker="o", lw=2.4, color=plot.ACCENT)
    for x, y, n in zip(tr.index, 100 * tr.went, tr.spots):
        ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
    ax.set_ylim(0, 100); ax.set_ylabel("Went for it (%)"); ax.set_xticks(tr.index)
    plot.finish(fig, ax, "Coaches go for it more, but still not as often as the math says",
                "4th downs where going adds 2+ WP points, score within 16, outside the last 5 minutes. 2026 is partial.",
                OUT / "go_rate_trend.png")

    # 4b. team scorecard, latest two seasons: WP points lost per game on 4th-down calls
    rows = []
    for season in sorted(ev.season.unique())[-2:]:
        e = ev[(ev.season == season) & ev.close & (ev.season_type == "REG")]
        gpt = pbp[(pbp.season == season) & (pbp.season_type == "REG")].groupby("posteam").game_id.nunique()
        t = e.groupby("posteam").agg(fourth_downs=("choice", "size"), wp_lost=("wp_lost", "sum"),
                                     clear_go_spots=("clear_go", "sum"),
                                     went_in_clear=("choice", lambda c: 0)).reset_index()
        cg = e[e.clear_go].groupby("posteam").choice.apply(lambda c: (c == "go").sum())
        t["went_in_clear"] = t.posteam.map(cg).fillna(0).astype(int)
        t["games"] = t.posteam.map(gpt)
        t["wp_lost_per_game"] = t.wp_lost / t.games
        t["season"] = season
        rows.append(t.sort_values("wp_lost_per_game"))
    sc = pd.concat(rows)
    # team interval: resample the team's games
    reg = ev[ev.close & (ev.season_type == "REG")]
    pg = reg.groupby(["season", "posteam", "game_id"]).wp_lost.sum().reset_index()
    allg = pbp[pbp.season_type == "REG"][["season", "posteam", "game_id"]].dropna().drop_duplicates()
    pg = allg.merge(pg, on=["season", "posteam", "game_id"], how="left").fillna({"wp_lost": 0.0})
    pg = pg[pg.season >= 2018]
    lo_hi = {}
    for (se, tm), g in pg[pg.season.isin(sc.season.unique())].groupby(["season", "posteam"]):
        v = g.wp_lost.values; bs_ = rng.choice(v, (2000, len(v))).mean(axis=1)
        lo_hi[(se, tm)] = np.percentile(bs_, [5, 95])
    sc["ci_low"] = [lo_hi[(a_, b_)][0] for a_, b_ in zip(sc.season, sc.posteam)]
    sc["ci_high"] = [lo_hi[(a_, b_)][1] for a_, b_ in zip(sc.season, sc.posteam)]
    sc.to_csv(OUT / "team_scorecard.csv", index=False)
    # does the team number repeat? odd weeks vs even weeks within a season, and one season to the next
    wk = pbp[["game_id", "week"]].drop_duplicates("game_id")
    pgw = pg.merge(wk, on="game_id")
    full_seasons = pgw[pgw.season < LAST]
    half = full_seasons.assign(odd=full_seasons.week % 2).groupby(["season", "posteam", "odd"]).wp_lost.mean().unstack("odd").dropna()
    find["scorecard_split_half_r"] = round(float(half[0].corr(half[1])), 2); find["scorecard_team_seasons"] = int(len(half))
    yr = full_seasons.groupby(["season", "posteam"]).wp_lost.mean().reset_index()
    yy = yr.merge(yr.assign(season=yr.season - 1), on=["season", "posteam"], suffixes=("", "_next"))
    find["scorecard_yoy_r"] = round(float(yy.wp_lost.corr(yy.wp_lost_next)), 2)
    # the same two repeatability checks on the card as it was graded before the punt correction
    pgf = ev.assign(wp_lost=lost_flat)[ev.close & (ev.season_type == "REG")].groupby(["season", "posteam", "game_id"]).wp_lost.sum().reset_index()
    pgf = allg.merge(pgf, on=["season", "posteam", "game_id"], how="left").fillna({"wp_lost": 0.0})
    pgf = pgf[(pgf.season >= 2018)].merge(wk, on="game_id")
    curf = pgf[pgf.season == LAST].groupby("posteam").wp_lost.mean().sort_values(ascending=False)
    pgf = pgf[pgf.season < LAST]
    hf = pgf.assign(odd=pgf.week % 2).groupby(["season", "posteam", "odd"]).wp_lost.mean().unstack("odd").dropna()
    yf = pgf.groupby(["season", "posteam"]).wp_lost.mean().reset_index()
    yf = yf.merge(yf.assign(season=yf.season - 1), on=["season", "posteam"], suffixes=("", "_next"))
    find["punt_fix"].update({"split_half_r_before": round(float(hf[0].corr(hf[1])), 2), "yoy_r_before": round(float(yf.wp_lost.corr(yf.wp_lost_next)), 2),
                             "most_costly_before": curf.index[:3].tolist()})
    cur = sc[sc.season == sc.season.max()].sort_values("wp_lost_per_game", ascending=False)
    find["scorecard_season"] = int(sc.season.max())
    find["most_costly"] = cur.head(3)[["posteam", "wp_lost_per_game", "ci_low", "ci_high"]].round(2).values.tolist()
    find["least_costly"] = cur.tail(3)[["posteam", "wp_lost_per_game", "ci_low", "ci_high"]].round(2).values.tolist()
    med = cur.wp_lost_per_game.median()
    find["scorecard_teams_clear_of_median"] = int(((cur.ci_low > med) | (cur.ci_high < med)).sum())
    find["scorecard_games"] = [int(cur.games.min()), int(cur.games.max())]
    # do the headline numbers move when the components come from the training seasons only?
    hc = hv[hv.clear_go & tv.close & (tv.game_seconds_remaining > 300)].join(tv[["season", "choice"]]).groupby("season").choice.agg(
        spots="size", went=lambda c: (c == "go").mean())
    rates = {int(se): (float(tr.went[se]), float(tr.lo[se]), float(tr.hi[se]), float(hc.went[se])) for se in hc.index}
    e = tv.assign(held=hv.wp_lost)[tv.close & (tv.season_type == "REG")]
    ht = e.groupby(["season", "posteam"])[["wp_lost", "held"]].sum().reset_index()
    card = sc.merge(ht[["season", "posteam", "held"]], on=["season", "posteam"], how="left").fillna({"held": 0.0})
    card["held_out"] = card.held / card.games
    card_cur = card[card.season == sc.season.max()].sort_values("wp_lost_per_game", ascending=False)
    card_cur[["season", "posteam", "games", "wp_lost_per_game", "ci_low", "ci_high", "held_out"]].round(3).to_csv(OUT / "holdout_team_card.csv", index=False)
    why = headline_moves(rates, card_cur)
    big = card_cur.assign(d=(card_cur.held_out - card_cur.wp_lost_per_game)).sort_values("d", key=np.abs, ascending=False).iloc[0]
    lg = card[card.season > TRAIN_LAST].groupby("season").apply(lambda g: [round(float(g.wp_lost.sum() / g.games.sum()), 3), round(float(g.held.sum() / g.games.sum()), 3)])
    hold["headline"] = {
        "go_rate": {int(se): [round(v[0], 3), round(v[3], 3), int(tr.spots[se]), int(hc.spots[se])] for se, v in rates.items()},
        "card_season": int(sc.season.max()),
        "card_r": round(float(np.corrcoef(card_cur.wp_lost_per_game, card_cur.held_out)[0, 1]), 3),
        "card_biggest_change": [str(big.posteam), round(float(big.wp_lost_per_game), 2), round(float(big.held_out), 2)],
        "card_mean_abs_change": round(float((card_cur.held_out - card_cur.wp_lost_per_game).abs().mean()), 3),
        "card_top3_held_out": card_cur.sort_values("held_out", ascending=False).posteam.head(3).tolist(),
        "wp_lost_per_team_game": {int(k): v for k, v in lg.items()},
        "moves": bool(why), "reasons": why}
    find["holdout"] = hold

    fig, ax = plt.subplots(figsize=(8, 8.5))
    c = cur.iloc[::-1]
    ax.barh(c.posteam, c.wp_lost_per_game, color=plot.ACCENT2)
    ax.errorbar(c.wp_lost_per_game, c.posteam, xerr=[c.wp_lost_per_game - c.ci_low, c.ci_high - c.wp_lost_per_game], fmt="none", ecolor=plot.INK, lw=0.9)
    ax.set_xlabel("Win-probability points lost per game on 4th-down decisions"); ax.grid(axis="y", visible=False)
    plot.finish(fig, ax, f"{int(sc.season.max())} fourth-down calls: a description, not a ranking",
                f"WP points lost per game on clear misses, games within 16, with 90% intervals. Split-half r = {find['scorecard_split_half_r']:.2f}",
                OUT / "team_scorecard.png")

    # 4c. costliest single decisions this season
    worst = ev[ev.season == ev.season.max()].sort_values("wp_lost", ascending=False).head(10)
    worst[["week", "posteam", "defteam", "qtr", "game_seconds_remaining", "score_differential", "yardline_100",
           "ydstogo", "choice", "rec", "go_boost", "wp_lost", "desc"]].to_csv(OUT / "costliest_calls_current_season.csv", index=False)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k, v in find.items():
        print(k, v)


if __name__ == "__main__":
    main()
