"""10 Draft Value: in rounds 3-7, which positions return the most value per pick, and are some drafted too late?

Michael MacKelvie argues that teams know how to draft and still don't, and that the "safe" pick is the
dangerous one. The testable version: if the draft prices positions correctly, a pick at any position should
return about what the average pick at that slot returns. A position whose round 3-7 picks beat the slot,
on more than one measure, is being drafted too late.

Tests:
  1. The pick-value curve: expected outcome by overall pick, smoothed (kernel in log pick, forced to fall
     with the pick), with the bandwidth chosen by leaving out one draft class at a time.
  2. Value over the curve: each pick's outcome minus the curve at his slot, averaged by position and round,
     with 95% intervals from 1,000 bootstrap samples that resample picks and refit the curve.
  3. Hit rates over expected: became a starter, earned a real second contract (1%+ of the cap).
  4. A Sharpe ratio by position (mean surplus / spread of surplus), MacKelvie's risk-return lens.
  5. Robustness: the same position test on a second outcome measured in money (second-contract APY as a
     share of the cap), on rookie-deal snaps, on the drafting team's AV, and on older classes only.
  The three clearest inefficiencies follow a rule written before the results: rounds 3-7 pooled, AV
  surplus 95% interval clear of zero, second-contract surplus with the same sign; ranked by the weaker of
  the two z-scores.
Data: nflverse draft_picks (PFR: w_av, dr_av, seasons_started, games, probowls, allpro), Over The Cap
contracts via nflverse, nflverse snap counts and players. Drafts 2006-2021 so careers are mostly observed.
Run: python -m projects.draft_value
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.isotonic import IsotonicRegression

from nflan import data, plot
from projects.box_score_tax import ols

OUT = Path("reports/10-draft-value")
SRC = "Data: Pro Football Reference draft tables, Over The Cap and snap counts via nflverse. Chart: Dylan Fanelli"
FIRST, LAST = 2006, 2021          # draft classes; 2021 is the last class with five NFL seasons played
CONTRACT_FIRST = 2011             # Over The Cap lists every drafted player from the 2011 class on
SNAP_FIRST = 2013                 # nflverse snap counts start in 2013
SECOND_WINDOW = (2, 5)            # a second contract is a veteran deal signed 2 to 5 years after the draft
REAL_DEAL = 0.01                  # "earned a second contract": a veteran deal worth 1%+ of the cap a year
OLD_CLASSES = 2017                # robustness: classes with 8+ seasons observed
B = 1000
SPECIALISTS = {"K", "P", "LS"}
POS_ORDER = ["QB", "RB", "WR", "TE", "OT", "IOL", "EDGE", "IDL", "LB", "CB", "S"]
DRAFT_MAP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "T": "OT", "G": "IOL", "C": "IOL",
             "DT": "IDL", "NT": "IDL", "ILB": "LB", "CB": "CB", "S": "S"}
GENERIC = {"DB", "LB", "OLB", "DL", "OL", "DE"}   # labels that do not say edge vs off-ball, CB vs S, 3-4 end vs 4-3 end
OTC_MAP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "LT": "OT", "RT": "OT", "LG": "IOL", "RG": "IOL",
           "C": "IOL", "ED": "EDGE", "IDL": "IDL", "LB": "LB", "CB": "CB", "S": "S"}
PL_MAP = {"CB": "CB", "FS": "S", "SS": "S", "SAF": "S", "S": "S", "DE": "EDGE", "DT": "IDL", "NT": "IDL", "OLB": "LB",
          "ILB": "LB", "MLB": "LB", "G": "IOL", "C": "IOL", "OT": "OT"}


# ------------------------------------------------------------------ positions and outcomes
LABEL_ONLY = {"DE": "EDGE", "OLB": "LB", "LB": "LB", "DL": "IDL", "OL": "IOL"}   # robustness: no later information at all


def position_group(draft_pos, otc_pos=None, pl_pos=None, label_only=False):
    """Specific draft labels are kept (no look-ahead); generic ones (DB, LB, OLB, DL, OL, DE) are split with the
    player's Over The Cap position, then his nflverse players position. Returns None when still unresolved.
    label_only: use the draft label alone (DB stays unresolved, OLB counts as LB), the robustness version."""
    if draft_pos in SPECIALISTS:
        return "ST"
    if draft_pos not in GENERIC:
        return DRAFT_MAP.get(draft_pos)
    if label_only:
        return LABEL_ONLY.get(draft_pos)
    for p, m in ((otc_pos, OTC_MAP), (pl_pos, PL_MAP)):
        if isinstance(p, str) and p in m:
            return m[p]
    return {"DE": "EDGE"}.get(draft_pos)   # an unmatched DE is most often a 4-3 end


def second_contract(c: pd.DataFrame, window=SECOND_WINDOW) -> pd.DataFrame:
    """Largest veteran deal (APY as a share of the cap) signed window[0]..window[1] years after the draft, keyed by
    (draft_year, draft_overall). Rookie deals (signed in the draft year) are not veteran deals."""
    c = c.dropna(subset=["draft_year", "draft_overall", "apy_cap_pct"]).copy()
    lag = c.year_signed - c.draft_year
    v = c[(lag >= window[0]) & (lag <= window[1])]
    return (v.groupby(["draft_year", "draft_overall"]).agg(apy_cap=("apy_cap_pct", "max"), first_vet_year=("year_signed", "min"))
             .reset_index().astype({"draft_year": int, "draft_overall": int}))


def rookie_deal_snaps(snaps: pd.DataFrame, picks: pd.DataFrame) -> pd.Series:
    """Games with half or more of his side's snaps (offense or defense) in his first four seasons."""
    s = snaps[snaps.game_type == "REG"]
    s = s.assign(half=((s.offense_pct >= 0.5) | (s.defense_pct >= 0.5)).astype(int))
    g = s.groupby(["pfr_player_id", "season"]).half.sum().rename("g").reset_index()
    m = picks[["pfr_player_id", "season"]].reset_index().merge(g.rename(columns={"season": "yr"}), on="pfr_player_id", how="left")
    m = m[(m.yr >= m.season) & (m.yr <= m.season + 3)]
    return m.groupby("index").g.sum().reindex(picks.index).fillna(0)


