"""13 The Metric Stability Atlas: which team and player numbers can a club trust, and after how much sample?

The question: a club reads dozens of numbers every Monday. Some are mostly signal after a few games, some are
mostly noise after a full season. For a broad set of team metrics (offense, defense, special teams, results)
and player metrics (quarterbacks, receivers, running backs, pass rushers), this study measures:
  (a) split-half reliability within a season: each unit-season's games are split into two halves at random,
      200 times, and the two halves are correlated across units (seasons centred, so league trends do not count
      as signal). The odd vs even week split is reported too. From it comes the regression constant k, the sample
      at which a metric is half signal: reliability(n) = n / (n + k), so after n plays regress k / (n + k) of the
      way to the league mean.
  (b) year-to-year stability: the same unit's full season against its next season.
  (c) prediction: which team metric over the first 8 games best predicts rest-of-season point differential and
      win %, fit on 2006-2015 and tested on 2016-2025; which quarterback metric over Weeks 1-9 predicts his
      EPA per dropback in Weeks 10+; and what a full season predicts about the next one.
Intervals resample whole teams or players (1,000 draws for r; 500 for the split-half r). The regression
constants are also tested out of sample: k is fit on earlier seasons and used to forecast even-week results
from odd-week results in later seasons.

Data (nflverse, pulled on the run date and recorded in findings.json):
  play-by-play 2006-2026 (nflfastR EPA, success, CPOE, xpass, xYAC), FTN charting pressure via nflverse
  participation (2023-2025; the 2016-2022 pressure field comes from a different source and leaves sacks out, so it
  is not used), NFL Next Gen Stats weekly rushing (RYOE, 2018-2025), Pro Football Reference weekly defense
  (pressures and sacks, 2018-2025), snap counts (2018-2025) and players.
Not available, so not measured: yards per route run (no public per-player routes), pass-rush win rate.
Run: python -m projects.metric_stability_atlas
"""
from __future__ import annotations

import datetime as dt
import json
import zlib
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot
from nflan.stats import boot_r

OUT = Path("reports/13-metric-stability-atlas")
SRC = "Data: nflverse play-by-play (nflfastR models) 2006-2025. Chart: Dylan Fanelli"
SRC_ALL = "Data: nflverse play-by-play, FTN charting, NFL Next Gen Stats, PFR, snap counts. Chart: Dylan Fanelli"
FIRST, SPLIT_YEAR = 2006, 2016          # train on 2006-2015, test on 2016-2025
N_SPLITS, N_BOOT_SPLITS, B_SPLIT, B_R = 200, 20, 500, 1000
EARLY_GAMES = 8                          # team prediction: first 8 games vs the rest
QB_EARLY_LAST_WEEK = 9                   # QB prediction: Weeks 1-9 vs Weeks 10+


# =====================================================================================================
# Engine (pure functions; tested on made-up data in tests/test_stability_atlas.py)
# =====================================================================================================
def k_from_r(r: float, n_half: float) -> float:
    """Regression constant from a split-half r measured on halves of n_half: r = n/(n+k) -> k = n(1-r)/r."""
    if not np.isfinite(r) or r <= 0:
        return float("inf")
    return float(n_half * (1 - r) / r)


def reliability(n, k):
    """Share of the observed spread that is signal after n trials: n / (n + k). Zero when k is infinite."""
    n = np.asarray(n, float)
    return np.where(np.isfinite(k), n / (n + k), 0.0) if np.ndim(n) else (float(n / (n + k)) if np.isfinite(k) else 0.0)


def regress_share(n, k):
    """How far to move an observed value toward the league mean after n trials: k / (n + k)."""
    return 1 - reliability(n, k)


def spearman_brown(r: float, m: float = 2.0) -> float:
    """Reliability of a sample m times as long as the one that gave r."""
    if not np.isfinite(r) or r <= 0:
        return 0.0
    return float(m * r / (1 + (m - 1) * r))


def shrink(x, mean, n, k):
    """Regressed estimate: mean + reliability(n) * (x - mean)."""
    return mean + reliability(n, k) * (np.asarray(x, float) - mean)


