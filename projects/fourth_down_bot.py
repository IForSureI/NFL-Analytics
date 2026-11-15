"""02 Fourth-Down Bot: who leaves wins on the table?

Inspired by Brett Kollmann, "Are analytics ruining football?" (decision vs execution), and
Michael MacKelvie, "Passing is better...so, why run?" (coaches lag the math).
Steps:
  1. Train a win-probability model (2006-2023), test it on 2024-2025 against nflfastR's WP.
  2. Fit conversion, field-goal and punt models.
  3. Score every 4th down 2018-present: WP if you go vs the best kick.
  4. Track how often coaches go when the math says go, and grade each team's 4th-down calls.
Run: python -m projects.fourth_down_bot
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot
from nflan.wp import WPModel, training_frame, add_features, brier, calibration_table, PBP_COLUMNS, FEATURES
from nflan.fourth import FourthDownBot, fg_range
from nflan.stats import wilson

OUT = Path("reports/02-fourth-down-bot")
N_BOOT = 30  # game-bootstrap refits used for the uncertainty on every call
LAST = data.latest_season_available()
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
    modern = add_features(pbp[pbp.season >= 2016])
    conv, gain = FourthDownBot.fit_convert(modern)
    fg = FourthDownBot.fit_fg(modern)
    punt = FourthDownBot.fit_punt(modern, pbp[pbp.season >= 2016])
    ko = kickoff_starts(pbp[pbp.season >= 2016])
    ko.to_csv(OUT / "kickoff_start_by_season.csv")
    fourth_all = modern[(modern.down == 4) & modern.play_type.isin(["run", "pass", "punt", "field_goal"]) & (modern.half_seconds_remaining > 120)]
    fg_max = fg_range(fourth_all)
    find["fg_max_dist"] = fg_max
    k_ = modern[(modern.field_goal_attempt == 1) & modern.kick_distance.notna()]
    find["fg_attempts_beyond_range"] = int((k_.kick_distance > fg_max).sum()); find["fg_attempts_total"] = int(len(k_))
    bot = FourthDownBot(full, conv, fg, punt, gain, float(ko.iloc[-1]), fg_max_dist=fg_max)
    # in-sample calibration of the component models (no held-out seasons for these; stated as such in the README)
    d34 = modern[modern.down.isin([3, 4]) & modern.play_type.isin(["run", "pass"])].dropna(subset=["ydstogo", "yardline_100", "yards_gained", "posteam_spread"])
    yc = ((d34.yards_gained >= d34.ydstogo) | ((d34.touchdown == 1) & (d34.td_team == d34.posteam)))
    pc_ = conv.predict_proba(d34[["ydstogo", "yardline_100"]].assign(is4=(d34.down == 4).astype(int), posteam_spread=d34.posteam_spread)[["ydstogo", "yardline_100", "is4", "posteam_spread"]])[:, 1]
    find["convert_in_sample"] = [round(float(pc_.mean()), 3), round(float(yc.mean()), 3)]
    with open(OUT / "model_summary.txt", "w") as f:
        f.write(f"Win-probability test (2024-2025): Brier {find['brier_ours']:.4f} vs nflfastR {find['brier_nflfastR_vegas_wp']:.4f}\n"
                f"Longest field goal the bot considers: {fg_max} yards\n\nConversion extra-yards table:\n{gain}\n\nKickoff start yardline_100 by season:\n{ko.round(1)}\n")

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
    ev["coach"] = np.where(ev.posteam == ev.home_team, ev.home_coach, ev.away_coach)

    # uncertainty: refit the win-probability, conversion and field-goal models on resampled games and rescore every 4th down
    rng = np.random.default_rng(7)
    tr_full = tf[tf.season <= LAST - 1] if LAST >= 2026 else tf
    gid_wp = {g: i.values for g, i in tr_full.reset_index(drop=True).groupby("game_id").groups.items()}
    trw = tr_full.reset_index(drop=True)
    mod = modern.reset_index(drop=True); gid_c = {g: i.values for g, i in mod.groupby("game_id").groups.items()}
    keys_w, keys_c = list(gid_wp), list(gid_c)
    boots = []
    for b_ in range(N_BOOT):
        w = WPModel.fit(trw.loc[np.concatenate([gid_wp[k] for k in rng.choice(keys_w, len(keys_w))])], seed=b_)
        mc_ = mod.loc[np.concatenate([gid_c[k] for k in rng.choice(keys_c, len(keys_c))])]
        cb, gb = FourthDownBot.fit_convert(mc_); fb = FourthDownBot.fit_fg(mc_)
        bb = FourthDownBot(w, cb, fb, punt, gb, float(ko.iloc[-1]), fg_max_dist=fg_max)
        outs = []
        for season, g in ev.groupby("season", sort=False):
            bb.kickoff_start = float(ko.get(season, ko.iloc[-1]))
            o = bb.evaluate(g); o.index = g.index; outs.append(o[["wp_go", "wp_fg", "wp_punt", "go_boost"]])
        boots.append(pd.concat(outs).loc[ev.index])
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
    ev.to_parquet(OUT / "fourth_downs_scored.parquet", index=False)
    find["n_boot"] = N_BOOT
    find["median_go_boost_se"] = round(float(ev.go_boost_se.median()), 2)
    find["share_1pt_gaps_that_hold_up"] = round(float(ev.clear_miss.sum() / max((ev.gap >= 1).sum(), 1)), 3)
    find["share_2pt_go_spots_that_hold_up"] = round(float(ev.clear_go.sum() / max((ev.go_boost >= 2).sum(), 1)), 3)

    # 4a. compliance trend: in clear go spots (go_boost >= 2 WP points), how often did coaches go?
    clear = ev[ev.clear_go & ev.close & (ev.game_seconds_remaining > 300)]
    tr = clear.groupby("season").agg(spots=("choice", "size"), n_went=("choice", lambda c: (c == "go").sum()), went=("choice", lambda c: (c == "go").mean()))
    ci = [wilson(k, n) for k, n in zip(tr.n_went, tr.spots)]
    tr["lo"], tr["hi"] = [c[0] for c in ci], [c[1] for c in ci]
    tr.to_csv(OUT / "go_rate_when_math_says_go.csv")
    find["go_rate_clear_spots"] = tr.went.round(3).to_dict()
    find["go_rate_ci"] = {int(k): [round(float(a_), 3), round(float(b_), 3)] for k, a_, b_ in zip(tr.index, tr.lo, tr.hi)}
    find["go_rate_spots"] = {int(k): int(v) for k, v in tr.spots.items()}
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
    cur = sc[sc.season == sc.season.max()].sort_values("wp_lost_per_game", ascending=False)
    find["scorecard_season"] = int(sc.season.max())
    find["most_costly"] = cur.head(3)[["posteam", "wp_lost_per_game", "ci_low", "ci_high"]].round(2).values.tolist()
    find["least_costly"] = cur.tail(3)[["posteam", "wp_lost_per_game", "ci_low", "ci_high"]].round(2).values.tolist()
    med = cur.wp_lost_per_game.median()
    find["scorecard_teams_clear_of_median"] = int(((cur.ci_low > med) | (cur.ci_high < med)).sum())
    find["scorecard_games"] = [int(cur.games.min()), int(cur.games.max())]
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