def build() -> pd.DataFrame:
    d = data.load_draft_picks()
    d = d[d.season.between(FIRST, LAST)].copy()
    c = data.load_contracts()
    otc_pos = (c.dropna(subset=["draft_year", "draft_overall"]).sort_values("year_signed")
                .groupby(["draft_year", "draft_overall"]).position.agg(lambda s: s.mode().iloc[0]))
    pl = data.load_players().dropna(subset=["gsis_id"]).drop_duplicates("gsis_id").set_index("gsis_id").position
    d["pos"] = [position_group(p, otc_pos.get((float(s), float(k))), pl.get(g))
                for p, s, k, g in zip(d.position, d.season, d.pick, d.gsis_id)]
    d["pos_label"] = [position_group(p, label_only=True) for p in d.position]
    d["w_av"] = d.w_av.fillna(0); d["dr_av"] = d.dr_av.fillna(0)   # no AV means he never played a down
    d["started"] = (d.seasons_started >= 1).astype(int)
    d["multi_start"] = (d.seasons_started >= 2).astype(int)
    d["pro_bowl"] = (d.probowls >= 1).astype(int)
    sc = second_contract(c)
    d = d.merge(sc, left_on=["season", "pick"], right_on=["draft_year", "draft_overall"], how="left").drop(columns=["draft_year", "draft_overall"])
    has_c = d.season >= CONTRACT_FIRST
    d["apy_pct"] = np.where(has_c, 100 * d.apy_cap.fillna(0), np.nan)      # 0 = no veteran deal in the window
    d["second"] = np.where(has_c, (d.apy_cap.fillna(0) >= REAL_DEAL).astype(float), np.nan)
    sc36 = second_contract(c, (3, 6)).rename(columns={"apy_cap": "apy_cap36"})[["draft_year", "draft_overall", "apy_cap36"]]
    d = d.merge(sc36, left_on=["season", "pick"], right_on=["draft_year", "draft_overall"], how="left").drop(columns=["draft_year", "draft_overall"])
    has36 = (d.season >= CONTRACT_FIRST) & (d.season <= LAST - 1)   # a 3-6 year window needs signings through 2026
    d["apy_pct36"] = np.where(has36, 100 * d.apy_cap36.fillna(0), np.nan)
    snaps = data.load_snap_counts(range(SNAP_FIRST, LAST + 4))
    d["snap_games"] = np.where(d.season >= SNAP_FIRST, rookie_deal_snaps(snaps, d), np.nan)
    return d


# ------------------------------------------------------------------ the pick-value curve
def scale_av(d: pd.DataFrame) -> pd.DataFrame:
    """Career AV keeps growing, so each class is scaled to the pooled class mean (the 2021 class has five seasons,
    2006 twenty). Done on the analysis sample, after specialists and unresolved positions are dropped."""
    d = d.copy()
    for col in ("w_av", "dr_av"):
        cm = d.groupby("season")[col].transform("mean")
        d[col + "_adj"] = d[col] * d[col].mean() / cm
    return d


def kernel(picks: np.ndarray, grid: np.ndarray, h: float) -> np.ndarray:
    """Gaussian weights in log pick: early picks are close in value only to their neighbours, late picks to a wide band."""
    return np.exp(-0.5 * ((np.log(grid)[:, None] - np.log(picks)[None, :]) / h) ** 2)


def fit_curve(pick, y, h, pmax=262, w=None):
    """Expected outcome at every pick 1..pmax: kernel-smoothed means, then forced to fall (or stay flat) with the pick."""
    pick = np.asarray(pick, int); y = np.asarray(y, float)
    w = np.ones_like(y) if w is None else np.asarray(w, float)
    S = np.bincount(pick, weights=y * w, minlength=pmax + 1)[1:pmax + 1]
    N = np.bincount(pick, weights=w, minlength=pmax + 1)[1:pmax + 1]
    grid = np.arange(1, pmax + 1)
    K = kernel(grid, grid, h)
    sm = (K @ S) / np.maximum(K @ N, 1e-12)
    return IsotonicRegression(increasing=False).fit_transform(grid, sm, sample_weight=np.maximum(K @ N, 1e-9))


def choose_bandwidth(df, ycol, hs=(0.04, 0.06, 0.08, 0.12, 0.18, 0.25, 0.35, 0.5)):
    """Leave one draft class out: fit on the other classes, score squared error on the held-out class."""
    out = {}
    for h in hs:
        err = 0.0
        for s in df.season.unique():
            tr, te = df[df.season != s], df[df.season == s]
            cv = fit_curve(tr.pick, tr[ycol], h)
            err += float(((te[ycol] - cv[te.pick.values - 1]) ** 2).sum())
        out[h] = err / len(df)
    return min(out, key=out.get), out


def round_baseline_mse(df, ycol):
    """The same held-out test for the plain alternative: the mean outcome of the pick's round."""
    err = 0.0
    for s in df.season.unique():
        tr, te = df[df.season != s], df[df.season == s]
        m = tr.groupby("round")[ycol].mean()
        err += float(((te[ycol] - te["round"].map(m)) ** 2).sum())
    return err / len(df)


def equivalent_shift(curve, picks, value, lo=-200, hi=200):
    """How many picks earlier (positive) or later (negative) the same players would have to be taken for the curve to
    expect exactly their mean outcome: solves mean(curve[pick - k]) = value for k, picks clipped to the board.
    Zero surplus gives zero shift, so the convex curve cannot invent a shift (it would if the mean pick were inverted)."""
    picks = np.asarray(picks, int); n = len(curve)
    f = lambda k: curve[np.clip(picks - k, 1, n) - 1].mean()
    if f(hi) <= value:
        return float(hi)
    if f(lo) >= value:
        return float(lo)
    a, b = lo, hi
    for _ in range(40):   # f rises with k (earlier picks expect more); bisect on a continuous k by interpolating the curve
        m = (a + b) / 2
        if _fc(curve, picks, m) < value:
            a = m
        else:
            b = m
    return round((a + b) / 2, 1)


def _fc(curve, picks, k):
    x = np.clip(picks - k, 1, len(curve))
    return float(np.interp(x, np.arange(1, len(curve) + 1), curve).mean())


# ------------------------------------------------------------------ value over the curve
GROUPS = {"R1": [1], "R2": [2], "R3": [3], "R4": [4], "R5": [5], "R6": [6], "R7": [7], "R3-7": [3, 4, 5, 6, 7]}