def center_by_season(v: np.ndarray, season: np.ndarray, valid: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    """Subtract each season's (weighted) mean over valid entries, so a league-wide trend is not counted as signal."""
    out = np.array(v, float)
    w = np.ones(len(v)) if w is None else np.asarray(w, float)
    for s in np.unique(season):
        m = (season == s) & valid
        if m.any() and w[m].sum() > 0:
            out[season == s] = out[season == s] - np.average(out[m], weights=w[m])
    return out


def wcorr(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> float:
    """Weighted Pearson r (a weight of 2 is the same as the row appearing twice)."""
    if w.sum() <= 0:
        return float("nan")
    ma, mb = np.average(a, weights=w), np.average(b, weights=w)
    va, vb = np.average((a - ma) ** 2, weights=w), np.average((b - mb) ** 2, weights=w)
    if va <= 0 or vb <= 0:
        return float("nan")
    return float(np.average((a - ma) * (b - mb), weights=w) / np.sqrt(va * vb))


@dataclass
class Rows:
    """Game-level rows for one metric: value of a half or a season = sum(num)/sum(den) [- sum(num2)/sum(den2)]."""
    key: np.ndarray        # unit-season code (0..K-1)
    week: np.ndarray
    num: np.ndarray
    den: np.ndarray
    num2: np.ndarray
    den2: np.ndarray
    season: np.ndarray     # per key
    cluster: np.ndarray    # per key (team or player), for the bootstrap
    unit: np.ndarray       # per key
    two: bool = False


def make_rows(df: pd.DataFrame, num: str, den: str, num2: str | None = None, den2: str | None = None,
              unit: str = "unit", cluster: str | None = None) -> Rows:
    """df: one row per unit-game with season, week, the unit id and the sums."""
    d = df.sort_values(["season", unit, "week"]).reset_index(drop=True)
    keys = pd.MultiIndex.from_frame(d[["season", unit]])
    code, uniq = pd.factorize(keys)
    meta = pd.DataFrame(list(uniq), columns=["season", unit])
    clus = meta[unit] if cluster is None else d.groupby(code)[cluster].first().values
    z = np.zeros(len(d))
    return Rows(code, d.week.to_numpy(), d[num].to_numpy(float), d[den].to_numpy(float),
                d[num2].to_numpy(float) if num2 else z, d[den2].to_numpy(float) if den2 else z,
                meta.season.to_numpy(), np.asarray(clus), meta[unit].to_numpy(), num2 is not None)


def _value(n, d, n2, d2, two):
    with np.errstate(invalid="ignore", divide="ignore"):
        v = n / d
        if two:
            v = v - n2 / d2
    return v


def _sums(rows: Rows, mask: np.ndarray):
    K = len(rows.season)
    f = lambda a: np.bincount(rows.key[mask], weights=a[mask], minlength=K)
    return f(rows.num), f(rows.den), f(rows.num2), f(rows.den2)


def season_values(rows: Rows, mask: np.ndarray | None = None):
    mask = np.ones(len(rows.key), bool) if mask is None else mask
    n, d, n2, d2 = _sums(rows, mask)
    return _value(n, d, n2, d2, rows.two), d, d2


def random_halves(rows: Rows, rng: np.random.Generator) -> np.ndarray:
    """True for the games in half A: each unit-season's games are shuffled and the first floor(n/2) go to A."""
    order = np.lexsort((rng.random(len(rows.key)), rows.key))
    k_sorted = rows.key[order]
    start = np.r_[0, np.flatnonzero(np.diff(k_sorted)) + 1]
    counts = np.diff(np.r_[start, len(k_sorted)])
    pos = np.arange(len(k_sorted)) - np.repeat(start, counts)
    in_a = pos < np.repeat(counts // 2, counts)
    out = np.empty(len(rows.key), bool)
    out[order] = in_a
    return out


def _halves(rows: Rows, mask_a: np.ndarray, min_half: float):
    a, da, da2 = season_values(rows, mask_a)
    b, db, db2 = season_values(rows, ~mask_a)
    dmin_a = np.minimum(da, da2) if rows.two else da
    dmin_b = np.minimum(db, db2) if rows.two else db
    valid = (dmin_a >= min_half) & (dmin_b >= min_half) & np.isfinite(a) & np.isfinite(b)
    return a, b, valid, (da + db) / 2


def split_half(rows: Rows, min_half: float, rng: np.random.Generator, n_splits: int = N_SPLITS,
               n_boot_splits: int = N_BOOT_SPLITS, b: int = B_SPLIT) -> dict:
    """Mean split-half r over random game splits (seasons centred), the odd/even-week r, the mean half sample,
    and a 95% interval from resampling clusters (teams or players) over a subset of the splits."""
    rs, nh, store = [], [], []
    for s in range(n_splits):
        a, bb, valid, half_n = _halves(rows, random_halves(rows, rng), min_half)
        ac, bc = center_by_season(a, rows.season, valid), center_by_season(bb, rows.season, valid)
        rs.append(wcorr(ac[valid], bc[valid], np.ones(valid.sum())))
        nh.append(float(half_n[valid].mean()))
        if s < n_boot_splits:
            store.append((ac, bc, valid))
    a, bb, valid, half_n = _halves(rows, rows.week % 2 == 1, min_half)
    ac, bc = center_by_season(a, rows.season, valid), center_by_season(bb, rows.season, valid)
    r_oe = wcorr(ac[valid], bc[valid], np.ones(valid.sum()))
    # cluster bootstrap: a cluster drawn twice counts twice (weights), on the stored splits
    cl_code, _ = pd.factorize(rows.cluster)
    C = cl_code.max() + 1
    draws = rng.integers(0, C, (b, C))
    W = np.stack([np.bincount(d_, minlength=C) for d_ in draws])[:, cl_code].astype(float)  # (b, K)
    boot = np.zeros(b)
    for ac_, bc_, v_ in store:
        x, y, w = ac_[v_], bc_[v_], W[:, v_]
        sw = w.sum(1, keepdims=True)
        mx, my = (w * x).sum(1, keepdims=True) / sw, (w * y).sum(1, keepdims=True) / sw
        cov = (w * (x - mx) * (y - my)).sum(1)
        boot += cov / np.sqrt((w * (x - mx) ** 2).sum(1) * (w * (y - my) ** 2).sum(1))
    boot /= len(store)
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    return {"r": float(np.nanmean(rs)), "r_ci": [float(lo), float(hi)], "r_odd_even": float(r_oe),
            "n_half": float(np.mean(nh)), "units": int(valid.sum())}


def yoy(rows: Rows, min_season: float, b: int = B_R, seed: int = 7) -> dict:
    """Full season t vs season t+1 for the same unit, seasons centred, interval resampling clusters."""
    v, d, d2 = season_values(rows)
    dm = np.minimum(d, d2) if rows.two else d
    df = pd.DataFrame({"unit": rows.unit, "season": rows.season, "cl": rows.cluster, "v": v, "ok": dm >= min_season})
    df = df[df.ok & np.isfinite(df.v)].copy()
    df["vc"] = center_by_season(df.v.to_numpy(), df.season.to_numpy(), np.ones(len(df), bool))
    nx = df.assign(season=df.season - 1)[["unit", "season", "vc"]]
    p = df.merge(nx, on=["unit", "season"], suffixes=("", "_next"))
    if len(p) < 10:
        return {"r": float("nan"), "r_ci": [float("nan")] * 2, "pairs": len(p)}
    r, lo, hi = boot_r(p.vc, p.vc_next, groups=p.cl, n=b, seed=seed)
    return {"r": r, "r_ci": [lo, hi], "pairs": int(len(p))}


def oos_r2(x_tr, y_tr, x_te, y_te) -> float:
    """Out-of-sample R^2 of an OLS fit on train, scored on test against the train mean."""
    X = np.column_stack([np.ones(len(y_tr)), np.asarray(x_tr, float).reshape(len(y_tr), -1)])
    beta = np.linalg.lstsq(X, np.asarray(y_tr, float), rcond=None)[0]
    Xt = np.column_stack([np.ones(len(y_te)), np.asarray(x_te, float).reshape(len(y_te), -1)])
    sse = np.sum((np.asarray(y_te) - Xt @ beta) ** 2)
    sst = np.sum((np.asarray(y_te) - np.mean(y_tr)) ** 2)
    return float(1 - sse / sst)


def paired_boot_diff(x1, x2, y, groups, b: int = B_R, seed: int = 7):
    """r(x1, y) - r(x2, y) with a 95% interval resampling whole groups."""
    x1, x2, y = map(lambda a: np.asarray(a, float), (x1, x2, y))
    rng = np.random.default_rng(seed)
    g = pd.Series(np.arange(len(y))).groupby(np.asarray(groups)).apply(lambda s: s.to_numpy())
    mem = list(g.values)
    out = []
    for _ in range(b):
        i = np.concatenate([mem[j] for j in rng.integers(0, len(mem), len(mem))])
        out.append(np.corrcoef(x1[i], y[i])[0, 1] - np.corrcoef(x2[i], y[i])[0, 1])
    d = np.corrcoef(x1, y)[0, 1] - np.corrcoef(x2, y)[0, 1]
    lo, hi = np.percentile(out, [2.5, 97.5])
    return float(d), float(lo), float(hi)


def shrink_test(rows: Rows, k: float, min_half: float, seasons) -> dict:
    """Use k (fit elsewhere) to forecast each unit's even-week value from its odd-week value in the given seasons.
    Returns the MSE of the regressed forecast, the raw odd-week value and the league mean, and the observed slope
    of even on odd against the reliability k implies."""
    a, bb, valid, _ = _halves(rows, rows.week % 2 == 1, min_half)
    _, da, _ = season_values(rows, rows.week % 2 == 1)
    valid = valid & np.isin(rows.season, list(seasons))
    if valid.sum() < 10:
        return {}
    x, y, n, s = a[valid], bb[valid], da[valid], rows.season[valid]
    m = pd.Series(x).groupby(s).transform("mean").to_numpy()          # the league mean known from the odd weeks
    my = pd.Series(y).groupby(s).transform("mean").to_numpy()
    pred = shrink(x, m, n, k)
    rel = reliability(n, k)
    slope = float(np.sum((x - m) * (y - my)) / np.sum((x - m) ** 2))
    return {"mse_shrunk": float(np.mean((y - pred) ** 2)), "mse_raw": float(np.mean((y - x) ** 2)),
            "mse_mean": float(np.mean((y - m) ** 2)), "pred_reliability": float(np.mean(rel)), "obs_slope": slope,
            "units": int(valid.sum())}


# =====================================================================================================
# Data
# =====================================================================================================
COLS = ["season", "season_type", "week", "game_id", "play_id", "posteam", "defteam", "home_team", "away_team", "home_score",
        "away_score", "play_type", "epa", "success", "down", "pass", "rush", "qb_scramble", "yards_gained", "sack", "qb_hit",
        "interception", "fumble_lost", "yardline_100", "fixed_drive", "fixed_drive_result", "third_down_converted",
        "third_down_failed", "pass_oe", "xpass", "wp", "half_seconds_remaining", "qtr", "qb_kneel", "qb_spike",
        "two_point_attempt", "penalty", "penalty_team", "kick_distance", "return_yards", "touchback", "field_goal_attempt",
        "field_goal_result", "punt_blocked", "special_teams_play", "id", "qb_dropback", "qb_epa", "cpoe", "cp", "air_yards",
        "complete_pass", "pass_attempt", "receiver_player_id", "rusher_player_id", "xyac_mean_yardage", "yards_after_catch"]


def load_participation(seasons, refresh: bool = False) -> pd.DataFrame:
    """FTN-charted pressure (nflverse participation). Seasons not posted yet are skipped."""
    frames = []
    for s in seasons:
        try:
            # cached as participation_<season>.parquet: a pbp_ prefix would be read as a play-by-play season
            p = pd.read_parquet(data._fetch(f"{data.BASE}/pbp_participation/pbp_participation_{s}.parquet",
                                            data.DATA_DIR / f"participation_{s}.parquet", refresh))
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue
        frames.append(p[["nflverse_game_id", "play_id", "was_pressure"]].rename(columns={"nflverse_game_id": "game_id"}).assign(season=s))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["game_id", "play_id", "was_pressure", "season"])


def load_pfr_week_def(seasons, refresh_current: int | None = None) -> pd.DataFrame:
    frames = []
    for s in seasons:
        try:
            frames.append(data._release("pfr_advstats", f"advstats_week_def_{s}.parquet", s == refresh_current))
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue
    return pd.concat(frames, ignore_index=True)


def load_ngs_rushing(refresh: bool = False) -> pd.DataFrame:
    return data._release("nextgen_stats", "ngs_rushing.parquet", refresh)


def neutral(p: pd.DataFrame) -> pd.Series:
    """Early downs, win probability 20-80%, not the last two minutes of a half (same filter as study 06)."""
    return (p.down.isin([1, 2]) & p.wp.between(0.2, 0.8) & (p.half_seconds_remaining > 120) & (p.qtr <= 4)
            & (p.qb_kneel != 1) & (p.qb_spike != 1))


def team_tables(p: pd.DataFrame, press: pd.DataFrame):
    """Unit-game sums for every team metric. Returns {metric: DataFrame(season, week, team, num, den[, num2, den2])}."""
    s = p[p.play_type.isin(["run", "pass"]) & p.epa.notna() & p.down.notna() & (p.two_point_attempt != 1)].copy()
    s["db"] = (s["pass"] == 1).astype(float); s["run"] = (s["rush"] == 1).astype(float)
    s["early"] = s.down.isin([1, 2]).astype(float)
    s["expl"] = (((s.run == 1) & (s.yards_gained >= 10)) | ((s.db == 1) & (s.yards_gained >= 20))).astype(float)
    s["hit"] = ((s.sack == 1) | (s.qb_hit == 1)).astype(float)
    s["third"] = (s.down == 3).astype(float)
    s["neutral"] = (neutral(s) & s.pass_oe.notna()).astype(float)
    s["pass_oe0"] = s.pass_oe.fillna(0) * s.neutral
    s = s.merge(press, on=["game_id", "play_id"], how="left")
    s["press_ok"] = ((s.db == 1) & s.was_pressure.notna()).astype(float)
    s["press"] = (s.was_pressure.fillna(False).astype(bool) & (s.press_ok == 1)).astype(float)
    for c in ["epa", "success", "sack", "interception", "fumble_lost", "third_down_converted"]:
        s[c] = s[c].fillna(0).astype(float)
    s["epa_db"] = s.epa * s.db; s["epa_run"] = s.epa * s.run; s["epa_early"] = s.epa * s.early
    s["sack_db"] = s.sack * s.db; s["hit_db"] = s.hit * s.db; s["int_db"] = s.interception * s.db
    s["conv3"] = s.third_down_converted * s.third
    s["one"] = 1.0
    sums = ["one", "epa", "success", "db", "run", "early", "epa_db", "epa_run", "epa_early", "sack_db", "hit_db", "press",
            "press_ok", "expl", "int_db", "fumble_lost", "third", "conv3", "neutral", "pass_oe0"]
    keys = ["season", "week", "game_id"]
    off = s.groupby(keys + ["posteam"])[sums].sum().reset_index().rename(columns={"posteam": "team"})
    de = s.groupby(keys + ["defteam"])[sums].sum().reset_index().rename(columns={"defteam": "team"})
    # red zone: drives with a scrimmage snap at the opponent 20 or closer; TD share
    rz = s[s.yardline_100 <= 20].drop_duplicates(["game_id", "fixed_drive"])
    rz = rz.assign(td=(rz.fixed_drive_result == "Touchdown").astype(float), trip=1.0)
    rz_off = rz.groupby(keys + ["posteam"])[["td", "trip"]].sum().reset_index().rename(columns={"posteam": "team"})
    rz_def = rz.groupby(keys + ["defteam"])[["td", "trip"]].sum().reset_index().rename(columns={"defteam": "team"})
    # penalties: accepted flags on the offense or defense per 100 offensive snaps (no-plays included)
    sn = p[p.play_type.isin(["run", "pass", "no_play"]) & p.down.notna() & p.posteam.notna()].copy()
    sn["pen_off"] = ((sn.penalty == 1) & (sn.penalty_team == sn.posteam)).astype(float) * 100
    sn["pen_def"] = ((sn.penalty == 1) & (sn.penalty_team == sn.defteam)).astype(float) * 100
    sn["snap"] = 1.0
    pen_off = sn.groupby(keys + ["posteam"])[["pen_off", "snap"]].sum().reset_index().rename(columns={"posteam": "team"})
    pen_def = sn.groupby(keys + ["defteam"])[["pen_def", "snap"]].sum().reset_index().rename(columns={"defteam": "team"})
    # special teams: net EPA per kicking play (punts, kickoffs, field goals, extra points), the team's side of each play
    st = p[p.play_type.isin(["kickoff", "punt", "field_goal", "extra_point"]) & p.epa.notna() & p.posteam.notna()]
    st_a = st.groupby(keys + ["posteam"]).epa.agg(["sum", "size"]).reset_index().rename(columns={"posteam": "team"})
    st_b = st.groupby(keys + ["defteam"]).epa.agg(["sum", "size"]).reset_index().rename(columns={"defteam": "team"})
    st_b["sum"] = -st_b["sum"]
    st_t = pd.concat([st_a, st_b]).groupby(keys + ["team"])[["sum", "size"]].sum().reset_index()
    fg = p[(p.field_goal_attempt == 1) & p.posteam.notna()].assign(made=lambda d: (d.field_goal_result == "made").astype(float), att=1.0)
    fg = fg.groupby(keys + ["posteam"])[["made", "att"]].sum().reset_index().rename(columns={"posteam": "team"})
    pu = p[(p.play_type == "punt") & (p.punt_blocked != 1) & p.kick_distance.notna()].copy()
    pu["net"] = pu.kick_distance - pu.return_yards.fillna(0) - 20 * pu.touchback.fillna(0); pu["n"] = 1.0
    pu = pu.groupby(keys + ["posteam"])[["net", "n"]].sum().reset_index().rename(columns={"posteam": "team"})
    # results
    g = p.drop_duplicates("game_id")[["season", "week", "game_id", "home_team", "away_team", "home_score", "away_score"]]
    res = pd.concat([g.assign(team=g.home_team, pd_=g.home_score - g.away_score), g.assign(team=g.away_team, pd_=g.away_score - g.home_score)])
    res["win"] = (res.pd_ > 0) + 0.5 * (res.pd_ == 0); res["one"] = 1.0
    res = res[keys + ["team", "pd_", "win", "one"]]

    T = {}
    for side, d in [("off", off), ("def", de)]:
        T[f"{side}_epa"] = d[keys + ["team"]].assign(num=d.epa, den=d.one)
        T[f"{side}_sr"] = d[keys + ["team"]].assign(num=d.success, den=d.one)
        T[f"{side}_pass_epa"] = d[keys + ["team"]].assign(num=d.epa_db, den=d.db)
        T[f"{side}_rush_epa"] = d[keys + ["team"]].assign(num=d.epa_run, den=d.run)
        T[f"{side}_early_epa"] = d[keys + ["team"]].assign(num=d.epa_early, den=d.early)
        T[f"{side}_sack_rate"] = d[keys + ["team"]].assign(num=d.sack_db, den=d.db)
        T[f"{side}_hit_rate"] = d[keys + ["team"]].assign(num=d.hit_db, den=d.db)
        T[f"{side}_pressure_rate"] = d[d.press_ok > 0][keys + ["team"]].assign(num=d.press, den=d.press_ok)
        T[f"{side}_explosive"] = d[keys + ["team"]].assign(num=d.expl, den=d.one)
        T[f"{side}_int_rate"] = d[keys + ["team"]].assign(num=d.int_db, den=d.db)
        T[f"{side}_fumble_lost_rate"] = d[keys + ["team"]].assign(num=d.fumble_lost, den=d.one)
        T[f"{side}_third_down"] = d[keys + ["team"]].assign(num=d.conv3, den=d.third)
    T["off_proe"] = off[keys + ["team"]].assign(num=off.pass_oe0, den=off.neutral)
    T["off_rz_td"] = rz_off[keys + ["team"]].assign(num=rz_off.td, den=rz_off.trip)
    T["def_rz_td"] = rz_def[keys + ["team"]].assign(num=rz_def.td, den=rz_def.trip)
    T["off_penalty_rate"] = pen_off[keys + ["team"]].assign(num=pen_off.pen_off, den=pen_off.snap)
    T["def_penalty_rate"] = pen_def[keys + ["team"]].assign(num=pen_def.pen_def, den=pen_def.snap)
    T["st_epa"] = st_t[keys + ["team"]].assign(num=st_t["sum"], den=st_t["size"])
    T["st_fg_pct"] = fg[keys + ["team"]].assign(num=fg.made, den=fg.att)
    T["st_net_punt"] = pu[keys + ["team"]].assign(num=pu.net, den=pu.n)
    T["res_point_diff"] = res[keys + ["team"]].assign(num=res.pd_, den=res.one)
    T["res_win_pct"] = res[keys + ["team"]].assign(num=res.win, den=res.one)
    net = off[keys + ["team", "epa", "success", "one"]].merge(de[keys + ["team", "epa", "success", "one"]], on=keys + ["team"], suffixes=("", "_d"))
    T["net_epa"] = net[keys + ["team"]].assign(num=net.epa, den=net.one, num2=net.epa_d, den2=net.one_d)
    T["net_sr"] = net[keys + ["team"]].assign(num=net.success, den=net.one, num2=net.success_d, den2=net.one_d)
    return T


@dataclass
class Spec:
    name: str
    label: str
    group: str
    unit: str            # what one trial is (plays, dropbacks, ...)
    min_half: float
    min_season: float
    first: int = FIRST
    fmt: str = "{:.3f}"
    scale: float = 1.0   # display scale (rates in %)
    higher_better: bool = True


TEAM_SPECS = [
    Spec("off_epa", "Offense EPA/play", "Offense", "plays", 50, 300),
    Spec("off_sr", "Offense success rate", "Offense", "plays", 50, 300, scale=100),
    Spec("off_pass_epa", "Offense EPA/dropback", "Offense", "dropbacks", 30, 200),
    Spec("off_rush_epa", "Offense EPA/designed run", "Offense", "runs", 30, 150),
    Spec("off_early_epa", "Offense early-down EPA/play", "Offense", "early-down plays", 30, 200),
    Spec("off_explosive", "Offense explosive play rate", "Offense", "plays", 50, 300, scale=100),
    Spec("off_sack_rate", "Sack rate allowed", "Offense", "dropbacks", 30, 200, scale=100, higher_better=False),
    Spec("off_hit_rate", "Sack-or-hit rate allowed", "Offense", "dropbacks", 30, 200, scale=100, higher_better=False),
    Spec("off_pressure_rate", "Pressure rate allowed (FTN)", "Offense", "dropbacks", 30, 200, first=2023, scale=100, higher_better=False),
    Spec("off_int_rate", "Interception rate thrown", "Offense", "dropbacks", 30, 200, scale=100, higher_better=False),
    Spec("off_fumble_lost_rate", "Fumbles lost per play", "Offense", "plays", 50, 300, scale=100, higher_better=False),
    Spec("off_rz_td", "Red-zone TD rate", "Offense", "red-zone trips", 4, 20, scale=100),
    Spec("off_third_down", "Third-down conversion rate", "Offense", "third downs", 15, 80, scale=100),
    Spec("off_proe", "Pass rate over expected (neutral)", "Offense", "neutral plays", 30, 150),
    Spec("off_penalty_rate", "Offensive penalties per 100 snaps", "Offense", "snaps", 50, 300, higher_better=False),
    Spec("def_epa", "Defense EPA/play allowed", "Defense", "plays", 50, 300, higher_better=False),
    Spec("def_sr", "Defense success rate allowed", "Defense", "plays", 50, 300, scale=100, higher_better=False),
    Spec("def_pass_epa", "Defense EPA/dropback allowed", "Defense", "dropbacks", 30, 200, higher_better=False),
    Spec("def_rush_epa", "Defense EPA/designed run allowed", "Defense", "runs", 30, 150, higher_better=False),
    Spec("def_early_epa", "Defense early-down EPA allowed", "Defense", "early-down plays", 30, 200, higher_better=False),
    Spec("def_explosive", "Explosive plays allowed", "Defense", "plays", 50, 300, scale=100, higher_better=False),
    Spec("def_sack_rate", "Defense sack rate", "Defense", "dropbacks", 30, 200, scale=100),
    Spec("def_hit_rate", "Defense sack-or-hit rate", "Defense", "dropbacks", 30, 200, scale=100),
    Spec("def_pressure_rate", "Defense pressure rate (FTN)", "Defense", "dropbacks", 30, 200, first=2023, scale=100),
    Spec("def_int_rate", "Interceptions per dropback", "Defense", "dropbacks", 30, 200, scale=100),
    Spec("def_fumble_lost_rate", "Fumbles recovered per play", "Defense", "plays", 50, 300, scale=100),
    Spec("def_rz_td", "Red-zone TD rate allowed", "Defense", "red-zone trips", 4, 20, scale=100, higher_better=False),
    Spec("def_third_down", "Third-down rate allowed", "Defense", "third downs", 15, 80, scale=100, higher_better=False),
    Spec("def_penalty_rate", "Defensive penalties per 100 snaps", "Defense", "snaps", 50, 300, higher_better=False),
    Spec("st_epa", "Special teams net EPA/kick play", "Special teams", "kick plays", 15, 80),
    Spec("st_fg_pct", "Field goal rate", "Special teams", "attempts", 5, 15, scale=100),
    Spec("st_net_punt", "Net punt yards", "Special teams", "punts", 8, 30, fmt="{:.1f}"),
    Spec("net_epa", "Net EPA/play (offense minus defense)", "Team", "plays", 50, 300),
    Spec("net_sr", "Net success rate", "Team", "plays", 50, 300, scale=100),
    Spec("res_point_diff", "Point differential per game", "Team", "games", 4, 12, fmt="{:.1f}"),
    Spec("res_win_pct", "Win %", "Team", "games", 4, 12, scale=100),
]


def player_tables(p: pd.DataFrame, pos: pd.DataFrame, last: int):
    """Unit-game sums for player metrics from play-by-play. pos: gsis_id -> position."""
    keys = ["season", "week", "game_id"]
    T = {}
    s = p[p.play_type.isin(["run", "pass"]) & p.epa.notna() & p.down.notna() & (p.two_point_attempt != 1)]
    # quarterbacks: every dropback (passes, sacks, scrambles) credited to the dropback QB
    q = s[(s.qb_dropback == 1) & s["id"].notna()].copy()
    q["one"] = 1.0; q["att"] = (q.pass_attempt == 1) & (q.sack != 1)
    q["cp_ok"] = (q.att & q.cpoe.notna()).astype(float); q["cpoe0"] = q.cpoe.fillna(0) * q.cp_ok
    q["ay_ok"] = (q.att & q.air_yards.notna()).astype(float); q["ay0"] = q.air_yards.fillna(0) * q.ay_ok
    q["att"] = q.att.astype(float); q["int0"] = q.interception.fillna(0) * q.att
    q["qb_epa0"] = q.qb_epa.fillna(q.epa); q["succ"] = q.success.fillna(0); q["sack0"] = q.sack.fillna(0)
    qg = q.groupby(keys + ["id"])[["one", "qb_epa0", "succ", "sack0", "att", "int0", "cp_ok", "cpoe0", "ay_ok", "ay0"]].sum().reset_index().rename(columns={"id": "unit"})
    T["qb_epa"] = qg[keys + ["unit"]].assign(num=qg.qb_epa0, den=qg.one)
    T["qb_sr"] = qg[keys + ["unit"]].assign(num=qg.succ, den=qg.one)
    T["qb_cpoe"] = qg[keys + ["unit"]].assign(num=qg.cpoe0, den=qg.cp_ok)
    T["qb_sack_rate"] = qg[keys + ["unit"]].assign(num=qg.sack0, den=qg.one)
    T["qb_int_rate"] = qg[keys + ["unit"]].assign(num=qg.int0, den=qg.att)
    T["qb_adot"] = qg[keys + ["unit"]].assign(num=qg.ay0, den=qg.ay_ok)
    # receivers (WR and TE): targets and the team's targets in the games he was targeted
    t = s[(s.pass_attempt == 1) & (s.sack != 1) & s.receiver_player_id.notna()].copy()
    team_t = t.groupby(keys + ["posteam"]).size().rename("team_tgt").reset_index()
    t["one"] = 1.0; t["yds"] = t.yards_gained.fillna(0); t["ay_ok"] = t.air_yards.notna().astype(float); t["ay0"] = t.air_yards.fillna(0)
    t["cp_ok"] = t.cp.notna().astype(float); t["croe0"] = (t.complete_pass - t.cp.fillna(0)) * t.cp_ok
    c_ = (t.complete_pass == 1) & t.xyac_mean_yardage.notna() & t.yards_after_catch.notna()
    t["xyac_ok"] = c_.astype(float); t["yacoe0"] = (t.yards_after_catch.fillna(0) - t.xyac_mean_yardage.fillna(0)) * t.xyac_ok
    rg = t.groupby(keys + ["posteam", "receiver_player_id"])[["one", "epa", "yds", "ay_ok", "ay0", "cp_ok", "croe0", "xyac_ok", "yacoe0"]].sum().reset_index()
    rg = rg.merge(team_t, on=keys + ["posteam"]).rename(columns={"receiver_player_id": "unit"})
    rg = rg[rg.unit.map(pos).isin(["WR", "TE"])]
    qual = rg.groupby(["season", "unit"]).one.transform("sum") >= 50   # same population as the per-target numbers: 50+ targets
    T["wr_tgt_share"] = rg[qual][keys + ["unit"]].assign(num=rg.one, den=rg.team_tgt)
    T["wr_epa_tgt"] = rg[keys + ["unit"]].assign(num=rg.epa, den=rg.one)
    T["wr_ypt"] = rg[keys + ["unit"]].assign(num=rg.yds, den=rg.one)
    T["wr_adot"] = rg[keys + ["unit"]].assign(num=rg.ay0, den=rg.ay_ok)
    T["wr_croe"] = rg[keys + ["unit"]].assign(num=rg.croe0, den=rg.cp_ok)
    T["wr_yacoe"] = rg[keys + ["unit"]].assign(num=rg.yacoe0, den=rg.xyac_ok)
    # running backs: designed runs
    r = s[(s["rush"] == 1) & (s.qb_scramble != 1) & s.rusher_player_id.notna()].copy()
    r["one"] = 1.0; r["yds"] = r.yards_gained.fillna(0); r["ex"] = (r.yards_gained >= 10).astype(float); r["succ"] = r.success.fillna(0)
    rr = r.groupby(keys + ["rusher_player_id"])[["one", "epa", "succ", "yds", "ex"]].sum().reset_index().rename(columns={"rusher_player_id": "unit"})
    rr = rr[rr.unit.map(pos) == "RB"]
    T["rb_sr"] = rr[keys + ["unit"]].assign(num=rr.succ, den=rr.one)
    T["rb_epa"] = rr[keys + ["unit"]].assign(num=rr.epa, den=rr.one)
    T["rb_ypc"] = rr[keys + ["unit"]].assign(num=rr.yds, den=rr.one)
    T["rb_explosive"] = rr[keys + ["unit"]].assign(num=rr.ex, den=rr.one)
    return T


def ngs_and_pfr_tables(last: int):
    """RYOE per carry (NGS weekly rows) and pass-rusher pressure and sack rates (PFR weekly, per defensive snap)."""
    T = {}
    n = load_ngs_rushing()
    n = n[(n.week > 0) & (n.season_type == "REG") & (n.season >= 2018) & (n.season < last) & n.rush_yards_over_expected.notna()]
    n = n.assign(game_id=n.season.astype(str) + "_" + n.week.astype(str) + "_" + n.player_gsis_id.astype(str))
    T["rb_ryoe"] = n[["season", "week", "game_id"]].assign(unit=n.player_gsis_id, num=n.rush_yards_over_expected, den=n.rush_attempts.astype(float))
    w = load_pfr_week_def(range(2018, last))
    w = w[w.game_type == "REG"]
    sc = data.load_snap_counts(range(2018, last))
    sc = sc[(sc.game_type == "REG") & (sc.defense_snaps > 0)]
    pl = data.load_players()[["pfr_id", "position"]].dropna().drop_duplicates("pfr_id")
    edge = set(pl[pl.position.isin(["DE", "DT", "NT", "DL", "OLB"])].pfr_id)
    sc = sc[sc.position.isin(["DE", "DT", "NT", "DL"]) | sc.pfr_player_id.isin(edge)]
    m = sc.merge(w[["pfr_game_id", "pfr_player_id", "def_pressures", "def_sacks"]], on=["pfr_game_id", "pfr_player_id"], how="left")
    m["pr"] = m.def_pressures.fillna(0) * 100; m["sk"] = m.def_sacks.fillna(0) * 100; m["snaps"] = m.defense_snaps.astype(float)
    m = m.rename(columns={"pfr_player_id": "unit"})
    T["pr_pressure_rate"] = m[["season", "week", "game_id", "unit"]].assign(num=m.pr, den=m.snaps)
    T["pr_sack_rate"] = m[["season", "week", "game_id", "unit"]].assign(num=m.sk, den=m.snaps)
    return T


PLAYER_SPECS = [
    Spec("qb_epa", "QB EPA/dropback", "Quarterback", "dropbacks", 75, 200),
    Spec("qb_sr", "QB success rate", "Quarterback", "dropbacks", 75, 200, scale=100),
    Spec("qb_cpoe", "QB CPOE", "Quarterback", "attempts", 60, 150, fmt="{:.1f}"),
    Spec("qb_sack_rate", "QB sack rate", "Quarterback", "dropbacks", 75, 200, scale=100, higher_better=False),
    Spec("qb_int_rate", "QB interception rate", "Quarterback", "attempts", 60, 150, scale=100, higher_better=False),
    Spec("qb_adot", "QB aDOT", "Quarterback", "attempts", 60, 150, fmt="{:.1f}"),
    Spec("wr_tgt_share", "Receiver target share", "Receiver (WR/TE)", "team targets", 100, 250, scale=100),
    Spec("wr_epa_tgt", "Receiver EPA/target", "Receiver (WR/TE)", "targets", 20, 50),
    Spec("wr_ypt", "Receiver yards/target", "Receiver (WR/TE)", "targets", 20, 50, fmt="{:.1f}"),
    Spec("wr_adot", "Receiver aDOT", "Receiver (WR/TE)", "targets", 20, 50, fmt="{:.1f}"),
    Spec("wr_croe", "Receiver catch rate over expected", "Receiver (WR/TE)", "targets", 20, 50, scale=100),
    Spec("wr_yacoe", "Receiver YAC over expected/catch", "Receiver (WR/TE)", "catches", 15, 35, fmt="{:.2f}"),
    Spec("rb_sr", "Rusher success rate", "Running back", "carries", 40, 100, scale=100),
    Spec("rb_epa", "Rusher EPA/carry", "Running back", "carries", 40, 100),
    Spec("rb_ypc", "Rusher yards/carry", "Running back", "carries", 40, 100, fmt="{:.2f}"),
    Spec("rb_explosive", "Rusher 10+ yard run rate", "Running back", "carries", 40, 100, scale=100),
    Spec("rb_ryoe", "Rusher RYOE/carry (NGS)", "Running back", "carries", 40, 100, first=2018, fmt="{:.2f}"),
    Spec("pr_pressure_rate", "Pass rusher pressures per 100 snaps (PFR)", "Pass rusher", "defensive snaps", 120, 300, first=2018, fmt="{:.2f}"),
    Spec("pr_sack_rate", "Pass rusher sacks per 100 snaps (PFR)", "Pass rusher", "defensive snaps", 120, 300, first=2018, fmt="{:.2f}"),
]


def per_game_volume(df: pd.DataFrame, spec: Spec, unit: str) -> float:
    """Typical trials per game for a qualifying unit (median of unit-season mean per game)."""
    g = df.groupby(["season", unit]).agg(den=("den", "sum"), games=("den", "size"))
    g = g[g.den >= spec.min_season]
    return float((g.den / g.games).median())


# =====================================================================================================
# Study
# =====================================================================================================
def atlas_row(spec: Spec, df: pd.DataFrame, unit: str, last: int) -> dict:
    rng = np.random.default_rng(zlib.crc32(spec.name.encode()))   # each metric has its own stream, so results do not depend on order
    df = df[(df.season >= spec.first) & (df.season < last) & (df.den > 0)]
    if "num2" in df:
        df = df[df.den2 > 0]
    rows = make_rows(df, "num", "den", "num2" if "num2" in df else None, "den2" if "den2" in df else None, unit=unit)
    sh = split_half(rows, spec.min_half, rng)
    k = k_from_r(sh["r"], sh["n_half"])
    k_lo, k_hi = k_from_r(sh["r_ci"][1], sh["n_half"]), k_from_r(sh["r_ci"][0], sh["n_half"])
    vpg = per_game_volume(df, spec, unit)
    season_n = vpg * 17
    y = yoy(rows, spec.min_season)
    # out of sample: k from the earlier seasons, used to forecast even weeks from odd weeks in the later ones
    seasons = sorted(set(rows.season))
    cut = SPLIT_YEAR if spec.first < SPLIT_YEAR - 4 else seasons[len(seasons) // 2 + (len(seasons) % 2)]
    tr = df[df.season < cut]; te_seasons = [s for s in seasons if s >= cut]
    rows_tr = make_rows(tr, "num", "den", "num2" if "num2" in tr else None, "den2" if "den2" in tr else None, unit=unit)
    sh_tr = split_half(rows_tr, spec.min_half, rng, n_splits=50, n_boot_splits=2, b=20)
    k_tr = k_from_r(sh_tr["r"], sh_tr["n_half"])
    st = shrink_test(rows, k_tr, spec.min_half, te_seasons)
    return {"metric": spec.name, "label": spec.label, "group": spec.group, "unit": spec.unit, "min_season": spec.min_season, "min_half": spec.min_half,
            "seasons": f"{spec.first}-{last - 1}", "unit_seasons": sh["units"],
            "split_half_r": round(sh["r"], 3), "split_half_ci": [round(x, 3) for x in sh["r_ci"]],
            "odd_even_r": round(sh["r_odd_even"], 3), "half_sample": round(sh["n_half"], 1),
            "k": round(k, 1) if np.isfinite(k) else None, "k_ci": [round(k_lo, 1) if np.isfinite(k_lo) else None, round(k_hi, 1) if np.isfinite(k_hi) else None],
            "per_game": round(vpg, 2), "k_games": round(k / vpg, 1) if np.isfinite(k) else None,
            "k_games_ci": [round(k_lo / vpg, 1) if np.isfinite(k_lo) else None, round(k_hi / vpg, 1) if np.isfinite(k_hi) else None],
            "rel_full_season": round(float(reliability(season_n, k)), 3),
            "regress_4": round(float(regress_share(4 * vpg, k)), 3), "regress_8": round(float(regress_share(8 * vpg, k)), 3),
            "regress_17": round(float(regress_share(season_n, k)), 3),
            "yoy_r": round(y["r"], 3), "yoy_ci": [round(x, 3) for x in y["r_ci"]], "yoy_pairs": y["pairs"],
            "oos_train": f"{spec.first}-{cut - 1}", "oos_test": f"{cut}-{last - 1}", "k_train": round(k_tr, 1) if np.isfinite(k_tr) else None,
            **{f"oos_{a}": (round(b, 6) if isinstance(b, float) else b) for a, b in st.items()},
            "scale": spec.scale}


def team_prediction(T: dict, last: int) -> tuple[dict, pd.DataFrame]:
    """First 8 games of each metric vs rest-of-season point differential per game and win %."""
    pdg = T["res_point_diff"]; wn = T["res_win_pct"]
    pdg = pdg[(pdg.season >= FIRST) & (pdg.season < last)].sort_values(["season", "team", "week"])
    pdg["g"] = pdg.groupby(["season", "team"]).cumcount()
    order = pdg[["season", "team", "game_id", "g"]]
    wn = wn.merge(order, on=["season", "team", "game_id"])
    rest = pdg[pdg.g >= EARLY_GAMES].groupby(["season", "team"]).agg(rest_pd=("num", "mean"))
    rest["rest_win"] = wn[wn.g >= EARLY_GAMES].groupby(["season", "team"]).num.mean()
    out = {}
    base = None
    tab = rest.copy()
    for spec in TEAM_SPECS:
        if spec.first > FIRST:
            continue
        d = T[spec.name].merge(order, on=["season", "team", "game_id"])
        e = d[d.g < EARLY_GAMES].groupby(["season", "team"])[[c for c in ["num", "den", "num2", "den2"] if c in d]].sum()
        val = e.num / e.den - (e.num2 / e.den2 if "num2" in e else 0)
        tab[spec.name] = val
    tab = tab.dropna().reset_index()
    for c in [s.name for s in TEAM_SPECS if s.name in tab]:
        tab[c + "_c"] = center_by_season(tab[c].to_numpy(), tab.season.to_numpy(), np.ones(len(tab), bool))
    tr, te = tab[tab.season < SPLIT_YEAR], tab[tab.season >= SPLIT_YEAR]
    for spec in TEAM_SPECS:
        c = spec.name
        if c not in tab:
            continue
        sign = 1 if spec.higher_better else -1
        r, lo, hi = boot_r(sign * tab[c + "_c"], tab.rest_pd, groups=tab.team, n=B_R, seed=11)
        rw = float(np.corrcoef(sign * tab[c + "_c"], tab.rest_win)[0, 1])
        d_, dlo, dhi = paired_boot_diff(sign * tab[c + "_c"], tab.res_point_diff_c, tab.rest_pd, tab.team, b=B_R, seed=11)
        out[c] = {"r_rest_pd": round(r, 3), "r_rest_pd_ci": [round(lo, 3), round(hi, 3)], "r_rest_win": round(rw, 3),
                  "minus_point_diff": [round(d_, 3), round(dlo, 3), round(dhi, 3)],
                  "oos_r2": round(oos_r2(tr[c + "_c"], tr.rest_pd, te[c + "_c"], te.rest_pd), 3),
                  "oos_r2_with_pd": round(oos_r2(tr[[c + "_c", "res_point_diff_c"]], tr.rest_pd, te[[c + "_c", "res_point_diff_c"]], te.rest_pd), 3)}
    out["_n"] = len(tab); out["_train"] = f"{FIRST}-{SPLIT_YEAR - 1}"; out["_test"] = f"{SPLIT_YEAR}-{last - 1}"
    out["_oos_r2_pd_alone"] = round(oos_r2(tr.res_point_diff_c, tr.rest_pd, te.res_point_diff_c, te.rest_pd), 3)
    trio = ["res_point_diff_c", "net_epa_c", "net_sr_c"]
    out["_oos_r2_pd_epa_sr"] = round(oos_r2(tr[trio], tr.rest_pd, te[trio], te.rest_pd), 3)
    out["_oos_r2_pd_epa"] = round(oos_r2(tr[trio[:2]], tr.rest_pd, te[trio[:2]], te.rest_pd), 3)
    return out, tab


def week_curve(T: dict, last: int, names) -> dict:
    """r between each metric through game g and point differential per game over the rest of the season."""
    pdg = T["res_point_diff"]
    pdg = pdg[(pdg.season >= FIRST) & (pdg.season < last)].sort_values(["season", "team", "week"])
    pdg["g"] = pdg.groupby(["season", "team"]).cumcount()
    order = pdg[["season", "team", "game_id", "g"]]
    out = {}
    for nm in names:
        d = T[nm].merge(order, on=["season", "team", "game_id"])
        sign = 1 if next(s for s in TEAM_SPECS if s.name == nm).higher_better else -1
        out[nm] = []
        for g in range(1, 13):
            e = d[d.g < g].groupby(["season", "team"])[[c for c in ["num", "den", "num2", "den2"] if c in d]].sum()
            v = (e.num / e.den - (e.num2 / e.den2 if "num2" in e else 0)).rename("v")
            y = pdg[pdg.g >= g].groupby(["season", "team"]).num.mean().rename("y")
            j = pd.concat([v, y], axis=1).dropna().reset_index()
            j["vc"] = center_by_season(j.v.to_numpy(), j.season.to_numpy(), np.ones(len(j), bool))
            r, lo, hi = boot_r(sign * j.vc, j.y, groups=j.team, n=300, seed=g)
            out[nm].append([g, round(r, 3), round(lo, 3), round(hi, 3)])
    return out


def next_season(T: dict, last: int) -> dict:
    """Full-season metric (seasons centred) vs next season's point differential per game."""
    pdg = T["res_point_diff"]
    pdg = pdg[(pdg.season >= FIRST) & (pdg.season < last)]
    nx = pdg.groupby(["season", "team"]).num.mean().rename("pd_next").reset_index().assign(season=lambda d: d.season - 1)
    out = {}
    for spec in TEAM_SPECS:
        if spec.first > FIRST:
            continue
        d = T[spec.name]; d = d[(d.season >= FIRST) & (d.season < last - 1)]
        e = d.groupby(["season", "team"])[[c for c in ["num", "den", "num2", "den2"] if c in d]].sum()
        v = (e.num / e.den - (e.num2 / e.den2 if "num2" in e else 0)).rename("v").reset_index().merge(nx, on=["season", "team"])
        v["vc"] = center_by_season(v.v.to_numpy(), v.season.to_numpy(), np.ones(len(v), bool))
        sign = 1 if spec.higher_better else -1
        r, lo, hi = boot_r(sign * v.vc, v.pd_next, groups=v.team, n=B_R, seed=5)
        out[spec.name] = [round(r, 3), round(lo, 3), round(hi, 3)]
    out["_pairs"] = int(len(v))
    return out


def qb_prediction(P: dict, last: int) -> dict:
    """Weeks 1-9 QB metrics vs EPA per dropback in Weeks 10+ (150+ dropbacks in each part)."""
    names = ["qb_epa", "qb_cpoe", "qb_sr", "qb_sack_rate", "qb_int_rate", "qb_adot"]
    parts = {}
    for nm in names:
        d = P[nm]; d = d[(d.season >= FIRST) & (d.season < last)]
        e = d[d.week <= QB_EARLY_LAST_WEEK].groupby(["season", "unit"])[["num", "den"]].sum()
        parts[nm] = (e.num / e.den).rename(nm)
    db = P["qb_epa"]; db = db[(db.season >= FIRST) & (db.season < last)]
    early_n = db[db.week <= QB_EARLY_LAST_WEEK].groupby(["season", "unit"]).den.sum().rename("n_early")
    late = db[db.week > QB_EARLY_LAST_WEEK].groupby(["season", "unit"])[["num", "den"]].sum()
    late = (late.num / late.den).rename("rest_epa").to_frame().assign(n_late=late.den)
    j = pd.concat([pd.DataFrame(parts), early_n, late], axis=1).dropna()
    j = j[(j.n_early >= 150) & (j.n_late >= 150)].reset_index()
    for nm in names:
        j[nm + "_c"] = center_by_season(j[nm].to_numpy(), j.season.to_numpy(), np.ones(len(j), bool))
    j["rest_c"] = center_by_season(j.rest_epa.to_numpy(), j.season.to_numpy(), np.ones(len(j), bool))
    tr, te = j[j.season < SPLIT_YEAR], j[j.season >= SPLIT_YEAR]
    out = {"n": int(len(j)), "qbs": int(j.unit.nunique())}
    for nm in names:
        sign = -1 if nm in ("qb_sack_rate", "qb_int_rate") else 1
        r, lo, hi = boot_r(sign * j[nm + "_c"], j.rest_c, groups=j.unit, n=B_R, seed=3)
        out[nm] = {"r": round(r, 3), "ci": [round(lo, 3), round(hi, 3)], "oos_r2": round(oos_r2(tr[nm + "_c"], tr.rest_c, te[nm + "_c"], te.rest_c), 3)}
    out["oos_r2_epa_cpoe"] = round(oos_r2(tr[["qb_epa_c", "qb_cpoe_c"]], tr.rest_c, te[["qb_epa_c", "qb_cpoe_c"]], te.rest_c), 3)
    out["oos_r2_epa_cpoe_sr"] = round(oos_r2(tr[["qb_epa_c", "qb_cpoe_c", "qb_sr_c"]], tr.rest_c, te[["qb_epa_c", "qb_cpoe_c", "qb_sr_c"]], te.rest_c), 3)
    d_, lo, hi = paired_boot_diff(j.qb_cpoe_c, j.qb_epa_c, j.rest_c, j.unit, b=B_R, seed=3)
    out["cpoe_minus_epa"] = [round(d_, 3), round(lo, 3), round(hi, 3)]
    return out


def current_season_table(T: dict, atlas: dict, cur: int) -> pd.DataFrame:
    """The season in progress: raw and regressed offense, defense and net EPA per play, using each metric's k."""
    rows = []
    for nm in ["off_epa", "def_epa", "net_epa", "res_point_diff"]:
        d = T[nm]; d = d[d.season == cur]
        e = d.groupby("team")[[c for c in ["num", "den", "num2", "den2"] if c in d]].sum()
        raw = e.num / e.den - (e.num2 / e.den2 if "num2" in e else 0)
        n = e.den if "den2" not in e else np.minimum(e.den, e.den2)
        k = atlas[nm]["k"] or np.inf
        m = float(raw.mean())
        reg = shrink(raw.to_numpy(), m, n.to_numpy(), k)
        rows.append(pd.DataFrame({"team": raw.index, "metric": nm, "raw": raw.to_numpy(), "sample": n.to_numpy(),
                                  "regress_share": regress_share(n.to_numpy(), k), "regressed": reg}))
    out = pd.concat(rows)
    w = out.pivot(index="team", columns="metric", values=["raw", "regressed", "regress_share", "sample"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    return w.reset_index()


def pull_info(paths) -> dict:
    return {p.name: dt.date.fromtimestamp(p.stat().st_mtime).isoformat() for p in paths if p.exists()}


# ------------------------------------------- figures -------------------------------------------
COL = {"Offense": plot.ACCENT, "Defense": plot.ACCENT2, "Special teams": plot.MUTED, "Team": plot.INK,
       "Quarterback": plot.ACCENT, "Receiver (WR/TE)": plot.ACCENT2, "Running back": plot.MUTED, "Pass rusher": plot.INK}


def atlas_figure(rows: list[dict], path, title, subtitle, cap=60, source=SRC):
    rows = sorted(rows, key=lambda r: (r["k_games"] if r["k_games"] is not None else 1e9), reverse=True)
    fig, ax = plt.subplots(figsize=(9.4, 0.27 * len(rows) + 1.6))
    y = np.arange(len(rows))
    for i, r in enumerate(rows):
        kg = r["k_games"] if r["k_games"] is not None else cap
        lo = r["k_games_ci"][0] if r["k_games_ci"][0] is not None else cap
        hi = r["k_games_ci"][1] if r["k_games_ci"][1] is not None else cap
        kg, lo, hi = min(kg, cap), min(lo, cap), min(hi, cap)
        c = COL[r["group"]]
        ax.plot([lo, hi], [i, i], color=c, lw=2, alpha=0.45, solid_capstyle="butt")
        ax.plot(kg, i, "o", color=c, ms=6)
        txt = f"{r['k_games']:.1f}" if r["k_games"] is not None and r["k_games"] < cap else ("no signal" if r["k_games"] is None else f"{r['k_games']:.0f}")
        if r["k_games_ci"][1] is None or (r["k_games_ci"][1] or 0) >= cap:
            ax.annotate("", xy=(cap + 1.2, i), xytext=(cap - 0.5, i), arrowprops=dict(arrowstyle="->", color=c, lw=1.2))
        ax.text(cap + 3.2, i, txt, va="center", fontsize=8.5, color=plot.INK)
    ax.axvline(17, color=plot.SOFT, lw=1, ls="--")
    ax.text(17.4, len(rows) - 0.4, "one 17-game season", fontsize=8, color=plot.MUTED, va="top")
    ax.set_yticks(y); ax.set_yticklabels([r["label"] for r in rows], fontsize=8.8)
    ax.set_xlim(0, cap + 9); ax.set_ylim(-0.7, len(rows) - 0.3); ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"Games of typical volume until the number is half signal (k), 95% interval; capped at {cap}")
    handles = [plt.Line2D([], [], marker="o", ls="", color=COL[g], label=g) for g in dict.fromkeys(r["group"] for r in rows)]
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(0.62, 0.55), fontsize=8.5, frameon=True, facecolor=plot.PLATE, edgecolor=plot.GRID)
    plot.finish(fig, ax, title, subtitle, path, source=source)


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    cur = data.latest_season_available()
    p = data.load_pbp(range(FIRST, cur + 1), columns=COLS)
    p = p[p.season_type == "REG"]
    last = cur  # the season in progress is left out of every estimate and used only for the current-season table
    through_week = int(p[p.season == cur].week.max())
    press = load_participation(range(2023, cur + 1))
    find = {"pulled": pull_info([data.DATA_DIR / f"pbp_{cur}.parquet", data.DATA_DIR / "ngs_rushing.parquet",
                                 data.DATA_DIR / f"participation_{cur - 1}.parquet", data.DATA_DIR / f"advstats_week_def_{cur - 1}.parquet"]),
            "seasons": f"{FIRST}-{last - 1}", "current_season": cur, "through_week": through_week,
            "pressure_seasons": sorted(int(s) for s in press.season.unique()), "n_splits": N_SPLITS, "boot_split": B_SPLIT, "boot_r": B_R,
            "train": f"{FIRST}-{SPLIT_YEAR - 1}", "test": f"{SPLIT_YEAR}-{last - 1}",
            "dropped": {"Yards per route run": "there are no public per-player route counts, since nflverse participation lists only the targeted receiver's route",
                        "Team pressure rate before 2023": "the 2016-2022 participation pressure field comes from a different source and leaves sacks out",
                        "Pass-rusher pressure per pass-rush snap": "there are no public pass-rush snap counts, so pressures per defensive snap are used instead"}}
    T = team_tables(p, press[["game_id", "play_id", "was_pressure"]])
    find["team_plays"] = int(T["off_epa"].query(f"season < {last}").den.sum())
    find["team_seasons"] = int(T["off_epa"].query(f"season < {last}").groupby(["season", "team"]).ngroups)

    atlas = {}
    for spec in TEAM_SPECS:
        atlas[spec.name] = atlas_row(spec, T[spec.name], "team", last)
        print(spec.name, atlas[spec.name]["split_half_r"], atlas[spec.name]["k_games"], atlas[spec.name]["yoy_r"])
    players = data.load_players()[["gsis_id", "position"]].dropna().drop_duplicates("gsis_id").set_index("gsis_id").position
    P = player_tables(p, players, last)
    P.update(ngs_and_pfr_tables(last))
    for spec in PLAYER_SPECS:
        atlas[spec.name] = atlas_row(spec, P[spec.name], "unit", last)
        print(spec.name, atlas[spec.name]["split_half_r"], atlas[spec.name]["k_games"], atlas[spec.name]["yoy_r"])
    find["atlas"] = atlas

    # ---- prediction ----
    pred, tab = team_prediction(T, last)
    find["predict_rest"] = pred
    find["week_curve"] = week_curve(T, last, ["res_point_diff", "res_win_pct", "net_epa", "net_sr", "off_epa", "def_epa"])
    find["next_season"] = next_season(T, last)
    find["qb_predict"] = qb_prediction(P, last)

    # ---- summaries the page quotes ----
    tm = [atlas[s.name] for s in TEAM_SPECS]
    pm = [atlas[s.name] for s in PLAYER_SPECS]
    def med(g, key="k_games"):
        v = [r[key] if r[key] is not None else np.inf for r in tm if r["group"] == g]
        return float(np.median(v))
    find["median_k_games"] = {g: round(med(g), 1) for g in ["Offense", "Defense"]}
    find["median_rel_full"] = {g: round(float(np.median([r["rel_full_season"] for r in tm if r["group"] == g])), 3) for g in ["Offense", "Defense", "Special teams", "Team"]}
    find["median_yoy"] = {g: round(float(np.median([r["yoy_r"] for r in tm if r["group"] == g])), 3) for g in ["Offense", "Defense"]}
    pairs = [(s.name, s.name.replace("off_", "def_")) for s in TEAM_SPECS if s.name.startswith("off_") and s.name.replace("off_", "def_") in atlas]
    find["off_vs_def_pairs"] = [[a, b, atlas[a]["rel_full_season"], atlas[b]["rel_full_season"]] for a, b in pairs]
    find["off_more_reliable_pairs"] = int(sum(atlas[a]["rel_full_season"] > atlas[b]["rel_full_season"] for a, b in pairs))
    noisy = sorted([r for r in tm + pm], key=lambda r: r["rel_full_season"])
    find["least_reliable"] = [[r["metric"], r["label"], r["rel_full_season"]] for r in noisy[:6]]
    find["most_reliable"] = [[r["metric"], r["label"], r["rel_full_season"]] for r in noisy[::-1][:6]]
    find["team_signal_by_8_games"] = [r["metric"] for r in tm if r["k_games"] is not None and r["k_games"] <= 8]
    find["team_no_majority_by_17"] = [r["metric"] for r in tm if r["rel_full_season"] < 0.5]
    oos = [r for r in tm + pm if "oos_mse_shrunk" in r]
    find["oos_metrics"] = len(oos)
    find["oos_shrunk_beats_raw"] = int(sum(r["oos_mse_shrunk"] < r["oos_mse_raw"] for r in oos))
    find["oos_shrunk_beats_mean"] = int(sum(r["oos_mse_shrunk"] < r["oos_mse_mean"] for r in oos))
    find["oos_median_mse_ratio_vs_raw"] = round(float(np.median([r["oos_mse_shrunk"] / r["oos_mse_raw"] for r in oos])), 3)
    find["oos_median_mse_ratio_vs_mean"] = round(float(np.median([r["oos_mse_shrunk"] / r["oos_mse_mean"] for r in oos])), 3)
    find["oos_calibration_r"] = round(float(np.corrcoef([r["oos_pred_reliability"] for r in oos], [r["oos_obs_slope"] for r in oos])[0, 1]), 3)
    find["oos_mean_abs_slope_gap"] = round(float(np.mean([abs(r["oos_obs_slope"] - r["oos_pred_reliability"]) for r in oos])), 3)
    ranked = sorted([(k, v) for k, v in pred.items() if not k.startswith("_")], key=lambda kv: -kv[1]["r_rest_pd"])
    find["predict_rank"] = [[k, v["r_rest_pd"]] for k, v in ranked]
    find["predict_beats_pd"] = [k for k, v in pred.items() if not k.startswith("_") and v["minus_point_diff"][1] > 0]
    # odd vs even across all metrics, for the robustness line
    find["odd_even_vs_random_mean_abs_gap"] = round(float(np.mean([abs(r["odd_even_r"] - r["split_half_r"]) for r in tm + pm])), 3)
    # the repo's own review findings, read from those studies' saved findings.json
    ctx = {}
    for slug, key in [("02-fourth-down-bot", "scorecard_split_half_r"), ("02-fourth-down-bot", "scorecard_yoy_r"),
                      ("03-sack-leverage", "epa_per_sack_yoy_r"), ("05-kickoff-value", "returner_split_half_r"),
                      ("05-kickoff-value", "kicker_split_half_r"), ("01-flag-audit", "split_r_net"), ("04-luck-index", "yoy_r_fumble_luck"),
                      ("09-run-game-value", "yoy_r")]:
        fp = Path("reports") / slug / "findings.json"
        if fp.exists():
            v = json.loads(fp.read_text()).get(key)
            ctx[f"{slug[:2]}_{key}"] = v["ryoe_pc"] if isinstance(v, dict) else v
    find["repo_context"] = ctx
    # where each of those would sit among the team metrics here (nearest split-half r)
    near = lambda v: min(tm, key=lambda r: abs(r["split_half_r"] - v))
    find["repo_context_nearest"] = {k: [near(v)["metric"], near(v)["label"], near(v)["split_half_r"]] for k, v in ctx.items()
                                    if isinstance(v, (int, float)) and "split_half" in k}
    find["share_yoy_below_within"] = [int(sum(r["yoy_r"] < r["rel_full_season"] for r in tm + pm)), len(tm + pm)]
    wc = find["week_curve"]
    find["week_curve_pd_minus_net_epa"] = [[a[0], round(a[1] - b[1], 3)] for a, b in zip(wc["res_point_diff"], wc["net_epa"])]
    find["week_curve_max_abs_gap"] = round(float(max(abs(g) for _, g in find["week_curve_pd_minus_net_epa"])), 3)
    find["week_curve_pd_peak"] = max(wc["res_point_diff"], key=lambda a: a[1])
    find["pressure_vs_sack_def"] = [atlas["def_pressure_rate"]["k_games"], atlas["def_sack_rate"]["k_games"]]

    # ---- outputs ----
    at = pd.DataFrame(tm + pm)
    at["rank_in_group"] = at.groupby(at.group.isin(["Offense", "Defense", "Special teams", "Team"])).rel_full_season.rank(ascending=False).astype(int)
    keep = ["metric", "label", "group", "unit", "min_season", "min_half", "seasons", "unit_seasons", "split_half_r", "split_half_ci", "odd_even_r", "half_sample", "k", "k_ci",
            "per_game", "k_games", "k_games_ci", "rel_full_season", "regress_4", "regress_8", "regress_17", "yoy_r", "yoy_ci", "yoy_pairs",
            "oos_train", "oos_test", "k_train", "oos_mse_shrunk", "oos_mse_raw", "oos_mse_mean", "oos_pred_reliability", "oos_obs_slope"]
    at.sort_values(["group", "rel_full_season"], ascending=[True, False])[keep].to_csv(OUT / "atlas.csv", index=False)
    gd = pd.DataFrame([{"metric": r["metric"], "label": r["label"], "unit": r["unit"], "k_trials": r["k"], "per_game": r["per_game"],
                        "regress_after_4_games": r["regress_4"], "regress_after_8_games": r["regress_8"], "regress_after_17_games": r["regress_17"]}
                       for r in tm + pm])
    gd.to_csv(OUT / "regression_guide.csv", index=False)
    pr = pd.DataFrame([{"metric": k, "label": atlas[k]["label"], **{a: (str(b) if isinstance(b, list) else b) for a, b in v.items()},
                        "r_next_season_pd": find["next_season"].get(k, [None])[0]} for k, v in ranked])
    pr.to_csv(OUT / "predict_rest_of_season.csv", index=False)
    cs = current_season_table(T, atlas, cur)
    cs.sort_values("regressed_net_epa", ascending=False).round(4).to_csv(OUT / f"teams_{cur}_regressed.csv", index=False)
    find["current_table_teams"] = int(len(cs))
    find["current_games_range"] = [int(cs.sample_res_point_diff.min()), int(cs.sample_res_point_diff.max())]
    find["current_regress_share"] = {nm: round(float(cs[f"regress_share_{nm}"].median()), 3) for nm in ["off_epa", "def_epa", "net_epa", "res_point_diff"]}
    rank_raw = cs.raw_net_epa.rank(ascending=False); rank_reg = cs.regressed_net_epa.rank(ascending=False)
    find["current_rank_r"] = round(float(np.corrcoef(rank_raw, rank_reg)[0, 1]), 3)
    find["current_point_diff_vs_net_epa_rank_moves_3plus"] = int(((cs.raw_res_point_diff.rank(ascending=False) - rank_reg).abs() >= 3).sum())

    # ---- figures ----
    atlas_figure(tm, OUT / "team_atlas.png", "How many games until a team number is half signal",
                 f"Split-half reliability over {N_SPLITS} random game splits, {FIRST}-{last - 1} regular seasons (FTN pressure {min(find['pressure_seasons'])}-{last - 1})",
                 source=SRC_ALL)
    atlas_figure(pm, OUT / "player_atlas.png", "How many games until a player number is half signal",
                 f"Games of a typical qualified player's volume; {FIRST}-{last - 1} (NGS and PFR rows from 2018)", source=SRC_ALL)

    fig, ax = plt.subplots(figsize=(8.6, 6.2))
    TEAM_G = {"Offense", "Defense", "Special teams", "Team"}
    for r in tm + pm:
        ax.errorbar(r["rel_full_season"], r["yoy_r"], yerr=[[r["yoy_r"] - r["yoy_ci"][0]], [r["yoy_ci"][1] - r["yoy_r"]]],
                    fmt="o" if r["group"] in TEAM_G else "s", color=COL[r["group"]], ms=5, elinewidth=0.8, alpha=0.85)
    lab = {"off_epa": (6, -10), "def_epa": (6, -10), "wr_tgt_share": (-10, -14), "pr_pressure_rate": (-150, 4), "def_fumble_lost_rate": (6, -14),
           "st_fg_pct": (4, 8), "qb_cpoe": (6, 4), "rb_ryoe": (-118, 6), "def_int_rate": (6, -10)}
    for r in tm + pm:
        if r["metric"] in lab:
            ax.annotate(r["label"], (r["rel_full_season"], r["yoy_r"]), xytext=lab[r["metric"]], textcoords="offset points", fontsize=7.8,
                        color=plot.MUTED, ha="left")
    ax.plot([0, 1], [0, 1], color=plot.SOFT, lw=1, ls="--"); ax.axhline(0, color=plot.SOFT, lw=0.8)
    ax.text(0.97, 0.99, "repeats as well as\nwithin a season", fontsize=8, color=plot.MUTED, ha="right", va="top")
    ax.set_xlim(0, 1); ax.set_ylim(-0.25, 1)
    ax.set_xlabel("Within-season reliability of a full season (from split halves)"); ax.set_ylabel("Year-to-year r (95% interval)")
    handles = [plt.Line2D([], [], marker="o" if g in TEAM_G else "s", ls="", color=c, label=g) for g, c in COL.items()]
    ax.legend(handles=handles, loc="upper left", fontsize=8, ncol=2)
    yb, ya = find["share_yoy_below_within"]
    plot.finish(fig, ax, f"{yb} of {ya} numbers repeat less across seasons than within one" if yb > ya / 2 else "Most numbers carry across seasons as well as within one",
                "Each dot is a metric: how reliable a full season is, against how well it carries into the next season", OUT / "within_vs_across.png", source=SRC_ALL)

    fig, ax = plt.subplots(figsize=(9, 0.27 * len(ranked) + 1.6))
    for i, (k, v) in enumerate(ranked[::-1]):
        c = COL[atlas[k]["group"]]
        ax.plot(v["r_rest_pd_ci"], [i, i], color=c, lw=2, alpha=0.45); ax.plot(v["r_rest_pd"], i, "o", color=c, ms=6)
        ax.text(max(v["r_rest_pd_ci"][1], 0) + 0.02, i, f"{v['r_rest_pd']:.2f}", va="center", fontsize=8.3)
    ax.axvline(pred["res_point_diff"]["r_rest_pd"], color=plot.SOFT, ls="--", lw=1)
    ax.axvline(0, color=plot.SOFT, lw=0.8)
    ax.set_yticks(range(len(ranked))); ax.set_yticklabels([atlas[k]["label"] for k, _ in ranked[::-1]], fontsize=8.6); ax.grid(axis="y", visible=False)
    ax.set_xlabel("r with point differential per game over the rest of the season (sign set so higher = better), 95% interval")
    ax.set_xlim(-0.35, 0.8)
    plot.finish(fig, ax, "After 8 games, no metric beats point differential at predicting the rest" if not find["predict_beats_pd"]
                else f"After 8 games, {len(find['predict_beats_pd'])} metric(s) beat point differential at predicting the rest",
                f"First 8 games vs games 9 on, {pred['_n']} team-seasons {FIRST}-{last - 1}; dashed line = point differential itself", OUT / "predict_rest.png", source=SRC)

    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    labs = {"res_point_diff": "Point differential", "res_win_pct": "Win %", "net_epa": "Net EPA/play", "net_sr": "Net success rate",
            "off_epa": "Offense EPA/play", "def_epa": "Defense EPA/play (sign flipped)"}
    cols = [plot.INK, plot.SOFT, plot.ACCENT, plot.MUTED, "#5aa37a", plot.ACCENT2]
    for (nm, lb), c in zip(labs.items(), cols):
        a = np.array(find["week_curve"][nm])
        ax.plot(a[:, 0], a[:, 1], "-o", color=c, ms=3.5, lw=1.8, label=lb)
        if nm in ("res_point_diff", "net_epa"):
            ax.fill_between(a[:, 0], a[:, 2], a[:, 3], color=c, alpha=0.12, lw=0)
    ax.set_xlabel("Games played"); ax.set_ylabel("r with point differential per game, rest of season")
    ax.set_xticks(range(1, 13)); ax.legend(fontsize=8.5, loc="lower right"); ax.set_ylim(0, 0.75)
    plot.finish(fig, ax, "Point differential and net EPA per play forecast the rest about equally" if find["week_curve_max_abs_gap"] < 0.05
                else "Point differential and net EPA per play forecast the rest differently",
                f"Each team-season {FIRST}-{last - 1}; bands are 95% intervals resampling teams", OUT / "week_curve.png", source=SRC)

    fig, ax = plt.subplots(figsize=(7.4, 6.2))
    for r in oos:
        ax.plot(r["oos_pred_reliability"], r["oos_obs_slope"], "o" if r["group"] in TEAM_G else "s", color=COL[r["group"]], ms=5.5, alpha=0.85)
    ax.plot([0, 1], [0, 1], color=plot.SOFT, ls="--", lw=1)
    ax.set_xlim(-0.05, 1); ax.set_ylim(-0.25, 1.05)
    ax.set_xlabel("Reliability the earlier seasons' k predicts for the odd weeks"); ax.set_ylabel("Observed slope, even weeks on odd weeks (later seasons)")
    handles = [plt.Line2D([], [], marker="o" if g in TEAM_G else "s", ls="", color=c, label=g) for g, c in COL.items()]
    ax.legend(handles=handles, loc="upper left", fontsize=8, ncol=2)
    plot.finish(fig, ax, f"Out of sample, the regressed number beats the raw one for {find['oos_shrunk_beats_raw']} of {find['oos_metrics']} metrics",
                f"Each dot is a metric; k fit on the earlier seasons ({find['train']} for most), tested on the later ones", OUT / "oos_check.png", source=SRC_ALL)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k_, v_ in find.items():
        if k_ != "atlas":
            print(k_, v_)


if __name__ == "__main__":
    main()
