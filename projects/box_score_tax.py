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
INTERIOR = {"DT", "NT", "DL"}
MIN_PRESSURES_FLAG = 20  # a buy or careful flag needs at least this many pressures
LUCK_FLAG = 2.0  # and a gap of at least this many sacks between actual and expected
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


def one_deal_per_player_year(c: pd.DataFrame) -> pd.DataFrame:
    """A tag or tender and a long-term deal signed in the same year are one decision: keep the longer, then richer, deal."""
    return c.sort_values(["years", "apy"], ascending=False, kind="mergesort").drop_duplicates(["gsis_id", "year_signed"])


def veteran_contracts(positions, first=2019, last=None) -> pd.DataFrame:
    c = data.load_contracts()
    c = c[c.position.isin(positions) & c.gsis_id.notna() & c.apy_cap_pct.notna()].copy()
    last = last or int(c.year_signed.max())
    rookie = c.draft_year.notna() & (c.year_signed == c.draft_year)
    c = c[~rookie & (c.year_signed.between(first, last)) & (c.apy_cap_pct >= 0.004)]
    return one_deal_per_player_year(c)


def rush_group(snap_pos: pd.Series) -> pd.Series:
    """Interior linemen convert pressures to sacks at a lower rate than edge players, so luck is measured within group."""
    return np.where(snap_pos.isin(INTERIOR), "interior", "edge")


def sack_luck(df: pd.DataFrame, conv: dict) -> pd.Series:
    return df.sk - df.grp.map(conv) * df.prss


def shrunk_luck(sk, prss, conv, k):
    """Sack luck after shrinking the player's conversion rate toward his group's rate (k = prior pressures)."""
    return (sk + k * conv) / (prss + k) * prss - conv * prss


def add_prior(df: pd.DataFrame, ps: pd.DataFrame, key: str, season: str) -> pd.DataFrame:
    """Attach the season before the platform year (pressures, sacks) so one hot year is not read as the whole record."""
    prev = ps[[key, "season", "prss", "sk"]].rename(columns={"prss": "prev_prss", "sk": "prev_sk"})
    prev = prev.assign(**{season: prev.season + 1}).drop(columns=["season"] if season != "season" else [])
    out = df.merge(prev.drop_duplicates([key, season]), on=[key, season], how="left")
    out["has_prev"] = out.prev_prss.notna().astype(float)
    out[["prev_prss", "prev_sk"]] = out[["prev_prss", "prev_sk"]].fillna(0)
    return out


def boot_players(frames: dict, fn, n=1000, seed=7):
    """Resample players (not rows) in each frame and recompute fn; returns the list of results."""
    rng = np.random.default_rng(seed)
    idx = {k: [g.index.values for _, g in d.reset_index(drop=True).groupby(key)] for k, (d, key) in frames.items()}
    base = {k: d.reset_index(drop=True) for k, (d, key) in frames.items()}
    out = []
    for _ in range(n):
        samp = {k: base[k].loc[np.concatenate([idx[k][j] for j in rng.integers(0, len(idx[k]), len(idx[k]))])] for k in base}
        out.append(fn(samp))
    return out