def cell_ids(df):
    """Index of each pick's position and round group, for fast bootstrap sums."""
    pi = df.pos.map({p: i for i, p in enumerate(POS_ORDER)}).values
    return pi


def surplus_table(df, ycol, h, n_boot=B, seed=10, cluster=None):
    """Mean outcome minus the curve, by position and round group, with a bootstrap that resamples picks and refits
    the curve each time. Returns a long table and the bootstrap draws of the rounds 3-7 surplus by position."""
    df = df.dropna(subset=[ycol]).reset_index(drop=True)
    P = len(POS_ORDER)
    pick = df.pick.values; y = df[ycol].values.astype(float); rd = df["round"].values
    pi = cell_ids(df)
    masks = {g: np.isin(rd, r) for g, r in GROUPS.items()}

    def stats(idx):
        cv = fit_curve(pick[idx], y[idx], h)
        e = cv[pick[idx] - 1]; s = y[idx] - e
        res = {}
        for g, m in masks.items():
            mm = m[idx]
            n = np.bincount(pi[idx][mm], minlength=P)
            res[g] = (np.bincount(pi[idx][mm], weights=s[mm], minlength=P) / np.maximum(n, 1),
                      np.bincount(pi[idx][mm], weights=y[idx][mm], minlength=P) / np.maximum(n, 1),
                      np.bincount(pi[idx][mm], weights=e[mm], minlength=P) / np.maximum(n, 1), n, cv)
        sd = np.array([s[masks["R3-7"][idx] & (pi[idx] == k)].std(ddof=1) if ((masks["R3-7"][idx]) & (pi[idx] == k)).sum() > 2 else np.nan
                       for k in range(P)])
        return res, sd

    base, base_sd = stats(np.arange(len(df)))
    rng = np.random.default_rng(seed)
    draws = {g: [] for g in GROUPS}; draws_rel = {g: [] for g in GROUPS}; draws_eq = []; draws_sharpe = []
    groups = [g.index.values for _, g in df.groupby(cluster)] if cluster else None
    for _ in range(n_boot):
        if groups:   # resample whole draft classes, so anything shared within a class stays together
            idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        else:
            idx = rng.integers(0, len(df), len(df))
        r, sd = stats(idx)
        for g in GROUPS:
            draws[g].append(r[g][0]); draws_rel[g].append(r[g][1] / np.where(r[g][2] > 0, r[g][2], np.nan) - 1)
        cv = r["R3-7"][4]
        draws_eq.append(np.array([equivalent_shift(cv, pick[idx][masks["R3-7"][idx] & (pi[idx] == k)], r["R3-7"][1][k])
                                  if (masks["R3-7"][idx] & (pi[idx] == k)).any() else np.nan for k in range(P)]))
        draws_sharpe.append(r["R3-7"][0] / sd)
    rows = []
    for g in GROUPS:
        D = np.array(draws[g]); Dr = np.array(draws_rel[g])
        mean_s, mean_y, mean_e, n, cv = base[g]
        for k, p in enumerate(POS_ORDER):
            if n[k] == 0:
                continue
            col = D[:, k]
            p2 = 2 * min(np.mean(col <= 0), np.mean(col >= 0))
            rows.append({"outcome": ycol, "round": g, "pos": p, "n": int(n[k]), "mean": round(float(mean_y[k]), 3),
                         "expected": round(float(mean_e[k]), 3), "surplus": round(float(mean_s[k]), 3),
                         "lo": round(float(np.nanpercentile(col, 2.5)), 3), "hi": round(float(np.nanpercentile(col, 97.5)), 3),
                         "rel": round(float(mean_y[k] / mean_e[k] - 1), 3) if mean_e[k] > 0 else np.nan,
                         "rel_lo": round(float(np.nanpercentile(Dr[:, k], 2.5)), 3), "rel_hi": round(float(np.nanpercentile(Dr[:, k], 97.5)), 3),
                         "se": round(float(np.nanstd(col, ddof=1)), 4), "p_boot": round(float(max(p2, 1 / n_boot)), 4)})
    t = pd.DataFrame(rows)
    # rounds 3-7 extras: equivalent pick (how many picks earlier the position's output sits) and the Sharpe ratio
    cv0 = base["R3-7"][4]
    m37 = masks["R3-7"]
    E = np.array(draws_eq); S = np.array(draws_sharpe)
    extra = []
    for k, p in enumerate(POS_ORDER):
        sel = m37 & (pi == k)
        if not sel.any():
            continue
        extra.append({"pos": p, "avg_pick": round(float(pick[sel].mean()), 1),
                      "picks_earlier": equivalent_shift(cv0, pick[sel], base["R3-7"][1][k]),
                      "picks_earlier_lo": round(float(np.nanpercentile(E[:, k], 2.5)), 1), "picks_earlier_hi": round(float(np.nanpercentile(E[:, k], 97.5)), 1),
                      "sharpe": round(float(base["R3-7"][0][k] / base_sd[k]), 3), "sd": round(float(base_sd[k]), 3),
                      "sharpe_lo": round(float(np.nanpercentile(S[:, k], 2.5)), 3), "sharpe_hi": round(float(np.nanpercentile(S[:, k], 97.5)), 3)})
    return t, pd.DataFrame(extra), base["R3-7"][4]


def holm(pvals: dict) -> dict:
    """Holm step-down adjusted p-values (family-wise error across the positions tested)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items); out = {}; run = 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p)); out[k] = run
    return out


def rounds37_title(ineff, money_clear, r37):
    """The one-page chart's title, written from the results whichever way they fall."""
    j = lambda xs: " and ".join(xs) if len(xs) <= 2 else ", ".join(xs[:-1]) + " and " + xs[-1]
    both = [x["pos"] for x in ineff if x["apy_clear"]]
    if both:
        return f"Rounds 3-7: {j(both)} beat or miss their slot on both measures"
    beat_av = [p for p, r in r37.items() if r["av_ci"][0] > 0]
    head = f"Rounds 3-7: {j(beat_av)} beat their slot in career AV" if beat_av else "Rounds 3-7: no position clearly beats its slot in career AV"
    miss = [p for p in money_clear if r37[p]["apy_surplus"] < 0]; beat = [p for p in money_clear if r37[p]["apy_surplus"] > 0]
    if not money_clear:
        return head + "; contract money does not clearly confirm any"
    return head + (f"; in contract money only {j(miss)} clearly {'misses' if len(miss) == 1 else 'miss'}" if miss else "") + \
        (f"; in money only {j(beat)} clearly {'beats' if len(beat) == 1 else 'beat'} it" if beat else "")


