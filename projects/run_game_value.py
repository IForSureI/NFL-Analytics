"""09 Run Game Value: what is a running back actually worth?

The question: how much of a back's production is his, and how much is his blocking and the box he
runs into, and do contracts pay for the part that is his? NFL Next Gen Stats splits every carry into
the yards a typical back would gain on it (expected yards, from tracking: blockers, defenders, box
count, space at the handoff) and the yards over that expectation (RYOE). If the back's part is RYOE,
it should repeat, follow him to a new team, predict next year, and be what contracts pay for.

Tests:
  1. Stability: year to year, raw yards per carry vs its two parts (expected yards per carry and
     RYOE per carry), plus success rate, EPA per carry, efficiency and the share of 8+ man boxes.
  2. Portability: does RYOE follow a back who changes teams (changers vs stayers)? Expected yards
     per carry should not, if it belongs to the line and the scheme.
  3. Prediction: what this season predicts next season's rushing EPA per carry and rushing yards.
  4. Price: in veteran RB contracts (Over The Cap, signed 2019-2026), what is paid for expected
     yards, RYOE, touchdowns, carries and receiving yards; the price per FUTURE rushing yard bought
     through each part (mirrors studies 07-08).
  5. The 2027 free-agent backs ranked by RYOE, with value flags.
Data: NFL Next Gen Stats rushing (nflverse release nextgen_stats/ngs_rushing.parquet, week 0 = the
season rows for qualified rushers, RYOE from 2018), nflverse play-by-play 2018-2026, Over The Cap
contracts, snap counts and players (nflverse).
Run: python -m projects.run_game_value
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import statsmodels.api as sm

from nflan import data, plot
from projects.box_score_tax import ols, CAP_2026

OUT = Path("reports/09-run-game-value")
SRC = "Data: NFL Next Gen Stats, nflverse play-by-play and Over The Cap via nflverse. Chart: Dylan Fanelli"
SRC_PLAY = "Data: NFL Next Gen Stats and nflverse play-by-play via nflverse. Chart: Dylan Fanelli"
FIRST = 2018  # NGS expected rushing yards start in 2018
B = 1000      # bootstrap draws (players resampled)

# News check of the free-agent list (report standard rule 6), checked 2026-11-12. Over The Cap via nflverse can
# lag; these notes override it. "drop" removes a player who is not a 2027 free agent.
NEWS = {
    "Christian McCaffrey": ("drop", "not a 2027 free agent: his 2024 two-year extension runs through 2027; Over The Cap's end year misses "
                                    "the fifth-year option year on his rookie deal"),
    "Kimani Vidal": ("note", "restricted, not unrestricted: signed a 2026 exclusive-rights tender, so the Chargers can tender him again"),
    "Zach Charbonnet": ("note", "torn ACL in the January 2026 playoffs (surgery in February); back from PUP in late October; rookie deal ends after 2026"),
    "Tony Pollard": ("note", "final year of his 2024 Titans deal; Tennessee kept him through the November 10, 2026 trade deadline"),
    "Jordan Mason": ("note", "final year of the two-year deal he signed when traded to Minnesota in 2025"),
    "Aaron Jones": ("note", "agreed to a reworked, lower-paid 2026 deal with Minnesota in March 2026"),
    "Alvin Kamara": ("note", "reworked deal for 2026 in the last year of his contract; 32 at the start of the 2027 season"),
    "Chase Brown": ("note", "rookie deal ends after 2026; extension talks reported, none signed"),
    "Brian Robinson Jr.": ("note", "one-year deal with Atlanta for 2026; placed on injured reserve (hamstring) on November 7, 2026"),
    "Rachaad White": ("note", "one-year deal with Washington for 2026"),
    "Emanuel Wilson": ("note", "one-year deal with Seattle for 2026"),
    "Devin Singletary": ("note", "kept by the Giants on a restructured deal for 2026"),
    "Kendre Miller": ("note", "released by New Orleans on November 7, 2026, a year after an October 2025 ACL tear; a free agent now unless claimed"),
    "Sean Tucker": ("note", "signed a one-year deal with Tampa Bay in August 2026"),
    "Samaje Perine": ("note", "final year of a two-year Cincinnati deal, 2025-26"),
    "Zonovan Knight": ("note", "one-year deal with Arizona for 2026"),
}


def load_ngs_rushing(refresh: bool = False) -> pd.DataFrame:
    return data._release("nextgen_stats", "ngs_rushing.parquet", refresh)


def ngs_seasons() -> pd.DataFrame:
    n = load_ngs_rushing()
    n = n[(n.week == 0) & (n.season_type == "REG") & (n.season >= FIRST)].copy()
    n = n.rename(columns={"player_gsis_id": "gsis_id", "player_display_name": "player", "team_abbr": "tm",
                          "percent_attempts_gte_eight_defenders": "box8"})
    n["ypc"] = n.rush_yards / n.rush_attempts
    # RYOE per carry over ALL carries, so YPC = expected YPC + RYOE per carry exactly. NGS's own per-attempt
    # figure divides by tracked attempts only; NGS expected yards also miss a few untracked carries, so the
    # expected part is defined as total yards minus RYOE.
    n["ryoe_pc"] = n.rush_yards_over_expected / n.rush_attempts
    n["xypc"] = n.ypc - n.ryoe_pc
    n["ryoe_yds"] = n.rush_yards_over_expected
    n["x_yds"] = n.rush_yards - n.ryoe_yds
    n["box8"] = n.box8 / 100 if n.box8.max() > 1 else n.box8
    return n


def pbp_backs(last: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = ["season", "season_type", "rush_attempt", "qb_scramble", "two_point_attempt", "rusher_player_id", "epa", "success",
            "rushing_yards", "rush_touchdown", "complete_pass", "receiver_player_id", "receiving_yards", "posteam"]
    p = data.load_pbp(range(FIRST, last + 1), columns=cols)
    p = p[p.season_type == "REG"]
    r = p[(p.rush_attempt == 1) & (p.qb_scramble == 0) & (p.two_point_attempt == 0) & p.rusher_player_id.notna() & p.epa.notna()]
    rush = r.groupby(["season", "rusher_player_id"]).agg(car=("epa", "size"), epa=("epa", "mean"), sr=("success", "mean"),
                                                        yds=("rushing_yards", "sum"), td=("rush_touchdown", "sum"),
                                                        team_now=("posteam", "last")).reset_index()
    main_tm = r.groupby(["season", "rusher_player_id", "posteam"]).size().rename("n").reset_index().sort_values("n")
    main_tm = main_tm.drop_duplicates(["season", "rusher_player_id"], keep="last")[["season", "rusher_player_id", "posteam"]]
    rush = rush.merge(main_tm.rename(columns={"posteam": "team_main"}), on=["season", "rusher_player_id"], how="left")
    rush = rush.rename(columns={"rusher_player_id": "gsis_id"})
    q = p[(p.complete_pass == 1) & p.receiver_player_id.notna()]
    rec = q.groupby(["season", "receiver_player_id"]).receiving_yards.sum().reset_index()
    rec = rec.rename(columns={"receiver_player_id": "gsis_id", "receiving_yards": "rec_yds"})
    return rush, rec


def nxt(df, cols, key="gsis_id"):
    a = df[[key, "season"] + cols]
    return a.merge(a.assign(season=a.season - 1), on=[key, "season"], suffixes=("", "_next"))


def boot_r(df, x, y, groups, rng, b=B):
    """Player-resampled 95% interval for corr(x, y)."""
    g = pd.factorize(df[groups])[0]
    idx = [np.where(g == k)[0] for k in range(g.max() + 1)]
    xv, yv = df[x].values, df[y].values
    out = []
    for _ in range(b):
        i = np.concatenate([idx[k] for k in rng.integers(0, len(idx), len(idx))])
        out.append(np.corrcoef(xv[i], yv[i])[0, 1])
    return [round(float(v), 3) for v in np.percentile(out, [2.5, 97.5])]


BIRTH = None


def main():
    global BIRTH
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pl_ = data.load_players()[["gsis_id", "birth_date"]].dropna().drop_duplicates("gsis_id")
    BIRTH = pl_.assign(birth=pd.to_datetime(pl_.birth_date, errors="coerce"))[["gsis_id", "birth"]]
    rng = np.random.default_rng(9)
    n = ngs_seasons()
    last = int(n.season.max())
    rush, rec = pbp_backs(last)
    n = n.merge(rush[["season", "gsis_id", "epa", "sr", "td", "car", "team_main"]], on=["season", "gsis_id"], how="left")
    # NGS leaves team_abbr empty for some season rows (2021); fill from the team he carried for most that season
    tm_missing = int(n.tm.isna().sum())
    n["tm"] = n.tm.fillna(n.team_main)
    n = n.merge(rec, on=["season", "gsis_id"], how="left").fillna({"rec_yds": 0})
    full = n[n.season < last].copy()
    find = {"seasons": f"{FIRST}-{last - 1}", "current_season": last, "qualified_seasons": len(full),
            "qualified_players": int(full.gsis_id.nunique()), "cap_2026_musd": CAP_2026,
            "ngs_untracked_yards_mean": round(float((full.rush_yards - full.expected_rush_yards - full.ryoe_yds).mean()), 1),
            "ngs_team_filled_from_pbp": tm_missing, "through_week": int(data.load_pbp(last, columns=["week", "season_type"]).query("season_type == 'REG'").week.max())}

    # ---------------- 1. stability ----------------
    stats = {"ypc": "Yards per carry", "xypc": "Expected yards per carry\n(blocking, box, space)", "ryoe_pc": "Rush yards over\nexpected per carry",
             "sr": "Success rate", "epa": "EPA per carry", "box8": "Share of carries vs 8+ box", "efficiency": "NGS efficiency"}
    pairs = nxt(full, list(stats) + ["tm", "rush_attempts", "ryoe_yds", "x_yds"])
    find["pairs"] = len(pairs); find["pair_players"] = int(pairs.gsis_id.nunique())
    find["yoy_r"] = {k: round(float(pairs[k].corr(pairs[k + "_next"])), 3) for k in stats}
    find["yoy_r_ci"] = {k: boot_r(pairs, k, k + "_next", "gsis_id", rng) for k in stats}
    # which part of YPC carries into next year's YPC: cov(YPC_next, part) / cov(YPC_next, YPC); the two shares sum to 1
    cv = lambda a: float(np.cov(pairs[a], pairs.ypc_next)[0, 1])
    find["share_of_repeatable_ypc_expected"] = round(cv("xypc") / cv("ypc"), 3)
    find["share_of_repeatable_ypc_ryoe"] = round(cv("ryoe_pc") / cv("ypc"), 3)
    find["r_next_ypc_from"] = {k: round(float(pairs[k].corr(pairs.ypc_next)), 3) for k in ["ypc", "xypc", "ryoe_pc"]}
    find["var_share_ypc"] = {"expected": round(float(full.xypc.var() / full.ypc.var()), 3), "ryoe": round(float(full.ryoe_pc.var() / full.ypc.var()), 3),
                             "cov2": round(float(2 * np.cov(full.xypc, full.ryoe_pc)[0, 1] / full.ypc.var()), 3)}
    find["league_ypc"] = round(float(full.rush_yards.sum() / full.rush_attempts.sum()), 2)
    find["r_box8_xypc"] = round(float(full.box8.corr(full.xypc)), 3)
    # bigger-sample check on raw YPC: every back with 100+ carries in back-to-back seasons (play-by-play, no NGS needed)
    big = rush[(rush.car >= 100) & (rush.season < last)].assign(ypc=lambda d: d.yds / d.car)
    bp = nxt(big, ["ypc"])
    find["pbp_100car_pairs"] = len(bp); find["pbp_100car_yoy_r_ypc"] = round(float(bp.ypc.corr(bp.ypc_next)), 3)
    # sample checks on the stability gap: 150+ carries both seasons, and pairs weighted by carries
    p150 = pairs[(pairs.rush_attempts >= 150) & (pairs.rush_attempts_next >= 150)]
    find["yoy_r_150car"] = {"n": len(p150), **{k: round(float(p150[k].corr(p150[k + "_next"])), 3) for k in ["ypc", "xypc", "ryoe_pc"]}}
    def wcorr(a, b, w):
        m_a, m_b = np.average(a, weights=w), np.average(b, weights=w)
        return float(np.average((a - m_a) * (b - m_b), weights=w) / np.sqrt(np.average((a - m_a) ** 2, weights=w) * np.average((b - m_b) ** 2, weights=w)))
    wts = np.minimum(pairs.rush_attempts, pairs.rush_attempts_next)
    find["yoy_r_carry_weighted"] = {k: round(wcorr(pairs[k], pairs[k + "_next"], wts), 3) for k in ["ypc", "xypc", "ryoe_pc"]}
    # bootstrap of the gap itself: expected-YPC r minus RYOE r
    g_ = pd.factorize(pairs.gsis_id)[0]; idx_ = [np.where(g_ == k)[0] for k in range(g_.max() + 1)]
    gaps = []
    for _ in range(B):
        i = np.concatenate([idx_[k] for k in rng.integers(0, len(idx_), len(idx_))]); d_ = pairs.iloc[i]
        gaps.append(d_.xypc.corr(d_.xypc_next) - d_.ryoe_pc.corr(d_.ryoe_pc_next))
    find["stability_gap_ci"] = [round(float(v), 3) for v in np.percentile(gaps, [2.5, 97.5])]
    find["stability_gap_share_positive"] = round(float(np.mean(np.array(gaps) > 0)), 3)

    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    order = sorted(stats, key=lambda k: find["yoy_r"][k])
    vals = [find["yoy_r"][k] for k in order]
    lo = [find["yoy_r"][k] - find["yoy_r_ci"][k][0] for k in order]; hi = [find["yoy_r_ci"][k][1] - find["yoy_r"][k] for k in order]
    cols = [plot.ACCENT2 if k == "ryoe_pc" else (plot.ACCENT if k == "xypc" else plot.SOFT) for k in order]
    ax.barh([stats[k] for k in order], vals, color=cols, xerr=[lo, hi], error_kw=dict(ecolor=plot.MUTED, lw=1, capsize=3))
    for i, (v, k) in enumerate(zip(vals, order)):
        ax.text(find["yoy_r_ci"][k][1] + 0.012, i, f"{v:.2f}", va="center", fontsize=9.5, fontweight="bold")
    ax.set_xlabel("Year-to-year correlation (r), 95% interval resampling players"); ax.grid(axis="y", visible=False); ax.set_xlim(-0.05, 0.7)
    plot.finish(fig, ax, "The blocking part of yards per carry repeats more than the back's part",
                f"Qualified rushers (NGS), back-to-back regular seasons {FIRST}-{last - 1} ({len(pairs)} pairs, {pairs.gsis_id.nunique()} backs)",
                OUT / "stability.png", source=SRC_PLAY)

    # ---------------- 2. portability: team changers vs stayers ----------------
    pairs["changed"] = pairs.tm != pairs.tm_next
    port = {}
    for k in ["ryoe_pc", "xypc", "ypc", "box8"]:
        row = {}
        for lab, d_ in [("stayers", pairs[~pairs.changed]), ("changers", pairs[pairs.changed])]:
            row[lab] = round(float(d_[k].corr(d_[k + "_next"])), 3)
            row[lab + "_ci"] = boot_r(d_, k, k + "_next", "gsis_id", rng)
        port[k] = row
    find["portability"] = port
    gd = pd.factorize(pairs.gsis_id)[0]; idd = [np.where(gd == k)[0] for k in range(gd.max() + 1)]
    diffs = {"ryoe_pc": [], "xypc": []}
    for _ in range(B):
        d_ = pairs.iloc[np.concatenate([idd[k] for k in rng.integers(0, len(idd), len(idd))])]
        for k in diffs:
            a1, a0 = d_[d_.changed], d_[~d_.changed]
            diffs[k].append(a1[k].corr(a1[k + "_next"]) - a0[k].corr(a0[k + "_next"]))
    find["changer_minus_stayer_ci"] = {k: [round(float(v), 3) for v in np.nanpercentile(diffs[k], [2.5, 97.5])] for k in diffs}
    find["changers_n"] = int(pairs.changed.sum()); find["stayers_n"] = int((~pairs.changed).sum())
    # mean level change for changers: does a back's expected YPC move with the new line?
    ch = pairs[pairs.changed]
    find["changers_mean_abs_change"] = {k: round(float((ch[k + "_next"] - ch[k]).abs().mean()), 3) for k in ["xypc", "ryoe_pc"]}
    st = pairs[~pairs.changed]
    find["stayers_mean_abs_change"] = {k: round(float((st[k + "_next"] - st[k]).abs().mean()), 3) for k in ["xypc", "ryoe_pc"]}
    pairs.round(3).to_csv(OUT / "back_to_back_seasons.csv", index=False)

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    labs = {"ryoe_pc": "RYOE per carry\n(the back's part)", "xypc": "Expected yards per carry\n(blocking, box, space)", "ypc": "Raw yards\nper carry"}
    x = np.arange(3); w = 0.36
    for j, (lab, col) in enumerate([("stayers", plot.ACCENT), ("changers", plot.ACCENT2)]):
        v = [port[k][lab] for k in labs]
        e = [[port[k][lab] - port[k][lab + "_ci"][0] for k in labs], [port[k][lab + "_ci"][1] - port[k][lab] for k in labs]]
        nn = find["stayers_n"] if lab == "stayers" else find["changers_n"]
        ax.bar(x + (j - 0.5) * w, v, w, color=col, yerr=e, error_kw=dict(ecolor=plot.MUTED, lw=1, capsize=3),
               label=f"Same team both years ({nn} pairs)" if lab == "stayers" else f"Changed teams ({nn} pairs)")
        for xi, vi, top_ in zip(x, v, [port[k][lab + "_ci"][1] for k in labs]):
            ax.text(xi + (j - 0.5) * w, top_ + 0.02, f"{vi:.2f}", ha="center", fontsize=9.5, fontweight="bold")
    ax.axhline(0, color=plot.SOFT, lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(list(labs.values())); ax.grid(axis="x", visible=False)
    ax.set_ylabel("Year-to-year correlation (r)"); ax.set_ylim(-0.2, 0.85); ax.legend(loc="upper right", fontsize=9)
    plot.finish(fig, ax, "Changing teams: neither part of yards per carry clearly travels better",
                f"Back-to-back qualified seasons {FIRST}-{last - 1}; bars show 95% intervals resampling players", OUT / "team_changers.png", source=SRC_PLAY)

    # ---------------- 3. prediction ----------------
    # next season from play-by-play for every back (not only NGS-qualified), so a back who fades out counts
    nx = rush[["season", "gsis_id", "car", "epa", "yds"]].rename(columns={"car": "car_next", "epa": "epa_next", "yds": "yds_next"})
    nx["season"] = nx.season - 1
    pe = full[full.season < last - 1].merge(nx, on=["season", "gsis_id"], how="left")
    pe["yds_next"] = pe.yds_next.fillna(0); pe["car_next"] = pe.car_next.fillna(0)
    pe_e = pe[pe.car_next >= 100].copy()
    preds = {"epa": "EPA per carry", "ypc": "Yards per carry", "xypc": "Expected YPC", "ryoe_pc": "RYOE per carry", "sr": "Success rate", "box8": "8+ box share"}
    find["predict_epa_n"] = len(pe_e)
    find["r_next_epa"] = {k: round(float(pe_e[k].corr(pe_e.epa_next)), 3) for k in preds}
    find["r_next_epa_ci"] = {k: boot_r(pe_e, k, "epa_next", "gsis_id", rng) for k in preds}
    me = ols(pe_e.epa_next, pe_e[["epa", "xypc", "ryoe_pc", "box8"]], groups=pe_e.gsis_id)
    find["epa_model_r2"] = round(float(me.rsquared), 3)
    find["epa_model_coef"] = {k: round(float(me.params[k]), 4) for k in ["epa", "xypc", "ryoe_pc", "box8"]}
    find["epa_model_p"] = {k: round(float(me.pvalues[k]), 3) for k in ["epa", "xypc", "ryoe_pc", "box8"]}
    find["league_epa_per_carry_next"] = round(float(pe_e.epa_next.mean()), 3)

    comp = ["x_yds", "ryoe_yds", "td", "rec_yds"]
    find["predict_yards_n"] = len(pe); find["predict_yards_zero_next"] = int((pe.car_next == 0).sum())
    py = ols(pe.yds_next, pe[comp], groups=pe.gsis_id)
    find["predict_next_yards_per"] = {c: round(float(py.params[c]), 3) for c in comp}
    find["predict_next_yards_ci"] = {c: [round(float(v), 3) for v in py.conf_int().loc[c]] for c in comp}
    find["predict_yards_r2"] = round(float(py.rsquared), 3)
    # expected yards are mostly volume (r with carries below); a signing team sets the volume, so the per-carry test is the clean one:
    # next season's YPC (backs with 50+ carries, weighted by carries) on this season's expected YPC and RYOE per carry
    find["r_xyds_with_carries"] = round(float(pe.x_yds.corr(pe.rush_attempts)), 3)
    find["r_ryoe_yds_with_carries"] = round(float(pe.ryoe_yds.corr(pe.rush_attempts)), 3)
    pv = pe[pe.car_next >= 50].copy(); pv["ypc_next"] = pv.yds_next / pv.car_next
    Xv = sm.add_constant(pv[["xypc", "ryoe_pc"]])
    pyv = sm.WLS(pv.ypc_next, Xv, weights=pv.car_next).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(pv.gsis_id)[0]})
    find["predict_ypc_n"] = len(pv)
    find["predict_next_ypc_per"] = {c: round(float(pyv.params[c]), 3) for c in ["xypc", "ryoe_pc"]}
    find["predict_next_ypc_ci"] = {c: [round(float(v), 3) for v in pyv.conf_int().loc[c]] for c in ["xypc", "ryoe_pc"]}
    find["predict_next_ypc_diff_p"] = round(float(pyv.t_test("xypc - ryoe_pc = 0").pvalue), 3)
    # yards model plus platform carries (separates the volume inside expected yards)
    pyc = ols(pe.yds_next, pe[comp].assign(carries=pe.rush_attempts), groups=pe.gsis_id)
    find["predict_plus_carries_per"] = {c: round(float(pyc.params[c]), 3) for c in ["x_yds", "ryoe_yds", "carries"]}
    find["predict_plus_carries_ci"] = {c: [round(float(v), 3) for v in pyc.conf_int().loc[c]] for c in ["x_yds", "ryoe_yds"]}
    # age: backs fade, so add age and age squared to the prediction
    pa = pe.merge(BIRTH, on="gsis_id", how="left")
    pa["age"] = (pd.to_datetime(pa.season.astype(int).astype(str) + "-09-01") - pa.birth).dt.days / 365.25
    pa = pa[pa.age.notna()]
    pya = ols(pa.yds_next, pa[comp].assign(age=pa.age, age2=pa.age ** 2), groups=pa.gsis_id)
    find["predict_with_age_per"] = {c: round(float(pya.params[c]), 3) for c in ["x_yds", "ryoe_yds"]}
    find["predict_with_age_ratio"] = round(float(pya.params["ryoe_yds"] / pya.params["x_yds"]), 2)
    # what predicts next-year TDs: TDs or yards?
    ptd = nxt(rush[(rush.car >= 100) & (rush.season < last)], ["td", "yds", "car"])
    find["yoy_r_rush_td"] = round(float(ptd.td.corr(ptd.td_next)), 3)
    find["r_next_td_from_yds"] = round(float(ptd.yds.corr(ptd.td_next)), 3)
    find["yoy_r_rush_yards"] = round(float(ptd.yds.corr(ptd.yds_next)), 3)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    order = sorted(preds, key=lambda k: find["r_next_epa"][k])
    v = [find["r_next_epa"][k] for k in order]
    e = [[find["r_next_epa"][k] - find["r_next_epa_ci"][k][0] for k in order], [find["r_next_epa_ci"][k][1] - find["r_next_epa"][k] for k in order]]
    ax.barh([preds[k] for k in order], v, color=[plot.ACCENT2 if k == "ryoe_pc" else plot.ACCENT for k in order], xerr=e,
            error_kw=dict(ecolor=plot.MUTED, lw=1, capsize=3))
    ax.axvline(0, color=plot.SOFT, lw=0.8)
    ax.set_xlabel("Correlation with next season's rushing EPA per carry (95% interval)"); ax.grid(axis="y", visible=False); ax.set_xlim(-0.45, 0.6)
    plot.finish(fig, ax, "No rushing stat predicts next season's rushing EPA well",
                f"Qualified rushers {FIRST}-{last - 2} with 100+ carries the next season ({len(pe_e)} back-seasons)", OUT / "predict_epa.png", source=SRC_PLAY)

    # ---------------- 4. price ----------------
    c = data.load_contracts()
    c = c[(c.position == "RB") & c.gsis_id.notna() & c.apy_cap_pct.notna()]
    rookie = c.draft_year.notna() & (c.year_signed == c.draft_year)
    c = c[~rookie & c.year_signed.between(2019, 2026) & (c.apy_cap_pct >= 0.004)].drop_duplicates(["gsis_id", "year_signed", "apy"])
    # a tag or tender and a long-term deal in the same year are one decision: keep the longer (then richer) deal
    c = c.sort_values(["years", "apy"], ascending=False, kind="mergesort").drop_duplicates(["gsis_id", "year_signed"])
    find["vet_rb_deals_all"] = len(c)
    plat = n[["gsis_id", "season", "player", "tm", "rush_attempts", "rush_yards", "expected_rush_yards", "x_yds", "ryoe_yds", "ryoe_pc", "xypc", "td", "rec_yds", "box8"]].rename(
        columns={"season": "platform", "player": "ngs_name"})
    mk = c.merge(plat, on="gsis_id")
    mk = mk[mk.platform == mk.year_signed - 1].copy()
    mk["apy_pct"] = 100 * mk.apy_cap_pct
    mk = mk.merge(BIRTH, on="gsis_id", how="left")
    mk["age"] = (pd.to_datetime(mk.year_signed.astype(int).astype(str) + "-09-01") - mk.birth.fillna(pd.to_datetime(mk.date_of_birth, errors="coerce"))).dt.days / 365.25
    find["market_median_age"] = round(float(mk.age.median()), 1)
    find["market_contracts"] = len(mk); find["market_players"] = int(mk.gsis_id.nunique())
    usd = lambda b, per=100: round(float(b) * per / 100 * CAP_2026, 3)
    pm = ols(mk.apy_pct, mk[comp], groups=mk.gsis_id)
    find["musd_per_100_yards"] = {cc: usd(pm.params[cc]) for cc in ["x_yds", "ryoe_yds", "rec_yds"]}
    find["musd_per_100_yards_ci"] = {cc: [usd(v) for v in pm.conf_int().loc[cc]] for cc in ["x_yds", "ryoe_yds", "rec_yds"]}
    find["musd_per_td"] = usd(pm.params["td"], 1); find["musd_per_td_ci"] = [round(usd(v, 1), 2) for v in pm.conf_int().loc["td"]]
    find["market_r2"] = round(float(pm.rsquared), 3)
    find["price_ratio_ryoe_to_expected_yard"] = round(float(pm.params["ryoe_yds"] / pm.params["x_yds"]), 2)
    find["price_diff_p"] = round(float(pm.t_test("ryoe_yds - x_yds = 0").pvalue), 3)
    # per-carry pay model: what +1 expected YPC and +1 RYOE per carry add to APY, holding carries, TDs and receiving fixed
    pc_ = ols(mk.apy_pct, mk[["rush_attempts", "xypc", "ryoe_pc", "td", "rec_yds"]], groups=mk.gsis_id)
    find["musd_per_ypc_part"] = {c: usd(pc_.params[c], 1) for c in ["xypc", "ryoe_pc"]}
    find["musd_per_ypc_part_ci"] = {c: [usd(v, 1) for v in pc_.conf_int().loc[c]] for c in ["xypc", "ryoe_pc"]}
    find["price_per_carry_diff_p"] = round(float(pc_.t_test("ryoe_pc - xypc = 0").pvalue), 3)
    find["predict_ratio_ryoe_to_expected_yard"] = round(float(py.params["ryoe_yds"] / py.params["x_yds"]), 2)
    fut = {cc: round(find["musd_per_100_yards"][cc] / max(find["predict_next_yards_per"][cc], 1e-6), 2) for cc in ["x_yds", "ryoe_yds"]}
    find["musd_per_100_future_yards"] = fut
    # the box-score view: carries, yards, TDs, receiving (what a GM sees on the back of the card)
    bs = ols(mk.apy_pct, mk[["rush_attempts", "rush_yards", "td", "rec_yds"]], groups=mk.gsis_id)
    find["boxscore_model"] = {"musd_per_100_rush_yards": usd(bs.params["rush_yards"]), "musd_per_100_carries": usd(bs.params["rush_attempts"]),
                              "musd_per_td": usd(bs.params["td"], 1), "r2": round(float(bs.rsquared), 3),
                              "carries_ci": [usd(v) for v in bs.conf_int().loc["rush_attempts"]]}
    # does RYOE per carry add pay beyond the box score?
    bs2 = ols(mk.apy_pct, mk[["rush_attempts", "rush_yards", "td", "rec_yds", "ryoe_pc"]], groups=mk.gsis_id)
    find["musd_per_ryoe_pc_beyond_boxscore"] = usd(bs2.params["ryoe_pc"], 1)
    find["musd_per_ryoe_pc_beyond_boxscore_ci"] = [usd(v, 1) for v in bs2.conf_int().loc["ryoe_pc"]]
    find["r2_gain_from_ryoe"] = round(float(bs2.rsquared - bs.rsquared), 3)

    # bootstrap: price per future yard via RYOE vs via expected yards (resample players in both samples)
    Xm = np.column_stack([np.ones(len(mk)), mk[comp].values]); ym = mk.apy_pct.values
    Xp = np.column_stack([np.ones(len(pe)), pe[comp].values]); yp = pe.yds_next.values
    gm = pd.factorize(mk.gsis_id)[0]; gp = pd.factorize(pe.gsis_id)[0]
    im = [np.where(gm == k)[0] for k in range(gm.max() + 1)]; ip = [np.where(gp == k)[0] for k in range(gp.max() + 1)]
    ratios = []
    for _ in range(B):
        i = np.concatenate([im[k] for k in rng.integers(0, len(im), len(im))])
        j = np.concatenate([ip[k] for k in rng.integers(0, len(ip), len(ip))])
        bm = np.linalg.lstsq(Xm[i], ym[i], rcond=None)[0]; bp_ = np.linalg.lstsq(Xp[j], yp[j], rcond=None)[0]
        if bp_[1] > 0 and bp_[2] > 0:
            ratios.append((bm[2] / bp_[2]) / (bm[1] / bp_[1]))  # cost per future yard: RYOE route / expected route
    find["future_yard_cost_ratio_ryoe_vs_expected"] = round(float((fut["ryoe_yds"]) / fut["x_yds"]), 2)
    find["future_yard_cost_ratio_ci90"] = [round(float(v), 2) for v in np.percentile(ratios, [5, 95])]
    find["share_boot_ryoe_route_dearer"] = round(float(np.mean(np.array(ratios) > 1)), 3)

    rob = []
    variants = {"base": mk, "base + age": mk, "deals >= 1% of cap": mk[mk.apy_cap_pct >= 0.01], "multi-year deals": mk[mk.years >= 2],
                "signed 2023-2026": mk[mk.year_signed >= 2023], "signed 2019-2022": mk[mk.year_signed <= 2022],
                "no receiving-yards control": mk, "plus platform carries": mk}
    for name, d_ in variants.items():
        X = d_[comp]
        if name == "base + age":
            X = X.assign(age=d_.age, age2=d_.age ** 2)
        if name == "no receiving-yards control":
            X = d_[["x_yds", "ryoe_yds", "td"]]
        if name == "plus platform carries":
            X = X.assign(carries=d_.rush_attempts)
        ok = X.notna().all(axis=1)
        m_ = ols(d_.apy_pct[ok], X[ok], groups=d_.gsis_id[ok])
        row = {"sample": name, "contracts": int(ok.sum())}
        for cc in ["x_yds", "ryoe_yds"]:
            row[f"{cc}_musd_per_100"] = usd(m_.params[cc]); lo_, hi_ = m_.conf_int().loc[cc]
            row[f"{cc}_ci_low"] = usd(lo_); row[f"{cc}_ci_high"] = usd(hi_)
        row["ryoe_to_expected_price_ratio"] = round(float(m_.params["ryoe_yds"] / m_.params["x_yds"]), 2)
        row["p_difference"] = round(float(m_.t_test("ryoe_yds - x_yds = 0").pvalue), 3)
        rob.append(row)
    # NGS's own expected-yards column in place of yards minus RYOE (a few untracked carries differ)
    alt = ols(mk.apy_pct, mk[["expected_rush_yards", "ryoe_yds", "td", "rec_yds"]], groups=mk.gsis_id)
    rob.append({"sample": "NGS expected-yards column", "contracts": len(mk),
                "x_yds_musd_per_100": usd(alt.params["expected_rush_yards"]), "x_yds_ci_low": usd(alt.conf_int().loc["expected_rush_yards"][0]),
                "x_yds_ci_high": usd(alt.conf_int().loc["expected_rush_yards"][1]), "ryoe_yds_musd_per_100": usd(alt.params["ryoe_yds"]),
                "ryoe_yds_ci_low": usd(alt.conf_int().loc["ryoe_yds"][0]), "ryoe_yds_ci_high": usd(alt.conf_int().loc["ryoe_yds"][1]),
                "ryoe_to_expected_price_ratio": round(float(alt.params["ryoe_yds"] / alt.params["expected_rush_yards"]), 2),
                "p_difference": round(float(alt.t_test("ryoe_yds - expected_rush_yards = 0").pvalue), 3)})
    rob = pd.DataFrame(rob); rob.to_csv(OUT / "robustness_price_per_100_yards.csv", index=False)
    find["robustness"] = rob.to_dict("records")
    find["robust_ratio_min"] = float(rob.ryoe_to_expected_price_ratio.min()); find["robust_ratio_max"] = float(rob.ryoe_to_expected_price_ratio.max())
    find["robust_ryoe_ci_above_zero"] = int((rob.ryoe_yds_ci_low > 0).sum()); find["robust_n"] = len(rob)
    find["robust_diff_significant"] = int((rob.p_difference < 0.05).sum())
    find["robust_p"] = {r_["sample"]: r_["p_difference"] for r_ in rob.to_dict("records")}
    find["robust_ratio"] = {r_["sample"]: r_["ryoe_to_expected_price_ratio"] for r_ in rob.to_dict("records")}
    mk[["player", "year_signed", "team", "apy", "apy_cap_pct", "years", "platform", "tm", "rush_attempts", "rush_yards", "x_yds", "ryoe_yds", "ryoe_pc",
        "td", "rec_yds", "age"]].sort_values(["year_signed", "apy"], ascending=[True, False]).round(3).to_csv(OUT / "rb_contracts_with_platform.csv", index=False)

    fig, axs = plt.subplots(1, 2, figsize=(10.5, 5.2))
    lab = ["+1 expected\nyard per carry", "+1 yard over\nexpected per carry"]
    x = np.arange(2); cols2 = [plot.ACCENT, plot.ACCENT2]
    def bars(ax, vals, cis, fmt):
        ax.bar(x, vals, 0.55, color=cols2, yerr=[[v - c[0] for v, c in zip(vals, cis)], [c[1] - v for v, c in zip(vals, cis)]],
               error_kw=dict(ecolor=plot.MUTED, lw=1, capsize=4))
        for xi, v in zip(x, vals):
            ax.text(xi + 0.3, v, fmt(v), ha="left", va="center", fontsize=11, fontweight="bold")
        ax.axhline(0, color=plot.INK, lw=0.8)
        ax.set_xticks(x); ax.set_xticklabels(lab); ax.grid(axis="x", visible=False); ax.set_xlim(-0.5, 1.75)
    bars(axs[0], [find["musd_per_ypc_part"][k] for k in ["xypc", "ryoe_pc"]], [find["musd_per_ypc_part_ci"][k] for k in ["xypc", "ryoe_pc"]],
         lambda v: f"${v:.2f}M")
    axs[0].set_ylabel("Paid: $M a year (2026 cap dollars)")
    bars(axs[1], [find["predict_next_ypc_per"][k] for k in ["xypc", "ryoe_pc"]], [find["predict_next_ypc_ci"][k] for k in ["xypc", "ryoe_pc"]],
         lambda v: f"{v:+.2f}")
    axs[1].set_ylabel("Predicts: next season's yards per carry")
    big_ax = fig.add_subplot(111, frameon=False)
    big_ax.tick_params(labelcolor="none", which="both", top=False, bottom=False, left=False, right=False); big_ax.grid(False)
    plot.finish(fig, big_ax, "Teams pay a little more for the back's part; both parts carry over about equally",
                f"Left: {len(mk)} veteran RB deals 2019-26, holding carries, TDs and receiving. Right: {len(pv)} back-seasons {FIRST}-{last - 2}. 95% intervals",
                OUT / "rb_price.png", source=SRC)

    # ---------------- 5. 2027 free agents ----------------
    allc = data.load_contracts()
    allc = allc[(allc.position == "RB") & allc.gsis_id.notna()].assign(act=lambda d: d.is_active.fillna(False).astype(int))
    allc = allc.sort_values(["year_signed", "act"], kind="mergesort")  # the active deal wins a same-year tie (a tender vs the signed deal)
    latest = allc.groupby("gsis_id").tail(1).copy()
    latest["end_year"] = latest.contract_history.map(data.contract_end_year)
    option = (latest.draft_round == 1) & (latest.year_signed == latest.draft_year)
    fa = latest[(latest.end_year == last) & ~option][["gsis_id", "player", "team", "apy", "apy_cap_pct", "year_signed", "years", "date_of_birth"]]
    pl = data.load_players()[["pfr_id", "gsis_id"]].dropna().drop_duplicates("gsis_id")
    sc = data.load_snap_counts(last)
    active = set(pl[pl.pfr_id.isin(sc[sc.offense_snaps > 0].pfr_player_id)].gsis_id) | set(rush[rush.season == last].gsis_id)
    fa = fa[fa.gsis_id.isin(active)].copy()
    drop = [k for k, v in NEWS.items() if v[0] == "drop"]
    find["fa_removed_after_news_check"] = [[k, NEWS[k][1]] for k in drop if k in set(fa.player)]
    fa = fa[~fa.player.isin(drop)]
    fa["news_note"] = fa.player.map(lambda p_: NEWS.get(p_, ("", ""))[1])
    cur = rush[rush.season == last].sort_values("car").drop_duplicates("gsis_id", keep="last").set_index("gsis_id").team_now
    fa["otc_team"] = fa.team
    fa["team"] = fa.gsis_id.map(cur).fillna(fa.team)
    find["fa_contracts_ending"] = len(fa)
    two = n[n.season.isin([last - 1, last])].groupby("gsis_id").agg(att=("rush_attempts", "sum"), yds=("rush_yards", "sum"),
                                                                   ryoe=("ryoe_yds", "sum"), seasons=("season", lambda s: "+".join(str(int(v)) for v in sorted(s)))).reset_index()
    fa = fa.merge(two, on="gsis_id", how="left")
    find["fa_without_ngs"] = int(fa.att.isna().sum())
    fa_ngs = fa[fa.att >= 100].copy()
    fa_ngs["ypc"] = fa_ngs.yds / fa_ngs.att; fa_ngs["ryoe_pc"] = fa_ngs.ryoe / fa_ngs.att; fa_ngs["xypc"] = fa_ngs.ypc - fa_ngs.ryoe_pc
    # shrink RYOE per carry toward 0 by its reliability: r of a season of ~avg carries -> k carries of prior
    r_ = max(find["yoy_r"]["ryoe_pc"], 0.05); avg_att = float(pairs.rush_attempts.mean())
    k = avg_att * (1 - r_) / r_
    find["ryoe_shrink_k_carries"] = round(k)
    fa_ngs["ryoe_pc_shrunk"] = fa_ngs.ryoe_pc * fa_ngs.att / (fa_ngs.att + k)
    fa_ngs = fa_ngs.merge(BIRTH, on="gsis_id", how="left")
    fa_ngs["age_2027"] = ((pd.Timestamp(f"{last + 1}-09-01") - fa_ngs.birth).dt.days / 365.25).round(1)
    med_apy = float(fa_ngs.apy.median())
    def flag(r):
        f_ = []
        if r.ryoe_pc > 0.3 and r.apy <= med_apy:
            f_.append("value: beats expectation at a modest price")
        elif r.ryoe_pc > 0.3:
            f_.append("beats expectation")
        if r.ypc >= find["league_ypc"] and r.ryoe_pc < 0:
            f_.append("careful: yards came from the blocking")
        elif r.ryoe_pc < -0.3:
            f_.append("below expectation")
        if r.player == "Kimani Vidal":
            f_.append("restricted free agent")
        if r.age_2027 >= 28:
            f_.append("age 28+ in 2027")
        return "; ".join(f_)
    fa_ngs["value_flag"] = fa_ngs.apply(flag, axis=1)
    fa_ngs = fa_ngs.sort_values("ryoe_pc", ascending=False)
    find["fa_seasons"] = dict(zip(fa_ngs.player, fa_ngs.seasons))
    cols_out = ["player", "team", "otc_team", "apy", "apy_cap_pct", "seasons", "att", "yds", "ypc", "xypc", "ryoe", "ryoe_pc", "ryoe_pc_shrunk", "age_2027", "value_flag", "news_note"]
    fa_ngs[cols_out].round(3).to_csv(OUT / f"free_agents_{last + 1}_rbs.csv", index=False)
    find["fa_class"] = last + 1; find["fa_n"] = len(fa_ngs); find["fa_median_apy_musd"] = round(med_apy, 2)
    find["fa_list"] = fa_ngs[["player", "team", "att", "ypc", "xypc", "ryoe_pc", "apy", "age_2027", "value_flag", "seasons"]].round(2).values.tolist()

    pr2 = rush[rush.season.isin([last - 1, last])].groupby("gsis_id").agg(car=("car", "sum"), yds=("yds", "sum"), epa=("epa", "mean")).reset_index()
    other = fa[~fa.gsis_id.isin(fa_ngs.gsis_id)].drop(columns=["att", "yds", "ryoe", "seasons"]).merge(pr2, on="gsis_id")
    other = other[other.car >= 100].assign(ypc=lambda d: d.yds / d.car).sort_values("car", ascending=False)
    other[["player", "team", "apy", "car", "yds", "ypc", "news_note"]].round(2).to_csv(OUT / f"free_agents_{last + 1}_rbs_no_ngs.csv", index=False)
    find["fa_other_100car"] = other[["player", "team", "car", "ypc", "apy"]].round(2).values.tolist()
    find["fa_other_notes"] = dict(zip(other.player, other.news_note))
    top = fa_ngs.head(14).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.8, 6.4))
    yy = np.arange(len(top))
    ax.barh(yy, top.ryoe_pc, color=[plot.ACCENT if v > 0 else plot.ACCENT2 for v in top.ryoe_pc], height=0.6)
    ax.set_yticks(yy); ax.set_yticklabels(top.player + " (" + top.team.fillna("") + ")"); ax.grid(axis="y", visible=False)
    ax.axvline(0, color=plot.INK, lw=0.8)
    for yi, (v, a_, xp, ss) in enumerate(zip(top.ryoe_pc, top.att, top.xypc, top.seasons)):
        ax.text(v + (0.04 if v >= 0 else -0.04), yi, f"{v:+.2f} on {a_:.0f} carries, {ss.replace('+', ' and ')} (exp. {xp:.1f} YPC)", va="center",
                ha="left" if v >= 0 else "right", fontsize=8.5, color=plot.MUTED)
    ax.set_xlim(min(-3.2, top.ryoe_pc.min() - 2.9), max(2.6, top.ryoe_pc.max() + 1.9))
    ax.set_xlabel(f"Rush yards over expected per carry, NGS season rows {last - 1} and {last} (through Week {find['through_week']})")
    plot.finish(fig, ax, f"The {last + 1} free-agent backs, ranked by yards over expected",
                f"Contracts ending after {last} (Over The Cap), active in {last}, 100+ NGS carries; first-round option deals left out", OUT / "free_agent_rbs.png", source=SRC)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    with open(OUT / "models.txt", "w") as f:
        for name, mdl in [("Next-season rushing EPA per carry ~ EPA + expected YPC + RYOE per carry + 8+ box share", me),
                          ("Next-season rushing yards ~ expected yards + RYOE + rush TDs + receiving yards", py),
                          ("Next-season YPC ~ expected YPC + RYOE per carry (50+ next carries, weighted by next carries)", pyv),
                          ("Next-season rushing yards ~ the same + platform carries", pyc),
                          ("Market, per carry: APY % of cap ~ carries + expected YPC + RYOE per carry + rush TDs + receiving yards", pc_),
                          ("Market: APY % of cap ~ expected yards + RYOE + rush TDs + receiving yards", pm),
                          ("Market, box score: APY % of cap ~ carries + rush yards + rush TDs + receiving yards", bs),
                          ("Market, box score + RYOE per carry", bs2)]:
            f.write(f"=== {name} (clustered by player)\n{mdl.summary()}\n\n")
    for k_, v_ in find.items():
        print(k_, v_)


if __name__ == "__main__":
    main()