def _beta(y, X):
    A = np.column_stack([np.ones(len(X)), X.values.astype(float)])
    return np.linalg.lstsq(A, y.values.astype(float), rcond=None)[0][1:]


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

    # sack luck: sacks above what pressures predict at the player's GROUP rate (edge or interior); does it repeat? is it paid?
    rush["grp"] = rush_group(rush.snap_pos)
    conv_g = (rush.groupby("grp").sk.sum() / rush.groupby("grp").prss.sum()).to_dict()
    find["sacks_per_pressure_by_group"] = {k: round(float(v), 3) for k, v in conv_g.items()}
    rush["sack_luck"] = sack_luck(rush, conv_g)
    nl = next_year(rush, ["sack_luck"])
    find["yoy_r_sack_luck"] = round(float(nl.sack_luck.corr(nl.sack_luck_next)), 3)
    mk["grp"] = np.where(mk.position == "IDL", "interior", "edge")
    mk["sack_luck"] = sack_luck(mk, conv_g)
    mk["age"] = pd.to_numeric(mk.age, errors="coerce")
    mk = add_prior(mk, ps.dropna(subset=["gsis_id"]), "gsis_id", "platform")
    PX = ["prss", "sack_luck", "snaps100", "age", "age2", "prev_prss", "prev_sk", "has_prev"]
    mk = mk.assign(snaps100=mk.def_snaps / 100, age2=mk.age ** 2).dropna(subset=["age"]).reset_index(drop=True)
    find["market_contracts"] = len(mk); find["market_players"] = int(mk.gsis_id.nunique())
    ml = ols(mk.apy_pct, mk[PX], groups=mk.gsis_id)
    ml_simple = ols(mk.apy_pct, mk[["prss", "sack_luck", "snaps100"]], groups=mk.gsis_id)
    # what a lucky sack predicts: next-year sacks and next-year pressures, same controls
    rush["age"] = pd.to_numeric(rush.age, errors="coerce")
    nlk = next_year(rush, ["sk", "prss", "sack_luck", "def_snaps", "age"]).dropna(subset=["age"])
    nlk = add_prior(nlk, ps, "pfr_id", "season")
    nlk = nlk.assign(snaps100=nlk.def_snaps / 100, age2=nlk.age ** 2).reset_index(drop=True)
    fl = ols(nlk.sk_next, nlk[PX], groups=nlk.pfr_id)
    fp = ols(nlk.prss_next, nlk[PX], groups=nlk.pfr_id)
    find["predict_pairs_with_controls"] = len(nlk)
    find["future_sacks_per_lucky_sack"] = round(float(fl.params["sack_luck"]), 3)
    find["future_sacks_per_lucky_sack_ci"] = [round(float(x), 3) for x in fl.conf_int().loc["sack_luck"]]
    find["future_sacks_per_pressure"] = round(float(fl.params["prss"]), 3)
    find["future_pressures_per_lucky_sack"] = round(float(fp.params["sack_luck"]), 3)
    find["future_pressures_per_lucky_sack_ci"] = [round(float(x), 3) for x in fp.conf_int().loc["sack_luck"]]
    usd = lambda b: float(b) / 100 * CAP_2026
    find["musd_per_lucky_sack_2026"] = round(usd(ml.params["sack_luck"]), 2)
    find["musd_per_lucky_sack_ci"] = [round(usd(x), 2) for x in ml.conf_int().loc["sack_luck"]]
    find["musd_per_lucky_sack_no_controls"] = round(usd(ml_simple.params["sack_luck"]), 2)
    find["musd_per_pressure_2026"] = round(usd(ml.params["prss"]), 2)
    find["musd_per_future_sack_via_luck"] = round(usd(ml.params["sack_luck"]) / fl.params["sack_luck"], 2)
    find["musd_per_future_sack_via_pressure"] = round(usd(ml.params["prss"]) / fl.params["prss"], 2)

    # THE TEST (stated before looking): is a lucky sack priced above its predictive value, relative to a pressure?
    #   T = (price per lucky sack / price per pressure) / (future sacks per lucky sack / future sacks per pressure); no tax means T = 1
    def tax_ratio(sm_):
        bm = _beta(sm_["m"].apy_pct, sm_["m"][PX]); bp = _beta(sm_["p"].sk_next, sm_["p"][PX])
        return (bm[1] / bm[0], bp[1] / bp[0], usd(bm[1]) / bp[1] if bp[1] > 0 else np.inf, usd(bm[0]) / bp[0], usd(bm[1]))
    bs = np.array(boot_players({"m": (mk, "gsis_id"), "p": (nlk, "pfr_id")}, tax_ratio, n=2000))
    rel_price, rel_pred = bs[:, 0], bs[:, 1]
    T = np.where(rel_pred > 0, rel_price / np.where(rel_pred > 0, rel_pred, 1), np.inf)
    point_T = (ml.params["sack_luck"] / ml.params["prss"]) / (fl.params["sack_luck"] / fl.params["prss"])
    find["tax_ratio"] = round(float(point_T), 2)
    find["tax_ratio_ci90"] = [round(float(x), 2) for x in np.percentile(T, [5, 95])]
    find["tax_ratio_ci95"] = [round(float(x), 2) for x in np.percentile(T, [2.5, 97.5])]
    find["tax_ratio_share_above_1"] = round(float(np.mean(T > 1)), 3)
    find["tax_ratio_boot_n"] = int(len(T))
    find["musd_per_future_sack_via_luck_ci90"] = [round(float(x), 2) for x in np.percentile(bs[:, 2], [5, 95])]
    find["musd_per_future_sack_via_pressure_ci90"] = [round(float(x), 2) for x in np.percentile(bs[:, 3], [5, 95])]
    find["share_boot_luck_costlier_per_future_sack"] = round(float(np.mean(bs[:, 2] > bs[:, 3])), 3)
    find["share_boot_lucky_sack_price_above_zero"] = round(float(np.mean(bs[:, 4] > 0)), 3)

    # robustness: the lucky-sack price under several cuts of the contract sample (all with age and prior-season controls)
    rob = []
    recent_from = int(mk.year_signed.max()) - 3
    variants = {
        "base (age + prior season)": mk,
        "no age or prior-season controls": mk,
        "deals >= 1% of cap": mk[mk.apy_cap_pct >= 0.01],
        "edge only": mk[mk.position == "ED"],
        "interior only": mk[mk.position == "IDL"],
        "multi-year deals": mk[mk.years >= 2],
        f"signed {recent_from}-{int(mk.year_signed.max())}": mk[mk.year_signed >= recent_from],
        f"signed {int(mk.year_signed.min())}-{recent_from - 1}": mk[mk.year_signed < recent_from],
    }
    for name, d_ in variants.items():
        cols = ["prss", "sack_luck", "snaps100"] if name.startswith("no age") else PX
        m_ = ols(d_.apy_pct, d_[cols], groups=d_.gsis_id)
        lo, hi = m_.conf_int().loc["sack_luck"]
        rob.append({"sample": name, "contracts": len(d_), "musd_per_lucky_sack": round(usd(m_.params["sack_luck"]), 2),
                    "ci_low": round(usd(lo), 2), "ci_high": round(usd(hi), 2)})
    rob = pd.DataFrame(rob); rob.to_csv(OUT / "robustness_lucky_sack_price.csv", index=False)
    find["robust_min"] = float(rob.musd_per_lucky_sack.min()); find["robust_max"] = float(rob.musd_per_lucky_sack.max())
    find["robust_all_ci_above_zero"] = bool((rob.ci_low > 0).all())
    find["robust_ci_above_zero"] = int((rob.ci_low > 0).sum())
    find["robust_n"] = len(rob)
    rec = rob[rob["sample"].str.startswith(f"signed {recent_from}")].iloc[0]
    old = rob[rob["sample"].str.endswith(str(recent_from - 1))].iloc[0]
    find["recent_deals_label"] = rec["sample"].replace("signed ", "")
    find["recent_deals_price"] = [float(rec.musd_per_lucky_sack), float(rec.ci_low), float(rec.ci_high)]
    find["recent_deals_n"] = int(rec.contracts)
    find["earlier_deals_label"] = old["sample"].replace("signed ", "")
    find["earlier_deals_price"] = [float(old.musd_per_lucky_sack), float(old.ci_low), float(old.ci_high)]

    mk[["player_x", "position", "year_signed", "team", "years", "apy", "apy_cap_pct", "platform", "age", "sk", "prss", "ns_prss", "sack_luck", "prev_prss", "prev_sk", "def_snaps"]].rename(
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

    # chart B: the test. cost of one future sack bought through sack luck vs through pressures, with bootstrap intervals
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["Bought through sack luck", "Bought through pressures"]
    vals = [find["musd_per_future_sack_via_luck"], find["musd_per_future_sack_via_pressure"]]
    cis = [find["musd_per_future_sack_via_luck_ci90"], find["musd_per_future_sack_via_pressure_ci90"]]
    top = min(max(c_[1] for c_ in cis), 4 * max(vals))
    ax.bar(labels, vals, color=[plot.ACCENT2, plot.ACCENT], width=0.55)
    for i, (v, c_) in enumerate(zip(vals, cis)):
        ax.plot([i, i], [c_[0], min(c_[1], top)], color=plot.INK, lw=1.4)
        ax.text(i + 0.3, v, f"${v:.2f}M", ha="left", va="center", fontsize=12, fontweight="bold")
    ax.set_ylabel("$M a year per expected future sack (2026 dollars)"); ax.grid(axis="x", visible=False); ax.set_ylim(0, top * 1.05)
    plot.finish(fig, ax, "Sack luck looks overpriced, but the test is not decisive",
                f"Bars: point estimates. Lines: 90% bootstrap intervals (players resampled; upper end cut at the axis). {len(mk)} contracts, {mk.gsis_id.nunique()} players", OUT / "sack_tax.png", source=SRC)

    # who is mispriced now: latest full season and season to date
    # prior strength for shrinking a player's conversion rate: beta-binomial method of moments on rusher-seasons with 20+ pressures
    big = rush[rush.prss >= MIN_PRESSURES_FLAG]
    rate = big.sk / big.prss; pbar = big.grp.map(conv_g)
    within = (pbar * (1 - pbar) / big.prss).mean(); between = max(((rate - pbar) ** 2).mean() - within, 1e-6)
    K_PRIOR = float((pbar * (1 - pbar)).mean() / between)
    find["shrink_prior_pressures"] = round(K_PRIOR, 0)
    rows = []
    for season in [last - 1]:  # PFR's current-season file lags snap counts, so only full seasons are rated
        r_ = ps[(ps.season == season) & (ps.def_snaps >= 300) & (ps.snap_pos.isin(FRONT) | (ps.prss >= 8))].copy()
        r_["grp"] = rush_group(r_.snap_pos)
        r_["exp_sk"] = r_.grp.map(conv_g) * r_.prss
        r_["sack_luck"] = r_.sk - r_.exp_sk
        r_["sack_luck_shrunk"] = shrunk_luck(r_.sk, r_.prss, r_.grp.map(conv_g), K_PRIOR)
        r_["season"] = season
        rows.append(r_[["season", "player", "tm", "snap_pos", "grp", "age", "def_snaps", "sk", "prss", "exp_sk", "sack_luck", "sack_luck_shrunk", "prss100"]])
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
    two = ps[(ps.season == last - 1) & ps.gsis_id.notna()][["gsis_id", "sk", "prss", "def_snaps", "age"]].rename(columns={"def_snaps": "snaps", "age": f"age_{last - 1}"})
    fa = fa.merge(two, on="gsis_id")
    pl = data.load_players()[["pfr_id", "gsis_id"]].dropna().drop_duplicates("gsis_id")
    sc = data.load_snap_counts(last)
    active = set(pl[pl.pfr_id.isin(sc[sc.defense_snaps > 0].pfr_player_id)].gsis_id)
    fa = fa[(fa.snaps >= 300) & fa.gsis_id.isin(active)].copy()  # played defense this season = still in the league
    fa["prss100"] = 100 * fa.prss / fa.snaps
    fa["grp"] = np.where(fa.position == "IDL", "interior", "edge")
    fa["exp_sk"] = fa.grp.map(conv_g) * fa.prss
    fa["sack_luck"] = fa.sk - fa.exp_sk
    fa["sack_luck_shrunk"] = shrunk_luck(fa.sk, fa.prss, fa.grp.map(conv_g), K_PRIOR)
    # flags need a real sample (20+ pressures) and a gap of at least two sacks; the shrunk column shows how little of a gap is skill
    enough = fa.prss >= MIN_PRESSURES_FLAG
    fa["value_flag"] = np.where(enough & (fa.prss100 >= fa.prss100[enough].median()) & (fa.sack_luck <= -LUCK_FLAG), "buy: pressure without the sacks",
                                np.where(enough & (fa.sack_luck >= LUCK_FLAG), "careful: sacks above pressures", ""))
    fa = fa.sort_values("prss100", ascending=False)
    fa.round(2).to_csv(OUT / f"free_agents_{last + 1}_rushers.csv", index=False)
    find["fa_class"] = last + 1
    find["fa_rushers_n"] = len(fa)
    find["fa_buy_targets"] = fa[fa.value_flag.str.startswith("buy")].head(6)[["player", "position", "apy", "sk", "prss", "prss100", f"age_{last - 1}"]].round(1).values.tolist()
    find["fa_careful"] = fa[fa.value_flag.str.startswith("careful")].head(5)[["player", "position", "apy", "sk", "prss", f"age_{last - 1}"]].round(1).values.tolist()
    find["fa_flag_rule"] = {"min_pressures": MIN_PRESSURES_FLAG, "luck_cut_sacks": LUCK_FLAG, "buy_n": int(fa.value_flag.str.startswith("buy").sum()), "careful_n": int(fa.value_flag.str.startswith("careful").sum())}

    top = lf[(lf.prss >= 30) & (lf.sack_luck <= -1)].sort_values("sack_luck").head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 6.2))
    y = np.arange(len(top))
    ax.barh(y - 0.2, top.exp_sk, height=0.4, color=plot.ACCENT, label="Sacks his pressures predict")
    ax.barh(y + 0.2, top.sk, height=0.4, color=plot.ACCENT2, label="Actual sacks")
    ax.set_yticks(y); ax.set_yticklabels(top.player + " (" + top.tm + ")"); ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=True, facecolor="white", edgecolor="white"); ax.set_xlabel("Sacks")
    plot.finish(fig, ax, f"Buy low: {last - 1} rushers whose sacks lag their pressures",
                f"30+ pressures. Expected sacks = pressures x group rate (edge {conv_g['edge']:.2f}, interior {conv_g['interior']:.2f} sacks per pressure)", OUT / "buy_low_rushers.png", source=SRC)

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