def pick_inefficiencies(av37: pd.DataFrame, apy37: pd.DataFrame, k=None) -> list:
    """The rule stated before the results: AV surplus interval clear of zero, second-contract surplus with the same
    sign, ranked by the weaker of the two z-scores. Returns up to k rows; fewer if fewer qualify."""
    a = av37.set_index("pos"); c = apy37.set_index("pos")
    out = []
    for p in a.index.intersection(c.index):
        ra, rc = a.loc[p], c.loc[p]
        if not (ra.lo > 0 or ra.hi < 0):
            continue
        if np.sign(ra.surplus) != np.sign(rc.surplus):
            continue
        za, zc = ra.surplus / ra.se, rc.surplus / rc.se
        out.append({"pos": p, "direction": "drafted too late" if ra.surplus > 0 else "drafted too early",
                    "z_av": round(float(za), 2), "z_apy": round(float(zc), 2), "strength": round(float(min(abs(za), abs(zc))), 2),
                    "apy_clear": bool(rc.lo > 0 or rc.hi < 0)})
    out = sorted(out, key=lambda r: -r["strength"])
    return out[:k] if k else out


def finish_wide(fig, title, subtitle, path, source=SRC):
    """plot.finish for a figure with several panels: the title block sits on the figure, not on one panel."""
    fig.tight_layout(rect=(0, 0.04, 1, 0.84 if "\n" in subtitle else 0.88))
    fig.text(0.01, 0.985, title, fontfamily=plot.DISPLAY, fontweight="bold", fontsize=12.5, color=plot.INK, va="top", ha="left")
    fig.text(0.01, 0.925, subtitle, color=plot.MUTED, fontsize=10, style="italic", va="top", ha="left")
    fig.text(0.01, 0.005, source, color=plot.MUTED, fontsize=8, ha="left", va="bottom")
    fig.text(0.99, 0.005, Path(path).parent.name.split("-")[0], color=plot.ACCENT, fontsize=13, ha="right", va="bottom",
             fontfamily=plot.DISPLAY, fontweight="bold")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ main
