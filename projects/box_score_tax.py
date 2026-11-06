"""07 The Box-Score Tax: NFL teams pay for the stats that don't repeat.

Where is value hiding? Our guess: in the gap between what a stat says about the past and what it
says about the future. Sacks and interceptions are the headline defensive stats, the ones that make
highlight packages, Pro Bowls and contract press releases. They are also rare events, so they are
noisy. Pressures (for pass rushers) and yards allowed per target (for cover players) happen on many
more snaps. If the market pays for the headline stat more than it predicts the future, teams that
buy the stable stat get the same future production for less money.

Tests:
  1. Stability: which stat repeats year to year?
  2. Prediction: what best predicts NEXT year's sacks / interceptions?
  3. Price: in real contracts (Over The Cap, signed 2019-2026), how much does the market pay per
     sack vs per non-sack pressure, per interception vs coverage quality? Compare price to prediction.
  4. Who is mispriced now.
Data: Pro Football Reference advanced defense (via nflverse, 2018+), nflverse snap counts,
Over The Cap contracts (via nflverse). Run: python -m projects.box_score_tax
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import statsmodels.api as sm

from nflan import data, plot

SRC = "Data: Pro Football Reference and Over The Cap via nflverse. Chart: Dylan Fanelli"

OUT = Path("reports/07-box-score-tax")
CAP_2026 = 301.2  # $M, NFL announcement Feb 2026
FRONT = {"DE", "DT", "DL", "NT", "OLB", "EDGE"}
DBS = {"CB", "S", "FS", "SS", "DB"}


def player_seasons() -> pd.DataFrame:
    d = data.load_pfr_def()
    d["is_total"] = d.tm.fillna("").str.endswith("TM")
    d = d.sort_values("is_total", ascending=False).drop_duplicates(["season", "pfr_id"])  # one row per player-season
    last = int(d.season.max())
    s = data.load_snap_counts(range(2018, last + 1))
    s = s[s.game_type == "REG"]
    snaps = s.groupby(["season", "pfr_player_id"]).agg(def_snaps=("defense_snaps", "sum"), snap_pos=("position", "last"),
                                                      games=("defense_snaps", lambda x: (x > 0).sum())).reset_index()
    m = d.merge(snaps, left_on=["season", "pfr_id"], right_on=["season", "pfr_player_id"], how="inner")
    for c in ["sk", "prss", "hrry", "qbkd", "int", "tgt", "cmp", "yds", "td"]:
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0)
    m["ns_prss"] = (m.prss - m.sk).clip(lower=0)  # PFR pressures include sacks
    m["sk100"] = 100 * m.sk / m.def_snaps
    m["prss100"] = 100 * m.prss / m.def_snaps
    m["ypt"] = m.yds / m.tgt.replace(0, np.nan)
    m["int_rate"] = m["int"] / m.tgt.replace(0, np.nan)
    m["cmp_pct"] = m.cmp / m.tgt.replace(0, np.nan)
    pl = data.load_players()[["pfr_id", "gsis_id"]].dropna().drop_duplicates("pfr_id")
    return m.merge(pl, on="pfr_id", how="left"), last


def next_year(df: pd.DataFrame, cols) -> pd.DataFrame:
    a = df[["pfr_id", "season"] + cols]
    return a.merge(a.assign(season=a.season - 1), on=["pfr_id", "season"], suffixes=("", "_next"))


def veteran_contracts(positions) -> pd.DataFrame:
    c = data.load_contracts()
    c = c[c.position.isin(positions) & c.gsis_id.notna() & c.apy_cap_pct.notna()].copy()
    rookie = c.draft_year.notna() & (c.year_signed == c.draft_year)
    c = c[~rookie & (c.year_signed.between(2019, 2026)) & (c.apy_cap_pct >= 0.004)]
    return c.drop_duplicates(["gsis_id", "year_signed", "apy"])


def ols(y, X, groups=None):
    X = sm.add_constant(X)
    if groups is not None:
        ok = X.notna().all(axis=1) & y.notna()
        g = pd.factorize(groups[ok])[0]
        return sm.OLS(y[ok], X[ok]).fit(cov_type="cluster", cov_kwds={"groups": g})
    return sm.OLS(y, X, missing="drop").fit(cov_type="HC1")


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    ps, last = player_seasons()
    full = ps[ps.season < last]
    find = {"seasons": f"2018-{last}", "cap_2026_musd": CAP_2026}

    # ---------------- Part A: pass rushers ----------------
    rush = full[(full.def_snaps >= 300) & (full.snap_pos.isin(FRONT) | (full.prss >= 15))].copy()
    conv = rush.sk.sum() / rush.prss.sum()
    find["rush_player_seasons"] = len(rush)
    find["league_sacks_per_pressure"] = round(float(conv), 3)
    ny = next_year(rush, ["sk100", "prss100", "sk", "prss", "ns_prss", "def_snaps"])
    find["rush_pairs"] = len(ny)
    find["yoy_r_sack_rate"] = round(float(ny.sk100.corr(ny.sk100_next)), 3)
    find["yoy_r_pressure_rate"] = round(float(ny.prss100.corr(ny.prss100_next)), 3)
    find["r_next_sack_rate_from_sack_rate"] = find["yoy_r_sack_rate"]
    find["r_next_sack_rate_from_pressure_rate"] = round(float(ny.prss100.corr(ny.sk100_next)), 3)
    # weights for predicting next-year sack RATE from this year's sacks and non-sack pressures (rates)
    ny["ns100"] = 100 * ny.ns_prss / ny.def_snaps
    pr = ols(ny.sk100_next, ny[["sk100", "ns100"]])
    find["predict_weight_sack"] = round(float(pr.params["sk100"]), 3)
    find["predict_weight_nonsack_pressure"] = round(float(pr.params["ns100"]), 3)
    find["predict_ratio_sack_to_pressure"] = round(float(pr.params["sk100"] / pr.params["ns100"]), 2)

    # market: veteran ED/IDL contracts, platform = season before signing
    c = veteran_contracts(["ED", "IDL"])
    plat = ps[ps.def_snaps >= 300][["gsis_id", "season", "sk", "ns_prss", "prss", "def_snaps", "player", "age"]].rename(columns={"season": "platform"})
    mk = c.merge(plat, left_on=["gsis_id"], right_on=["gsis_id"])
    mk = mk[mk.platform == mk.year_signed - 1].copy()
    mk["apy_pct"] = 100 * mk.apy_cap_pct
    mk["sk17"] = mk.sk * 17 / 17  # counts, kept as season totals
    mr = ols(mk.apy_pct, mk[["sk", "ns_prss", "def_snaps"]].assign(def_snaps=mk.def_snaps / 100), groups=mk.gsis_id)
    find["market_players"] = int(mk.gsis_id.nunique())
    find["market_contracts"] = len(mk)
    find["market_pct_cap_per_sack"] = round(float(mr.params["sk"]), 3)
    find["market_pct_cap_per_nonsack_pressure"] = round(float(mr.params["ns_prss"]), 3)
    find["market_ratio_sack_to_pressure"] = round(float(mr.params["sk"] / mr.params["ns_prss"]), 2)
    find["market_r2"] = round(float(mr.rsquared), 3)
    find["musd_per_sack_2026"] = round(float(mr.params["sk"]) / 100 * CAP_2026, 2)
    find["musd_per_nonsack_pressure_2026"] = round(float(mr.params["ns_prss"]) / 100 * CAP_2026, 2)
    # prediction weights in COUNT terms on the same kind of players (for a like-for-like ratio)
    nyc = next_year(rush, ["sk", "ns_prss", "def_snaps"])
    pc = ols(nyc.sk_next, nyc[["sk", "ns_prss", "def_snaps"]].assign(def_snaps=nyc.def_snaps / 100), groups=nyc.pfr_id)
    find["predict_count_weight_sack"] = round(float(pc.params["sk"]), 3)
    find["predict_count_weight_nonsack"] = round(float(pc.params["ns_prss"]), 3)
    find["predict_count_ratio"] = round(float(pc.params["sk"] / pc.params["ns_prss"]), 2)
    # bootstrap: how sure are we that the market ratio exceeds the predictive ratio?
    rng = np.random.default_rng(7)
    Xm = sm.add_constant(mk[["sk", "ns_prss"]].assign(s=mk.def_snaps / 100)).values; ym = mk.apy_pct.values
    Xp = sm.add_constant(nyc[["sk", "ns_prss"]].assign(s=nyc.def_snaps / 100)).values; yp = nyc.sk_next.values
    diffs, mrs, prs_ = [], [], []
    gm = pd.factorize(mk.gsis_id)[0]; gp = pd.factorize(nyc.pfr_id)[0]
    idx_m = [np.where(gm == k)[0] for k in range(gm.max() + 1)]; idx_p = [np.where(gp == k)[0] for k in range(gp.max() + 1)]
    for _ in range(1000):  # resample players, not rows
        i = np.concatenate([idx_m[k] for k in rng.integers(0, len(idx_m), len(idx_m))])
        j = np.concatenate([idx_p[k] for k in rng.integers(0, len(idx_p), len(idx_p))])
        bm = np.linalg.lstsq(Xm[i], ym[i], rcond=None)[0]; bp = np.linalg.lstsq(Xp[j], yp[j], rcond=None)[0]
        mrs.append(bm[1] / bm[2]); prs_.append(bp[1] / bp[2]); diffs.append(bm[1] / bm[2] - bp[1] / bp[2])
    find["market_ratio_ci90"] = [round(float(x), 2) for x in np.percentile(mrs, [5, 95])]
    find["predict_ratio_ci90"] = [round(float(x), 2) for x in np.percentile(prs_, [5, 95])]
    find["share_boot_market_above_predict"] = round(float(np.mean(np.array(diffs) > 0)), 3)

    # the tax: a 'lucky' sack (one more sack, same pressures) is paid X but predicts only Y future sacks
    find["future_sacks_per_extra_sack"] = find["predict_count_weight_sack"]
    find["future_sacks_per_extra_nonsack_pressure"] = find["predict_count_weight_nonsack"]
    find["musd_per_future_sack_buying_sacks"] = round(find["musd_per_sack_2026"] / max(pc.params["sk"], 1e-6), 2)
    find["musd_per_future_sack_buying_pressures"] = round(find["musd_per_nonsack_pressure_2026"] / max(pc.params["ns_prss"], 1e-6), 2)

    # sack luck: sacks above what pressures predict at league conversion; does it repeat? is it paid?
    rush["sack_luck"] = rush.sk - conv * rush.prss
    nl = next_year(rush, ["sack_luck"])
    find["yoy_r_sack_luck"] = round(float(nl.sack_luck.corr(nl.sack_luck_next)), 3)
    mk["sack_luck"] = mk.sk - conv * mk.prss
    ml = ols(mk.apy_pct, mk[["prss", "sack_luck"]].assign(def_snaps=mk.def_snaps / 100), groups=mk.gsis_id)
    # what a lucky sack actually buys: next-year sacks per lucky sack vs per pressure (same controls)
    nlk = next_year(rush, ["sk", "prss", "sack_luck", "def_snaps"])
    fl = ols(nlk.sk_next, nlk[["prss", "sack_luck"]].assign(def_snaps=nlk.def_snaps / 100), groups=nlk.pfr_id)
    find["future_sacks_per_lucky_sack"] = round(float(fl.params["sack_luck"]), 3)
    find["future_sacks_per_lucky_sack_ci"] = [round(float(x), 3) for x in fl.conf_int().loc["sack_luck"]]
    find["future_sacks_per_pressure"] = round(float(fl.params["prss"]), 3)
    find["musd_per_lucky_sack_2026"] = round(float(ml.params["sack_luck"]) / 100 * CAP_2026, 2)
    find["musd_per_lucky_sack_ci"] = [round(float(x) / 100 * CAP_2026, 2) for x in ml.conf_int().loc["sack_luck"]]
    find["musd_per_pressure_2026"] = round(float(ml.params["prss"]) / 100 * CAP_2026, 2)
    find["musd_per_future_sack_via_luck"] = round(float(ml.params["sack_luck"]) / 100 * CAP_2026 / fl.params["sack_luck"], 2)
    find["musd_per_future_sack_via_pressure"] = round(float(ml.params["prss"]) / 100 * CAP_2026 / fl.params["prss"], 2)
    # robustness: the lucky-sack price under several cuts of the contract sample
    rob = []
    variants = {
        "base": mk,
        "deals >= 1% of cap": mk[mk.apy_cap_pct >= 0.01],
        "edge only": mk[mk.position == "ED"],
        "interior only": mk[mk.position == "IDL"],
        "multi-year deals": mk[mk.years >= 2],
        "signed 2023-2026": mk[mk.year_signed >= 2023],
    }
    for name, d_ in variants.items():
        X = d_[["prss", "sack_luck"]].assign(def_snaps=d_.def_snaps / 100)
        if name == "base":
            X = X.assign(age=d_.age.astype(float), age2=d_.age.astype(float) ** 2)
            name = "base + age"
        m_ = ols(d_.apy_pct, X, groups=d_.gsis_id)
        lo, hi = m_.conf_int().loc["sack_luck"]
        rob.append({"sample": name, "contracts": len(d_), "musd_per_lucky_sack": round(m_.params["sack_luck"] / 100 * CAP_2026, 2),
                    "ci_low": round(lo / 100 * CAP_2026, 2), "ci_high": round(hi / 100 * CAP_2026, 2)})
    rob = pd.DataFrame(rob); rob.to_csv(OUT / "robustness_lucky_sack_price.csv", index=False)
    find["robust_min"] = float(rob.musd_per_lucky_sack.min()); find["robust_max"] = float(rob.musd_per_lucky_sack.max())
    find["robust_all_ci_above_zero"] = bool((rob.ci_low > 0).all())
    find["robust_n"] = len(rob)
    rec = rob[rob["sample"] == "signed 2023-2026"].iloc[0]
    find["recent_deals_price"] = [float(rec.musd_per_lucky_sack), float(rec.ci_low), float(rec.ci_high)]

    mk[["player_x", "year_signed", "team", "apy", "apy_cap_pct", "platform", "sk", "prss", "ns_prss", "sack_luck", "def_snaps"]].rename(
        columns={"player_x": "player"}).sort_values(["year_signed", "apy"], ascending=[True, False]).round(3).to_csv(OUT / "rusher_contracts_with_platform.csv", index=False)

    # chart A: stability
    fig, axs = plt.subplots(1, 2, figsize=(11, 5), sharey=False)
    for ax, (x, y, lab, col) in zip(axs, [("sk100", "sk100_next", "Sacks per 100 snaps", plot.ACCENT2),
                                          ("prss100", "prss100_next", "Pressures per 100 snaps", plot.ACCENT)]):
        ax.scatter(ny[x], ny[y], s=9, alpha=0.35, color=col)
        r = ny[x].corr(ny[y]); ax.set_xlabel(f"{lab}, season N"); ax.set_ylabel("Season N+1")
        ax.text(0.03, 0.92, f"r = {r:.2f}", transform=ax.transAxes, fontsize=12, fontweight="bold", color=col)
    fig.suptitle("Pressures repeat; sacks bounce around", x=0.01, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.01, 0.9, f"Pass rushers, back-to-back seasons with 300+ defensive snaps, 2018-{last - 1} ({len(ny):,} pairs)", color=plot.MUTED)
    fig.text(0.01, 0.005, "Data: Pro Football Reference via nflverse. Chart: Dylan Fanelli", color=plot.MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.02, 1, 0.88)); fig.savefig(OUT / "rush_stability.png", bbox_inches="tight"); plt.close(fig)

    # chart B: price vs prediction
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["What the market pays\n(sack vs non-sack pressure)", "What predicts next year's sacks\n(sack vs non-sack pressure)"]
    vals = [find["market_ratio_sack_to_pressure"], find["predict_count_ratio"]]
    ax.bar(labels, vals, color=[plot.ACCENT2, plot.ACCENT], width=0.55)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.1, f"{v:.2f}x", ha="center", fontsize=13, fontweight="bold")
    ax.set_ylabel("Value of one sack, in non-sack pressures"); ax.grid(axis="x", visible=False)
    plot.finish(fig, ax, "The sack tax: teams pay for sacks far beyond what they predict",
                f"Veteran ED/IDL contracts 2019-2026 ({len(mk)}, {mk.gsis_id.nunique()} players) vs next-season sacks, 2018-{last - 1}. Direction, not proof", OUT / "sack_tax.png", source=SRC)

    # who is mispriced now: latest full season and season to date
    rows = []
    for season in [last - 1]:  # PFR's current-season file lags snap counts, so only full seasons are rated
        r_ = ps[(ps.season == season) & (ps.def_snaps >= 300) & (ps.snap_pos.isin(FRONT) | (ps.prss >= 8))].copy()
        r_["exp_sk"] = conv * r_.prss
        r_["sack_luck"] = r_.sk - r_.exp_sk
        r_["season"] = season
        rows.append(r_[["season", "player", "tm", "snap_pos", "def_snaps", "sk", "prss", "exp_sk", "sack_luck", "prss100"]])
    board = pd.concat(rows)
    board.round(2).sort_values(["season", "sack_luck"]).to_csv(OUT / "rusher_sack_luck_board.csv", index=False)
    lf = board[board.season == last - 1]
    find["buy_low_last_full"] = lf[lf.prss >= 30].nsmallest(5, "sack_luck")[["player", "tm", "sk", "prss", "exp_sk"]].round(1).values.tolist()
    find["sell_high_last_full"] = lf.nlargest(5, "sack_luck")[["player", "tm", "sk", "prss", "exp_sk"]].round(1).values.tolist()
    find["current_season"] = int(last)
    # 2027 free agents: latest contract for each ED/IDL ends after the current season
    allc = data.load_contracts()
    allc = allc[allc.position.isin(["ED", "IDL"]) & allc.gsis_id.notna()].sort_values("year_signed")
    latest = allc.groupby("gsis_id").tail(1).copy()
    latest["end_year"] = latest.contract_history.map(data.contract_end_year)
    option = (latest.draft_round == 1) & (latest.year_signed == latest.draft_year)  # 5th-year option can extend these
    fa = latest[(latest.end_year == last) & ~option][["gsis_id", "player", "position", "team", "apy", "year_signed", "years"]]
    two = ps[(ps.season == last - 1) & ps.gsis_id.notna()][["gsis_id", "sk", "prss", "def_snaps"]].rename(columns={"def_snaps": "snaps"})
    fa = fa.merge(two, on="gsis_id")
    pl = data.load_players()[["pfr_id", "gsis_id"]].dropna().drop_duplicates("gsis_id")
    sc = data.load_snap_counts(last)
    active = set(pl[pl.pfr_id.isin(sc[sc.defense_snaps > 0].pfr_player_id)].gsis_id)
    fa = fa[(fa.snaps >= 300) & fa.gsis_id.isin(active)].copy()  # played defense this season = still in the league
    fa["prss100"] = 100 * fa.prss / fa.snaps
    fa["exp_sk"] = conv * fa.prss
    fa["sack_luck"] = fa.sk - fa.exp_sk
    fa["value_flag"] = np.where((fa.prss100 >= fa.prss100.quantile(0.5)) & (fa.sack_luck < 0), "buy: pressure without the sacks",
                                np.where(fa.sack_luck > 2, "careful: sacks above pressures", ""))
    fa = fa.sort_values("prss100", ascending=False)
    fa.round(2).to_csv(OUT / f"free_agents_{last + 1}_rushers.csv", index=False)
    find["fa_class"] = last + 1
    find["fa_rushers_n"] = len(fa)
    find["fa_buy_targets"] = fa[fa.value_flag.str.startswith("buy")].head(6)[["player", "position", "apy", "sk", "prss", "prss100"]].round(1).values.tolist()
    find["fa_careful"] = fa[fa.value_flag.str.startswith("careful")].head(5)[["player", "position", "apy", "sk", "prss"]].round(1).values.tolist()

    top = lf[(lf.prss >= 30) & (lf.sack_luck <= -1)].sort_values("sack_luck").head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 6.2))
    y = np.arange(len(top))
    ax.barh(y - 0.2, top.exp_sk, height=0.4, color=plot.ACCENT, label="Sacks his pressures predict")
    ax.barh(y + 0.2, top.sk, height=0.4, color=plot.ACCENT2, label="Actual sacks")
    ax.set_yticks(y); ax.set_yticklabels(top.player + " (" + top.tm + ")"); ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=True, facecolor="white", edgecolor="white"); ax.set_xlabel("Sacks")
    plot.finish(fig, ax, f"Buy low: {last - 1} rushers whose sacks lag their pressures",
                f"30+ pressures. Expected sacks = pressures x league rate ({conv:.2f} sacks per pressure)", OUT / "buy_low_rushers.png", source=SRC)

    # ---------------- Part B: coverage ----------------
    cov = full[(full.tgt >= 40) & full.snap_pos.isin(DBS)].copy()
    nc = next_year(cov, ["int_rate", "ypt", "cmp_pct", "int", "tgt"])
    find["cov_pairs"] = len(nc)
    find["yoy_r_int_rate"] = round(float(nc.int_rate.corr(nc.int_rate_next)), 3)
    find["yoy_r_yds_per_target"] = round(float(nc.ypt.corr(nc.ypt_next)), 3)
    find["yoy_r_cmp_pct"] = round(float(nc.cmp_pct.corr(nc.cmp_pct_next)), 3)
    find["r_next_int_rate_from_int_rate"] = find["yoy_r_int_rate"]
    find["r_next_ypt_from_ypt"] = find["yoy_r_yds_per_target"]
    cc = veteran_contracts(["CB", "S"])
    platc = ps[(ps.tgt >= 30)][["gsis_id", "season", "int", "ypt", "tgt", "def_snaps", "cmp_pct"]].rename(columns={"season": "platform"})
    mc = cc.merge(platc, on="gsis_id")
    mc = mc[mc.platform == mc.year_signed - 1].copy()
    mc["apy_pct"] = 100 * mc.apy_cap_pct
    cr = ols(mc.apy_pct, mc[["int", "ypt", "def_snaps"]].assign(def_snaps=mc.def_snaps / 100), groups=mc.gsis_id)
    find["cov_market_contracts"] = len(mc)
    find["musd_per_int_2026"] = round(float(cr.params["int"]) / 100 * CAP_2026, 2)
    find["musd_per_int_ci"] = [round(float(x) / 100 * CAP_2026, 2) for x in cr.conf_int().loc["int"]]
    find["musd_per_ypt_2026"] = round(float(cr.params["ypt"]) / 100 * CAP_2026, 2)
    find["musd_per_ypt_ci"] = [round(float(x) / 100 * CAP_2026, 2) for x in cr.conf_int().loc["ypt"]]
    nci = next_year(cov, ["int", "ypt", "tgt", "def_snaps"])
    pi = ols(nci.ypt_next, nci[["int", "ypt"]])
    find["ints_predict_next_ypt_coef"] = round(float(pi.params["int"]), 3)
    find["ints_predict_next_ypt_p"] = round(float(pi.pvalues["int"]), 3)
    fig, ax = plt.subplots(figsize=(8, 5))
    stats = [("Interceptions\nper target", find["yoy_r_int_rate"]), ("Completion %\nallowed", find["yoy_r_cmp_pct"]),
             ("Yards per target\nallowed", find["yoy_r_yds_per_target"])]
    ax.bar([s_[0] for s_ in stats], [s_[1] for s_ in stats], color=[plot.ACCENT2, plot.MUTED, plot.ACCENT], width=0.55)
    for i, (_, v) in enumerate(stats):
        ax.text(i, v + 0.01, f"r = {v:.2f}", ha="center", fontsize=12, fontweight="bold")
    ax.set_ylabel("Year-to-year correlation"); ax.grid(axis="x", visible=False); ax.set_ylim(0, max(0.4, max(v for _, v in stats) + 0.08))
    plot.finish(fig, ax, "Coverage: the hypothesis failed. Interception rate repeats best",
                f"Corners and safeties, back-to-back seasons with 40+ targets, 2018-{last - 1} ({len(nc):,} pairs). PFR charting.", OUT / "coverage_stability.png", source=SRC)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    with open(OUT / "models.txt", "w") as f:
        for name, mdl in [("Predict next-year sack rate from rates", pr), ("Market: APY % of cap ~ sacks + non-sack pressures + snaps", mr),
                          ("Predict next-year sacks (counts)", pc), ("Market: APY % of cap ~ pressures + sack luck + snaps", ml),
                          ("Coverage market: APY % of cap ~ INTs + yards/target + snaps", cr), ("Next-year yards/target ~ INTs + yards/target", pi)]:
            f.write(f"=== {name}\n{mdl.summary()}\n\n")
    for k, v in find.items():
        print(k, v)


if __name__ == "__main__":
    main()