def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    d = build()
    n_all = len(d)
    spec = d.pos.eq("ST"); unres = d.pos.isna()
    d_all = d.copy()
    d = scale_av(d[~spec & ~unres])
    find = {"draft_classes": f"{FIRST}-{LAST}", "picks_all": n_all, "picks": len(d), "specialists_dropped": int(spec.sum()),
            "unresolved_dropped": int(unres.sum()), "contract_classes": f"{CONTRACT_FIRST}-{LAST}", "snap_classes": f"{SNAP_FIRST}-{LAST}",
            "second_window": list(SECOND_WINDOW), "real_deal_cap_share": REAL_DEAL, "n_boot": B}
    find["picks_contract"] = int(d.apy_pct.notna().sum()); find["picks_snaps"] = int(d.snap_games.notna().sum())
    find["picks_by_pos"] = d.pos.value_counts().reindex(POS_ORDER).astype(int).to_dict()
    find["picks_r37"] = int(d["round"].between(3, 7).sum())
    find["class_av_scale"] = {int(s): round(float(d.w_av.mean() / v), 2) for s, v in d.groupby("season").w_av.mean().items()}

    # 1. curves (bandwidth chosen out of sample for each outcome)
    outcomes = {"w_av_adj": "Career AV (weighted, class-scaled)", "apy_pct": "Second-contract APY, % of cap",
                "started": "Became a starter", "second": "Earned a second contract (1%+ of cap)",
                "snap_games": "Half-snap games, seasons 1-4", "dr_av_adj": "AV for the drafting team (class-scaled)"}
    H, cvinfo, curves = {}, {}, {}
    for col in outcomes:
        sub = d.dropna(subset=[col])
        h, errs = choose_bandwidth(sub, col)
        H[col] = h
        base_mse = round_baseline_mse(sub, col)
        cvinfo[col] = {"bandwidth": h, "cv_mse": round(errs[h], 4), "round_mean_mse": round(base_mse, 4),
                       "improvement_pct": round(100 * (1 - errs[h] / base_mse), 2)}
        curves[col] = fit_curve(sub.pick, sub[col], h)
    find["curve_cv"] = cvinfo
    cav = curves["w_av_adj"]
    find["curve_av_at"] = {str(p): round(float(cav[p - 1]), 1) for p in (1, 10, 32, 64, 100, 150, 200, 250)}
    find["curve_apy_at"] = {str(p): round(float(curves["apy_pct"][p - 1]), 2) for p in (1, 10, 32, 64, 100, 150, 200, 250)}
    find["curve_start_at"] = {str(p): round(float(curves["started"][p - 1]), 3) for p in (1, 32, 64, 100, 150, 200, 250)}
    find["curve_second_at"] = {str(p): round(float(curves["second"][p - 1]), 3) for p in (1, 32, 64, 100, 150, 200, 250)}
    # where the curve flattens: share of pick 1's expected AV left by pick 32, 100 and 200
    find["av_top5"] = round(float(cav[:5].mean()), 1)   # pick 1 alone is 16 players, so shares are taken of the top-five average
    find["av_share_of_top5"] = {str(p): round(float(cav[p - 1] / cav[:5].mean()), 3) for p in (32, 64, 100, 200)}
    find["av_drop_r1"] = round(float(cav[0] - cav[31]), 1); find["av_drop_r3_7"] = round(float(cav[63] - cav[249]), 1)
    pd.DataFrame({"pick": np.arange(1, 263), **{k: np.round(v, 4) for k, v in curves.items()}}).to_csv(OUT / "pick_value_curve.csv", index=False)

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, col, lab, fmt in ((axs[0], "w_av_adj", "Career AV (class-scaled)", "{:.0f}"), (axs[1], "apy_pct", f"Second-contract APY, % of cap (classes {CONTRACT_FIRST}-{LAST})", "{:.1f}")):
        sub = d.dropna(subset=[col])
        b = sub.assign(bin=(sub.pick - 1) // 8).groupby("bin").agg(p=("pick", "mean"), y=(col, "mean"))
        ax.scatter(b.p, b.y, s=14, color=plot.SOFT, label="Mean of each 8 picks", zorder=2)
        ax.plot(np.arange(1, 263), curves[col], color=plot.ACCENT, lw=2.4, label="Smoothed curve", zorder=3)
        for r in (32, 64, 100, 140, 180, 220):
            ax.axvline(r, color=plot.GRID, lw=1, zorder=1)
        ax.set_xlabel("Overall pick"); ax.set_ylabel(lab); ax.set_xlim(0, 262); ax.set_ylim(bottom=0)
        ax.legend(fontsize=8.5, loc="upper right")
    s1, s2 = find["av_share_of_top5"]["32"], find["av_share_of_top5"]["100"]
    finish_wide(fig, f"The value of a pick falls steeply in round 1 and flattens after",
                f"Pick 32 is worth {100 * s1:.0f}% of a top-five pick in career AV, pick 100 {100 * s2:.0f}%. Drafts {FIRST}-{LAST}, {len(d):,} picks, specialists left out",
                OUT / "pick_value_curve.png")

    # 2. value over the curve by position and round, with bootstrap intervals
    tabs, extras = {}, {}
    for col in ("w_av_adj", "apy_pct", "started", "second", "snap_games", "dr_av_adj"):
        t, ex, _ = surplus_table(d, col, H[col])
        tabs[col] = t; extras[col] = ex
    allt = pd.concat(tabs.values(), ignore_index=True)
    allt.to_csv(OUT / "surplus_by_position_round.csv", index=False)
    pd.concat([e.assign(outcome=k) for k, e in extras.items()]).to_csv(OUT / "rounds_3_7_by_position.csv", index=False)

    # the positions-by-round table, AV surplus (rounds 1-7) and second-contract surplus (rounds 3-7)
    piv = lambda col, val: tabs[col][tabs[col]["round"] != "R3-7"].pivot(index="pos", columns="round", values=val).reindex(POS_ORDER)
    grid_av = piv("w_av_adj", "surplus"); grid_lo = piv("w_av_adj", "lo"); grid_hi = piv("w_av_adj", "hi"); grid_n = piv("w_av_adj", "n")
    grid_apy = piv("apy_pct", "surplus")
    find["grid_av"] = {p: {r: round(float(grid_av.loc[p, r]), 1) for r in grid_av.columns} for p in POS_ORDER}
    find["grid_av_clear"] = {p: {r: bool(grid_lo.loc[p, r] > 0 or grid_hi.loc[p, r] < 0) for r in grid_av.columns} for p in POS_ORDER}
    find["grid_n"] = {p: {r: int(grid_n.loc[p, r]) for r in grid_av.columns} for p in POS_ORDER}
    find["grid_apy"] = {p: {r: round(float(grid_apy.loc[p, r]), 2) for r in grid_apy.columns} for p in POS_ORDER}
    find["grid_cells"] = int(grid_av.notna().sum().sum()); find["grid_cells_clear"] = int(sum(v for p in find["grid_av_clear"].values() for v in p.values()))
    rows37 = ["R3", "R4", "R5", "R6", "R7"]
    find["grid_cells_r37"] = len(POS_ORDER) * len(rows37)
    find["grid_cells_r37_clear"] = int(sum(find["grid_av_clear"][p][r] for p in POS_ORDER for r in rows37))

    fig, ax = plt.subplots(figsize=(9.5, 6.4))
    G = grid_av[["R1", "R2"] + rows37].values
    vmax = np.nanmax(np.abs(G[:, 2:])) if np.isfinite(G[:, 2:]).any() else 1
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("div", [plot.ACCENT2, "#fbfaf6", plot.ACCENT])
    ax.imshow(np.clip(G, -vmax, vmax), cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    for i, p in enumerate(POS_ORDER):
        for j, r in enumerate(["R1", "R2"] + rows37):
            v = grid_av.loc[p, r]; clear = find["grid_av_clear"][p][r]
            ax.text(j, i, f"{v:+.1f}" + ("*" if clear else ""), ha="center", va="center", fontsize=9.5,
                    fontweight="bold" if clear else "normal", color=plot.INK)
    ax.set_xticks(range(7)); ax.set_xticklabels([f"Round {r[1:]}" for r in ["R1", "R2"] + rows37])
    ax.set_yticks(range(len(POS_ORDER))); ax.set_yticklabels(POS_ORDER); ax.grid(False)
    ax.axvline(1.5, color=plot.INK, lw=1.2)
    ax.set_xlabel("Round (rounds 1-2 shown for reference; colour scale set by rounds 3-7)"); ax.set_ylabel("Position group")
    top = tabs["w_av_adj"]; t37 = top[top["round"] == "R3-7"].set_index("pos")
    best = t37.surplus.idxmax(); worst = t37.surplus.idxmin()
    plot.finish(fig, ax, f"Late-round {best}s beat their slot; late-round {worst}s fall short",
                f"Career AV above (green) or below (orange) the pick-value curve, per pick. * = 95% interval clear of zero. Drafts {FIRST}-{LAST}",
                OUT / "surplus_heatmap.png", source=SRC)

    # 3. rounds 3-7 by position: AV, money, hit rates, Sharpe
    def r37(col):
        t = tabs[col]; return t[t["round"] == "R3-7"].set_index("pos").reindex(POS_ORDER)
    av, apy, st, sc2, sn, dr = (r37(c) for c in ("w_av_adj", "apy_pct", "started", "second", "snap_games", "dr_av_adj"))
    ex = extras["w_av_adj"].set_index("pos").reindex(POS_ORDER)
    exa = extras["apy_pct"].set_index("pos").reindex(POS_ORDER)
    pvals = av.p_boot.to_dict(); hp = holm(pvals)
    pvals_c = apy.p_boot.to_dict(); hpc = holm(pvals_c)
    summary = []
    for p in POS_ORDER:
        summary.append({
            "pos": p, "picks": int(av.loc[p, "n"]), "avg_pick": float(ex.loc[p, "avg_pick"]),
            "av_surplus": float(av.loc[p, "surplus"]), "av_ci": [float(av.loc[p, "lo"]), float(av.loc[p, "hi"])],
            "av_rel": float(av.loc[p, "rel"]), "av_rel_ci": [float(av.loc[p, "rel_lo"]), float(av.loc[p, "rel_hi"])],
            "av_p": float(av.loc[p, "p_boot"]), "av_p_holm": round(float(hp[p]), 4),
            "picks_earlier": float(ex.loc[p, "picks_earlier"]), "picks_earlier_ci": [float(ex.loc[p, "picks_earlier_lo"]), float(ex.loc[p, "picks_earlier_hi"])],
            "sharpe": float(ex.loc[p, "sharpe"]), "sharpe_ci": [float(ex.loc[p, "sharpe_lo"]), float(ex.loc[p, "sharpe_hi"])], "av_sd": float(ex.loc[p, "sd"]),
            "apy_picks": int(apy.loc[p, "n"]), "apy_surplus": float(apy.loc[p, "surplus"]), "apy_ci": [float(apy.loc[p, "lo"]), float(apy.loc[p, "hi"])],
            "apy_rel": float(apy.loc[p, "rel"]), "apy_p": float(apy.loc[p, "p_boot"]), "apy_p_holm": round(float(hpc[p]), 4),
            "apy_sharpe": float(exa.loc[p, "sharpe"]),
            "start_rate": float(st.loc[p, "mean"]), "start_expected": float(st.loc[p, "expected"]), "start_over": float(st.loc[p, "surplus"]),
            "start_over_ci": [float(st.loc[p, "lo"]), float(st.loc[p, "hi"])],
            "second_rate": float(sc2.loc[p, "mean"]), "second_expected": float(sc2.loc[p, "expected"]), "second_over": float(sc2.loc[p, "surplus"]),
            "second_over_ci": [float(sc2.loc[p, "lo"]), float(sc2.loc[p, "hi"])],
            "snap_surplus": float(sn.loc[p, "surplus"]), "snap_ci": [float(sn.loc[p, "lo"]), float(sn.loc[p, "hi"])], "snap_picks": int(sn.loc[p, "n"]),
            "dr_surplus": float(dr.loc[p, "surplus"]), "dr_ci": [float(dr.loc[p, "lo"]), float(dr.loc[p, "hi"])],
        })
    S = pd.DataFrame(summary)
    S.drop(columns=[c for c in S.columns if c.endswith("_ci")]).to_csv(OUT / "rounds_3_7_summary.csv", index=False)
    find["r37"] = {r["pos"]: {k: v for k, v in r.items() if k != "pos"} for r in summary}
    find["r37_av_clear"] = [p for p in POS_ORDER if find["r37"][p]["av_ci"][0] > 0 or find["r37"][p]["av_ci"][1] < 0]
    find["r37_av_holm_clear"] = [p for p in POS_ORDER if find["r37"][p]["av_p_holm"] < 0.05]
    find["r37_apy_clear"] = [p for p in POS_ORDER if find["r37"][p]["apy_ci"][0] > 0 or find["r37"][p]["apy_ci"][1] < 0]
    find["r37_apy_holm_clear"] = [p for p in POS_ORDER if find["r37"][p]["apy_p_holm"] < 0.05]
    find["r37_by_av"] = S.sort_values("av_surplus", ascending=False).pos.tolist()
    find["r37_by_sharpe"] = S.sort_values("sharpe", ascending=False).pos.tolist()
    find["r37_by_apy"] = S.sort_values("apy_surplus", ascending=False).pos.tolist()
    find["r37_rank_corr_av_apy"] = round(float(S.av_surplus.rank().corr(S.apy_surplus.rank())), 2)
    nq = S[S.pos != "QB"]
    find["r37_rank_corr_av_apy_no_qb"] = round(float(nq.av_surplus.rank().corr(nq.apy_surplus.rank())), 2)
    nqt = S[~S.pos.isin(["QB", "TE"])]
    find["r37_rank_corr_av_apy_no_qb_te"] = round(float(nqt.av_surplus.rank().corr(nqt.apy_surplus.rank())), 2)
    find["r37_rank_corr_av_snaps"] = round(float(S.av_surplus.rank().corr(S.snap_surplus.rank())), 2)
    find["r37_rank_corr_av_dr"] = round(float(S.av_surplus.rank().corr(S.dr_surplus.rank())), 2)
    find["r37_start_rate_all"] = round(float(d[d["round"].between(3, 7)].started.mean()), 3)
    find["r37_second_rate_all"] = round(float(d[d["round"].between(3, 7)].second.mean()), 3)
    find["r37_av_sd_all"] = round(float(np.std(d[d["round"].between(3, 7)].w_av_adj - cav[d[d["round"].between(3, 7)].pick - 1], ddof=1)), 2)

    # the three clearest inefficiencies, by the rule in the docstring
    passers = pick_inefficiencies(av.reset_index().assign(pos=POS_ORDER), apy.reset_index().assign(pos=POS_ORDER))
    ineff = passers[:3]
    find["rule_passers"] = passers
    find["inefficiencies"] = ineff
    find["inefficiency_rule_n"] = len(passers)
    # if the rule finds fewer than three, the next-strongest single-measure signals are reported as weaker, labeled
    rest = []
    for r in summary:
        if r["pos"] in {x["pos"] for x in ineff}:
            continue
        za = r["av_surplus"] / max(av.loc[r["pos"], "se"], 1e-9); zc = r["apy_surplus"] / max(apy.loc[r["pos"], "se"], 1e-9)
        rest.append({"pos": r["pos"], "z_av": round(float(za), 2), "z_apy": round(float(zc), 2)})
    find["next_signals"] = sorted(rest, key=lambda x: -max(abs(x["z_av"]), abs(x["z_apy"])))[:3]

    # rounds 1-2 for MacKelvie's "safe pick" claim: non-premium positions early
    t12 = tabs["w_av_adj"][tabs["w_av_adj"]["round"].isin(["R1"])].set_index("pos")
    c12 = tabs["apy_pct"][tabs["apy_pct"]["round"].isin(["R1"])].set_index("pos")
    find["r1"] = {p: {"n": int(t12.loc[p, "n"]), "av_surplus": float(t12.loc[p, "surplus"]), "av_ci": [float(t12.loc[p, "lo"]), float(t12.loc[p, "hi"])],
                      "apy_surplus": float(c12.loc[p, "surplus"]), "apy_ci": [float(c12.loc[p, "lo"]), float(c12.loc[p, "hi"])]}
                  for p in POS_ORDER if p in t12.index}

    # clustered OLS check: rounds 3-7 AV surplus on position (no intercept), errors clustered by drafting team
    late = d[d["round"].between(3, 7)].copy()
    late["surplus_av"] = late.w_av_adj - cav[late.pick - 1]
    X = pd.get_dummies(late.pos).reindex(columns=POS_ORDER).astype(float)
    import statsmodels.api as sm
    ok = late.surplus_av.notna()
    g = pd.factorize(late.team[ok])[0]
    mod = sm.OLS(late.surplus_av[ok], X[ok]).fit(cov_type="cluster", cov_kwds={"groups": g})
    find["ols_team_clustered"] = {p: [round(float(mod.params[p]), 2), round(float(mod.conf_int().loc[p, 0]), 2), round(float(mod.conf_int().loc[p, 1]), 2)] for p in POS_ORDER}
    # and with draft-class fixed effects plus pick, so the curve's shape cannot be doing the work
    Xf = pd.concat([X.drop(columns=["WR"]), pd.get_dummies(late.season, prefix="c", drop_first=True).astype(float), np.log(late.pick).rename("log_pick")], axis=1)
    mf = ols(late.w_av_adj, Xf, groups=late.team)
    find["ols_vs_wr_fe"] = {p: [round(float(mf.params[p]), 2), round(float(mf.conf_int().loc[p, 0]), 2), round(float(mf.conf_int().loc[p, 1]), 2)] for p in POS_ORDER if p != "WR"}

    # robustness: rounds 3-7 position surplus on alternative samples and measures
    rob = []
    def add(name, col, sub, h, t=None):
        if t is None:
            t, _, _ = surplus_table(sub, col, h, n_boot=200, seed=11)
        t = t[t["round"] == "R3-7"].set_index("pos")
        row = {"version": name, "picks": int(t.n.sum())}
        for p in POS_ORDER:
            row[p] = round(float(t.loc[p, "rel"]), 3) if p in t.index else np.nan
            row[p + "_clear"] = bool(t.loc[p, "lo"] > 0 or t.loc[p, "hi"] < 0) if p in t.index else False
        rob.append(row)
    add("Career AV, all classes (main)", "w_av_adj", d, H["w_av_adj"], t=tabs["w_av_adj"])
    add(f"Career AV, classes {FIRST}-{OLD_CLASSES} (8+ seasons seen)", "w_av_adj", d[d.season <= OLD_CLASSES], H["w_av_adj"])
    add(f"Career AV, classes {CONTRACT_FIRST}-{LAST} (current rookie wage scale)", "w_av_adj", d[d.season >= CONTRACT_FIRST], H["w_av_adj"])
    d2 = d.assign(w_av_raw=d.w_av)
    add("Career AV, not class-scaled", "w_av_raw", d2, H["w_av_adj"])
    add("AV for the drafting team", "dr_av_adj", d, H["dr_av_adj"])
    add(f"Second-contract APY, % of cap (classes {CONTRACT_FIRST}-{LAST})", "apy_pct", d, H["apy_pct"])
    add("Earned a second contract (1%+ of cap)", "second", d, H["second"])
    add(f"Half-snap games, seasons 1-4 (classes {SNAP_FIRST}-{LAST})", "snap_games", d, H["snap_games"])
    add("Became a starter", "started", d, H["started"])
    add(f"Career AV, classes {FIRST}-{LAST - 3} (2019-2021 left out)", "w_av_adj", d[d.season <= LAST - 3], H["w_av_adj"])
    dl = scale_av(d_all[d_all.pos_label.notna() & (d_all.pos_label != "ST")].assign(pos=lambda x: x.pos_label))
    add("Career AV, positions from the draft label only", "w_av_adj", dl, H["w_av_adj"])
    add(f"Second-contract APY, window 3-6 years (classes {CONTRACT_FIRST}-{LAST - 1})", "apy_pct36", d, H["apy_pct"])
    R = pd.DataFrame(rob); R.to_csv(OUT / "robustness_rounds_3_7.csv", index=False)
    find["robustness"] = R.to_dict(orient="records")
    find["robust_n"] = len(R)
    find["robust_sign_agree"] = {p: int((np.sign(R[p]) == np.sign(R.loc[0, p])).sum()) for p in POS_ORDER}
    find["robust_clear_count"] = {p: int(R[p + "_clear"].sum()) for p in POS_ORDER}

    # the rule itself under three alternatives: how fragile is the list of three?
    def rule_under(sub, apy_col="apy_pct"):
        ta, _, _ = surplus_table(sub, "w_av_adj", H["w_av_adj"], n_boot=300, seed=12)
        tc, _, _ = surplus_table(sub, apy_col, H["apy_pct"], n_boot=300, seed=12)
        pick37 = lambda t: t[t["round"] == "R3-7"].reset_index(drop=True)
        return [(x["pos"], x["direction"]) for x in pick_inefficiencies(pick37(ta), pick37(tc))][:3]
    find["rule_versions"] = {
        "main": [(x["pos"], x["direction"]) for x in ineff],
        f"classes {FIRST}-{LAST - 3}": rule_under(d[d.season <= LAST - 3]),
        "draft label only": rule_under(dl),
        "second contract window 3-6 years": rule_under(d, "apy_pct36"),
    }
    find["label_only_picks"] = int(len(dl)); find["label_only_lb_av_rel"] = float(R.loc[R.version.str.contains("draft label"), "LB"].iloc[0])

    # bootstrap that resamples whole draft classes, as a check on the pick bootstrap
    cb = {}
    for col in ("w_av_adj", "apy_pct"):
        t, _, _ = surplus_table(d, col, H[col], n_boot=500, seed=13, cluster="season")
        t = t[t["round"] == "R3-7"].set_index("pos")
        cb[col] = {p: [float(t.loc[p, "lo"]), float(t.loc[p, "hi"])] for p in POS_ORDER}
    find["class_boot"] = cb
    find["class_boot_av_clear"] = [p for p in POS_ORDER if cb["w_av_adj"][p][0] > 0 or cb["w_av_adj"][p][1] < 0]
    find["class_boot_apy_clear"] = [p for p in POS_ORDER if cb["apy_pct"][p][0] > 0 or cb["apy_pct"][p][1] < 0]

    # 4. the one-page chart a GM can read: rounds 3-7, how many picks earlier each position's output sits, plus money
    fig, axs = plt.subplots(1, 3, figsize=(13, 6.2), sharey=True, gridspec_kw={"width_ratios": [1.25, 1, 1]})
    o = S.sort_values("av_rel").reset_index(drop=True)
    yy = np.arange(len(o))
    ineff_pos = {x["pos"] for x in ineff}
    for ax, val, ci, lab, fmt in ((axs[0], "av_rel", "av_rel_ci", "Career AV vs the slot (%)\nright of zero = drafted too late", "{:+.0%}"),
                                  (axs[1], "apy_surplus", "apy_ci", "Second-contract APY vs slot\n(% of cap a year)", "{:+.2f}"),
                                  (axs[2], "second_over", "second_over_ci", "Second-contract rate vs slot\n(percentage points)", "{:+.0%}")):
        for i, r in o.iterrows():
            lo, hi = find["r37"][r.pos][ci]
            v = r[val]
            col = plot.ACCENT if lo > 0 else plot.ACCENT2 if hi < 0 else plot.SOFT
            ax.plot([lo, hi], [i, i], color=col, lw=2.2, solid_capstyle="round")
            ax.scatter([v], [i], color=col, s=46, zorder=3, edgecolor="white", linewidth=0.8)
        ax.axvline(0, color=plot.INK, lw=1)
        ax.set_xlabel(lab, fontsize=9.5); ax.grid(axis="y", visible=False)
        if val in ("second_over", "av_rel"):
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{100 * x:+.0f}"))
    axs[0].set_yticks(yy); axs[0].set_yticklabels([f"{p}  (n={find['r37'][p]['picks']})" for p in o.pos])
    for t_, p in zip(axs[0].get_yticklabels(), o.pos):
        if p in ineff_pos:
            t_.set_fontweight("bold"); t_.set_color(plot.INK)
    msg = rounds37_title(ineff, find["r37_apy_clear"], find["r37"])
    finish_wide(fig, msg,
                f"Late-round picks at each position vs the average pick at the same slots; 95% intervals, green/orange = clear of zero.\nBold = the three strongest passing the two-measure rule (AV clear, money same sign). AV: drafts {FIRST}-{LAST}; contracts: {CONTRACT_FIRST}-{LAST}",
                OUT / "gm_one_page.png")

    # 5. MacKelvie's risk-return view: mean surplus against its spread
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    from adjustText import adjust_text
    labels = []
    for r in summary:
        ax.scatter(r["av_sd"], r["av_surplus"], s=30 + r["picks"] / 4, color=plot.ACCENT if r["av_surplus"] > 0 else plot.ACCENT2, alpha=0.85, edgecolor="white", zorder=3)
        labels.append(ax.text(r["av_sd"] + 0.08, r["av_surplus"] + 0.12, f"{r['pos']}  ({r['sharpe']:+.2f})", fontsize=9.5))
    adjust_text(labels, ax=ax)
    ax.axhline(0, color=plot.INK, lw=1)
    ax.set_xlabel("Spread of surplus: SD of career AV over the curve, per pick"); ax.set_ylabel("Mean career AV over the curve, per pick")
    sh = S.sort_values("sharpe", ascending=False)
    plot.finish(fig, ax, f"{', '.join(sh.pos.iloc[:3])} return the most for their risk in rounds 3-7; {sh.pos.iloc[-2]} and {sh.pos.iloc[-1]} the least",
                f"Rounds 3-7, drafts {FIRST}-{LAST}. Label = Sharpe ratio (mean surplus / spread). Dot size = picks",
                OUT / "risk_return.png", source=SRC)

    # 6. hit rates over expected
    fig, ax = plt.subplots(figsize=(9, 5.6))
    o2 = S.sort_values("start_over").reset_index(drop=True); w = 0.38
    for i, r in o2.iterrows():
        for off, val, ci, col, lab in ((-w / 2, "start_over", "start_over_ci", plot.ACCENT, "Became a starter"),
                                       (w / 2, "second_over", "second_over_ci", plot.ACCENT2, "Earned a second contract (1%+ of cap)")):
            lo, hi = find["r37"][r.pos][ci]
            ax.barh(i + off, 100 * r[val], w, color=col, alpha=0.9, label=lab if i == 0 else None)
            ax.plot([100 * lo, 100 * hi], [i + off] * 2, color=plot.INK, lw=1)
    ax.set_yticks(range(len(o2))); ax.set_yticklabels(o2.pos); ax.axvline(0, color=plot.INK, lw=1)
    ax.set_xlabel("Percentage points above (right) or below the rate expected at the same picks"); ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8.5, loc="upper left")
    plot.finish(fig, ax, f"Late-round {o2.pos.iloc[-1]}s start most often for their slot; {o2.pos.iloc[0]}s least",
                f"Rounds 3-7. Starter: primary starter for 1+ season (PFR), drafts {FIRST}-{LAST}. Second contract: classes {CONTRACT_FIRST}-{LAST}. Lines = 95% intervals",
                OUT / "hit_rates.png", source=SRC)

    # named examples: the biggest late-round hits at the positions the rule flags, for the reader to check by eye
    find["share_beat_slot"] = {p: round(float((late[late.pos == p].surplus_av > 0).mean()), 3) for p in POS_ORDER}
    find["share_beat_slot_all"] = round(float((late.surplus_av > 0).mean()), 3)
    ex_rows = []
    for x in ineff:
        if x["direction"] != "drafted too late":
            continue
        for _, r in late[late.pos == x["pos"]].nlargest(3, "w_av").iterrows():
            ex_rows.append([x["pos"], r.pfr_player_name, int(r.season), int(r["round"]), int(r.pick), float(r.w_av), int(r.probowls), int(r.allpro)])
    find["examples"] = ex_rows
    late[["season", "round", "pick", "team", "pfr_player_name", "position", "pos", "w_av", "w_av_adj", "surplus_av", "seasons_started", "probowls",
          "allpro", "apy_pct", "second", "snap_games"]].round(3).sort_values(["season", "pick"]).to_csv(OUT / "late_round_picks.csv", index=False)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    with open(OUT / "models.txt", "w") as f:
        f.write(f"=== Rounds 3-7: career AV over the curve on position (no intercept), errors clustered by drafting team\n{mod.summary()}\n\n"
                f"=== Rounds 3-7: class-scaled career AV on position (vs WR), draft-class fixed effects and log pick, clustered by team\n{mf.summary()}\n")
    for k, v in find.items():
        print(k, v)


if __name__ == "__main__":
    main()
