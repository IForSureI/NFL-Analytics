"""11 Turnovers Forced: do defenses that force turnovers keep doing it?

The defensive version of studies 04 (Luck Index) and 07 (Box-Score Tax). Takeaways decide games and
headlines, but they are rare events, so a season of them is noisy. If takeaways repeat less than the
rest of a defense's work, a takeaway-heavy year makes a defense look better than it is, and next
year's points allowed should follow the defense underneath the takeaways, not the takeaways.

Team-season defensive measures (regular season, scrimmage plays):
  takeaway side: interceptions per dropback, forced fumbles per play, share of the offense's loose
  balls the defense recovers, takeaways per play and per game.
  stable side: sack-or-QB-hit rate per dropback (a pressure proxy), success rate allowed and EPA
  per play allowed, both on plays without a takeaway.
Tests:
  1. Stability: year-to-year r of each measure, with franchise-resampled 95% intervals.
  2. Prediction: does this year's takeaway rate predict next year's points allowed better or worse
     than EPA allowed without turnovers? Correlations, then an out-of-sample test (fit on seasons
     2006-2015 -> next year, scored on 2016-2024 -> next year).
  3. The fooled test: how many points per game do takeaways save this year, and how much of that
     carries into next year, next to the non-turnover defense?
  4. Regression of top-5 takeaway seasons: how much of the excess is left next year, and how their
     points allowed change against defenses that allowed the same points without the takeaways.
  5. Players: do individual interceptions repeat? Reconciled with study 07's PFR finding.
  6. The 2026 buy/sell list through the latest completed week: a rest-of-season forecast built on
     weeks 1-10 of 2006-2025, against points allowed so far.
Data: nflverse play-by-play 2006-present, nflverse snap counts (2013+), Pro Football Reference
advanced defense via nflverse (2018+). No coach fields are used.
Run: python -m projects.turnovers_forced
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot
from projects.box_score_tax import ols

OUT = Path("reports/11-turnovers-forced")
SRC = "Data: nflverse play-by-play (nflfastR EPA). Chart: Dylan Fanelli"
FIRST = 2006
FRANCHISE = {"STL": "LA", "SD": "LAC", "OAK": "LV"}   # relocations: one franchise, one id, so year-to-year pairs survive moves
N_BOOT = 1000
TOP_N = 5               # top-5 takeaway seasons each year
MATCH_PA = 1.0          # controls allowed within this many points per game of the top-5 team
SPLIT_WEEK = 10         # in-season forecast: weeks 1-10 predict weeks 11+
FLAG_PPG = 1.5          # buy/sell flag (set before the 2026 list was run): takeaways worth this many points per game, above (sell) or below (buy) league average
MIN_SNAPS = 400         # player-seasons: defensive snaps
DBS = {"CB", "S", "FS", "SS", "DB"}
LBS = {"LB", "ILB", "MLB", "OLB"}

COLS = ["game_id", "season", "season_type", "week", "game_date", "posteam", "defteam", "home_team", "away_team",
        "home_score", "away_score", "play_type", "epa", "down", "qb_dropback", "interception", "fumble",
        "fumble_forced", "fumble_lost", "fumbled_1_team", "fumble_recovery_1_team", "sack", "qb_hit", "success",
        "interception_player_id", "interception_player_name", "forced_fumble_player_1_player_id",
        "forced_fumble_player_2_player_id", "pass_defense_1_player_id", "pass_defense_2_player_id"]

LABELS = {
    "takeaways_pg": "Takeaways per game",
    "to_rate": "Takeaways per 100 plays",
    "int_rate": "Interceptions per 100 dropbacks",
    "ff_rate": "Forced fumbles per 100 plays",
    "fum_rec_share": "Share of loose balls recovered",
    "press_rate": "Sack or QB hit per dropback",
    "succ_noto": "Success rate allowed (no-takeaway plays)",
    "epa_noto": "EPA per play allowed (no-takeaway plays)",
    "epa_all": "EPA per play allowed (all plays)",
    "pa_pg": "Points allowed per game",
}
TAKEAWAY_SIDE = ["takeaways_pg", "to_rate", "int_rate", "ff_rate", "fum_rec_share"]
STABLE_SIDE = ["press_rate", "succ_noto", "epa_noto", "epa_all", "pa_pg"]


def fr(team: pd.Series) -> pd.Series:
    return team.replace(FRANCHISE)


def latest_complete_week(pbp: pd.DataFrame, season: int) -> int:
    """The last week of `season` with all its games in the file: a week with fewer games than any earlier week
    (byes included) is still being played."""
    g = pbp[(pbp.season == season) & (pbp.season_type == "REG")].drop_duplicates("game_id")
    if g.empty:
        return 0
    n = g.groupby("week").game_id.size().sort_index()
    last = int(n.index.max())
    if len(n) > 1 and n.loc[last] < n.iloc[:-1].min():
        return last - 1
    return last


def tag_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Scrimmage plays (runs and dropbacks with EPA) with the defensive events marked."""
    s = data.scrimmage(pbp).copy()
    s["defteam"] = fr(s.defteam); s["posteam"] = fr(s.posteam)
    s["fumbled_1_team"] = fr(s.fumbled_1_team); s["fumble_recovery_1_team"] = fr(s.fumble_recovery_1_team)
    s["int"] = (s.interception == 1).astype(int)
    s["fum_lost"] = ((s.fumble_lost == 1) & (s.interception != 1)).astype(int)   # a fumble after an interception return is the defense's own
    s["takeaway"] = ((s.int == 1) | (s.fum_lost == 1)).astype(int)
    off_fum = (s.fumble == 1) & (s.fumbled_1_team == s.posteam) & (s.interception != 1)
    s["opp_fum"] = off_fum.astype(int)
    s["opp_fum_known"] = (off_fum & s.fumble_recovery_1_team.notna()).astype(int)     # out-of-bounds fumbles have no recovery team
    s["def_rec"] = (off_fum & (s.fumble_recovery_1_team == s.defteam)).astype(int)
    s["ff"] = (off_fum & (s.fumble_forced == 1)).astype(int)
    s["db"] = (s.qb_dropback == 1).astype(int)
    s["press"] = ((s.db == 1) & ((s.sack == 1) | (s.qb_hit == 1))).astype(int)   # each dropback counted once (most sacks are also QB hits)
    s["noto"] = 1 - s.takeaway
    s["epa_noto_x"] = np.where(s.noto == 1, s.epa, 0.0)
    s["succ_noto_x"] = np.where(s.noto == 1, s.success, 0.0)
    return s


def team_points(pbp: pd.DataFrame) -> pd.DataFrame:
    g = pbp.drop_duplicates("game_id")[["game_id", "season", "week", "home_team", "away_team", "home_score", "away_score"]]
    h = pd.DataFrame({"game_id": g.game_id, "season": g.season, "week": g.week, "team": fr(g.home_team), "pa": g.away_score})
    a = pd.DataFrame({"game_id": g.game_id, "season": g.season, "week": g.week, "team": fr(g.away_team), "pa": g.home_score})
    return pd.concat([h, a], ignore_index=True)


def aggregate(s: pd.DataFrame, pts: pd.DataFrame, keys=("season", "team")) -> pd.DataFrame:
    keys = list(keys)
    a = s.rename(columns={"defteam": "team"}).groupby(keys).agg(
        plays=("epa", "size"), dropbacks=("db", "sum"), ints=("int", "sum"), fum_lost=("fum_lost", "sum"),
        takeaways=("takeaway", "sum"), opp_fum=("opp_fum", "sum"), opp_fum_known=("opp_fum_known", "sum"),
        def_rec=("def_rec", "sum"), ff=("ff", "sum"), press=("press", "sum"), noto=("noto", "sum"),
        epa_noto_sum=("epa_noto_x", "sum"), succ_noto_sum=("succ_noto_x", "sum"), epa_sum=("epa", "sum"))
    p = pts.groupby(keys).agg(games=("pa", "size"), pa=("pa", "sum"))
    t = a.join(p, how="inner")
    t["takeaways_pg"] = t.takeaways / t.games
    t["to_rate"] = 100 * t.takeaways / t.plays
    t["int_rate"] = 100 * t.ints / t.dropbacks
    t["ff_rate"] = 100 * t.ff / t.plays
    t["fum_rec_share"] = t.def_rec / t.opp_fum_known.replace(0, np.nan)
    t["press_rate"] = t.press / t.dropbacks
    t["succ_noto"] = t.succ_noto_sum / t.noto
    t["epa_noto"] = t.epa_noto_sum / t.noto
    t["epa_all"] = t.epa_sum / t.plays
    t["pa_pg"] = t.pa / t.games
    return t.reset_index()


def pairs(ts: pd.DataFrame, center: bool = False) -> pd.DataFrame:
    """Season N joined to season N+1 for the same franchise. center=True subtracts each season's league mean first,
    so a league-wide trend (interceptions fell from about 2.9 to 1.9 per 100 dropbacks over 2006-2024) is not read as a team trait."""
    cols = ["season", "team", "games"] + list(LABELS)
    a = ts[cols].copy()
    if center:
        a[list(LABELS)] = a[list(LABELS)] - a.groupby("season")[list(LABELS)].transform("mean")
    return a.merge(a.assign(season=a.season - 1), on=["season", "team"], suffixes=("", "_next"))


def boot(df: pd.DataFrame, fn, key="team", n=N_BOOT, seed=11):
    """Resample clusters (franchises or players) with replacement and recompute fn on each sample."""
    rng = np.random.default_rng(seed)
    d = df.reset_index(drop=True)
    groups = [g.index.values for _, g in d.groupby(key)]
    out = []
    for _ in range(n):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        out.append(fn(d.loc[idx].reset_index(drop=True)))
    return out


def point_ci(df, fn, key="team", d=3, n=N_BOOT):
    v = fn(df)
    b = np.array(boot(df, fn, key, n), dtype=float)
    lo, hi = np.nanpercentile(b, [2.5, 97.5])
    return [round(float(v), d), round(float(lo), d), round(float(hi), d)]


def corr(x, y):
    return lambda d: d[x].corr(d[y])


def fit_predict(train, test, xs, y):
    A = np.column_stack([np.ones(len(train))] + [train[x] for x in xs])
    b = np.linalg.lstsq(A, train[y].to_numpy(), rcond=None)[0]
    return np.column_stack([np.ones(len(test))] + [test[x] for x in xs]) @ b


def rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def matched_change(d: pd.DataFrame, hit_mask: pd.Series, ctrl_mask: pd.Series, col="pa_pg", window: float = MATCH_PA,
                   same_season: bool = True, count: bool = False) -> float:
    """Mean next-year change for hit teams minus the change for controls that allowed about the same points (within `window`).
    same_season=True draws controls from the hit team's own season, so league-wide scoring trends cancel.
    count=True returns how many hit teams found at least one control."""
    hit, ctrl = d[hit_mask.to_numpy()], d[ctrl_mask.to_numpy()]
    if hit.empty or ctrl.empty:
        return np.nan
    cpa = ctrl.pa_pg.to_numpy(); cch = (ctrl[col + "_next"] - ctrl[col]).to_numpy(); cse = ctrl.season.to_numpy()
    gaps = []
    for pa, ch, se in zip(hit.pa_pg.to_numpy(), (hit[col + "_next"] - hit[col]).to_numpy(), hit.season.to_numpy()):
        m = np.abs(cpa - pa) <= window
        if same_season:
            m &= cse == se
        if m.any():
            gaps.append(ch - cch[m].mean())
    if count:
        return len(gaps)
    return float(np.mean(gaps)) if gaps else np.nan


def player_tables(pbp: pd.DataFrame, last_full: int):
    """Player-season interceptions, forced fumbles and pass breakups (pbp) with defensive snaps (nflverse snap counts)."""
    p = pbp[(pbp.season_type == "REG") & (pbp.season >= 2013) & (pbp.season <= last_full)]
    ints = p[p.interception == 1].groupby(["season", "interception_player_id"]).size().rename("ints")
    ff = pd.concat([p[["season", c]].rename(columns={c: "pid"}) for c in ["forced_fumble_player_1_player_id", "forced_fumble_player_2_player_id"]]).dropna()
    ff = ff.groupby(["season", "pid"]).size().rename("ff")
    pdx = []
    for c in ["pass_defense_1_player_id", "pass_defense_2_player_id"]:
        q = p[p[c].notna()]
        q = q[~((q.interception == 1) & (q[c] == q.interception_player_id))]      # the interceptor is usually also credited with the pass defensed
        pdx.append(q[["season", c]].rename(columns={c: "pid"}))
    pbu = pd.concat(pdx).groupby(["season", "pid"]).size().rename("pbu")
    ev = pd.concat([ints.rename_axis(["season", "pid"]), ff, pbu], axis=1).fillna(0).reset_index()
    s = data.load_snap_counts(range(2013, last_full + 1))
    s = s[s.game_type == "REG"]
    sn = s.groupby(["season", "pfr_player_id"]).agg(def_snaps=("defense_snaps", "sum"), pos=("position", "last"), player=("player", "last")).reset_index()
    pl = data.load_players()[["pfr_id", "gsis_id"]].dropna().drop_duplicates("pfr_id")
    sn = sn.merge(pl, left_on="pfr_player_id", right_on="pfr_id", how="inner")
    m = sn.merge(ev, left_on=["season", "gsis_id"], right_on=["season", "pid"], how="left")
    m[["ints", "ff", "pbu"]] = m[["ints", "ff", "pbu"]].fillna(0)
    m = m[(m.def_snaps >= MIN_SNAPS) & m.pos.isin(DBS | LBS)].copy()
    m["grp"] = np.where(m.pos.isin(DBS), "DB", "LB")
    for c in ["ints", "ff", "pbu"]:
        m[c + "100"] = 100 * m[c] / m.def_snaps
    m["plays_on_ball100"] = m.ints100 + m.pbu100
    rates = ["ints100", "ff100", "pbu100", "plays_on_ball100"]
    m[rates] = m[rates] - m.groupby(["season", "grp"])[rates].transform("mean")   # league trends out, as for teams
    return m


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    last = data.latest_season_available()
    pbp = data.load_pbp(range(FIRST, last + 1), columns=COLS)
    pbp = pbp[pbp.season_type == "REG"]
    wk = latest_complete_week(pbp, last)
    cur_mask = (pbp.season == last) & (pbp.week > wk)
    pbp = pbp[~cur_mask]
    last_full = last - 1 if wk < 17 else last
    find = {"min_snaps": MIN_SNAPS, "split_week": SPLIT_WEEK, "seasons": f"{FIRST}-{last_full}", "current_season": int(last), "through_week": int(wk),
            "pbp_pulled": pd.Timestamp(data.pbp_path(last).stat().st_mtime, unit="s").strftime("%Y-%m-%d"),
            "current_last_game_date": str(pbp[pbp.season == last].game_date.max())}

    s = tag_plays(pbp)
    pts = team_points(pbp)
    ts = aggregate(s, pts)
    full = ts[ts.season <= last_full].copy()
    full.round(4).to_csv(OUT / "team_season_defense.csv", index=False)
    find["team_seasons"] = len(full)
    lg = full[["takeaways_pg", "to_rate", "int_rate", "ff_rate", "fum_rec_share", "press_rate", "succ_noto", "epa_noto", "pa_pg"]].mean()
    find["league_means"] = {k: round(float(v), 4) for k, v in lg.items()}
    find["league_fum_rec_share_pooled"] = round(float(full.def_rec.sum() / full.opp_fum_known.sum()), 3)

    # ---------- 1. stability ----------
    nr = pairs(full)                    # raw values: the top-5 description and its matched test
    nx = pairs(full, center=True)       # each season's league mean taken out: stability, prediction and carry
    find["pairs"] = len(nx)
    yoy = {m: point_ci(nx, corr(m, m + "_next")) for m in LABELS}
    find["yoy_r"] = yoy
    find["yoy_r_raw"] = {m: round(float(nr[m].corr(nr[m + "_next"])), 3) for m in LABELS}
    find["league_int_rate_first_last"] = [round(float(full[full.season == full.season.min()].int_rate.mean()), 2),
                                          round(float(full[full.season == full.season.max()].int_rate.mean()), 2)]
    dr = lambda a, b: (lambda d: d[a].corr(d[a + "_next"]) - d[b].corr(d[b + "_next"]))
    find["yoy_r_diff"] = {f"{a}_minus_{b}": point_ci(nx, dr(a, b)) for a, b in
                          [("epa_noto", "to_rate"), ("epa_noto", "int_rate"), ("press_rate", "int_rate"), ("succ_noto", "to_rate"), ("int_rate", "fum_rec_share")]}
    # within-season split-half (odd vs even weeks), Spearman-Brown to a full season: the regression constant for the in-season list
    s["odd"] = s.week % 2
    pts["odd"] = pts.week % 2
    halves = aggregate(s[s.season <= last_full], pts[pts.season <= last_full], keys=("season", "team", "odd"))
    hw = halves.pivot_table(index=["season", "team"], columns="odd", values=["to_rate", "int_rate", "fum_rec_share", "epa_noto", "succ_noto", "press_rate"])
    split = {}
    for m in ["to_rate", "int_rate", "fum_rec_share", "epa_noto", "succ_noto", "press_rate"]:
        r = hw[m][0].corr(hw[m][1])
        split[m] = {"split_half_r": round(float(r), 3), "full_season_reliability": round(float(2 * r / (1 + r)), 3)}
    find["split_half"] = split
    # takeaway-rate regression constant in plays: reliability = n / (n + k)
    n_half = full.plays.mean() / 2
    r_to = max(split["to_rate"]["split_half_r"], 1e-3)
    k_to = n_half * (1 - r_to) / r_to
    find["to_rate_k_plays"] = round(float(k_to), 0)

    # ---------- 2. prediction of next year's points allowed ----------
    preds = ["takeaways_pg", "to_rate", "int_rate", "fum_rec_share", "press_rate", "succ_noto", "epa_noto", "epa_all", "pa_pg"]
    find["r_next_pa"] = {m: point_ci(nx, corr(m, "pa_pg_next")) for m in preds}
    find["r_next_pa_diff_epa_noto_minus_to_rate"] = point_ci(
        nx, lambda d: abs(d.epa_noto.corr(d.pa_pg_next)) - abs(d.to_rate.corr(d.pa_pg_next)))
    find["r_next_pa_diff_epa_noto_minus_pa"] = point_ci(
        nx, lambda d: abs(d.epa_noto.corr(d.pa_pg_next)) - abs(d.pa_pg.corr(d.pa_pg_next)))
    # same-year link, for contrast: takeaways are tied to this year's points allowed
    find["r_same_pa"] = {m: round(float(full[m].corr(full.pa_pg)), 3) for m in ["to_rate", "epa_noto", "takeaways_pg"]}
    # out of sample
    train = nx[nx.season <= 2015]; test = nx[nx.season >= 2016].copy()
    models = {"league mean": [], "takeaways per 100 plays": ["to_rate"], "EPA allowed, no-takeaway plays": ["epa_noto"],
              "EPA + takeaway rate": ["epa_noto", "to_rate"], "points allowed this year": ["pa_pg"],
              "points allowed + EPA no-takeaway": ["pa_pg", "epa_noto"]}
    oos = {}
    for name, xs in models.items():
        test["p_" + name] = fit_predict(train, test, xs, "pa_pg_next") if xs else train.pa_pg_next.mean()
    sst = float(((test.pa_pg_next - test.pa_pg_next.mean()) ** 2).sum())
    for name in models:
        oos[name] = {"rmse": round(rmse(test.pa_pg_next, test["p_" + name]), 3),
                     "r2": round(1 - float(((test.pa_pg_next - test["p_" + name]) ** 2).sum()) / sst, 3)}
    find["oos"] = oos
    find["oos_train"] = f"{int(train.season.min())}-{int(train.season.max())}"
    find["oos_test"] = f"{int(test.season.min())}-{int(test.season.max())}"
    find["oos_n"] = [len(train), len(test)]
    d_fn = lambda d: rmse(d.pa_pg_next, d["p_takeaways per 100 plays"]) - rmse(d.pa_pg_next, d["p_EPA allowed, no-takeaway plays"])
    find["oos_rmse_to_minus_epa"] = point_ci(test, d_fn)
    # the same comparison under other splits: reversed (fit on the later seasons) and leave one season out
    splits = {}
    rev_tr, rev_te = nx[nx.season >= 2015], nx[nx.season <= 2014].copy()
    for name in ["takeaways per 100 plays", "EPA allowed, no-takeaway plays", "EPA + takeaway rate", "points allowed this year"]:
        rev_te["p_" + name] = fit_predict(rev_tr, rev_te, models[name], "pa_pg_next")
    splits["reversed"] = {k: round(rmse(rev_te.pa_pg_next, rev_te["p_" + k]), 3) for k in ["takeaways per 100 plays", "EPA allowed, no-takeaway plays", "EPA + takeaway rate", "points allowed this year"]}
    lo = nx.copy()
    for name in ["takeaways per 100 plays", "EPA allowed, no-takeaway plays", "EPA + takeaway rate", "points allowed this year"]:
        lo["p_" + name] = np.nan
        for se in lo.season.unique():
            m = lo.season == se
            lo.loc[m, "p_" + name] = fit_predict(lo[~m], lo[m], models[name], "pa_pg_next")
    splits["leave one season out"] = {k: round(rmse(lo.pa_pg_next, lo["p_" + k]), 3) for k in ["takeaways per 100 plays", "EPA allowed, no-takeaway plays", "EPA + takeaway rate", "points allowed this year"]}
    splits["base"] = {k: oos[k]["rmse"] for k in ["takeaways per 100 plays", "EPA allowed, no-takeaway plays", "EPA + takeaway rate", "points allowed this year"]}
    find["oos_splits"] = splits
    find["oos_epa_beats_to_in"] = sum(v["EPA allowed, no-takeaway plays"] < v["takeaways per 100 plays"] for v in splits.values())
    find["oos_adding_to_helps_in"] = sum(v["EPA + takeaway rate"] < v["EPA allowed, no-takeaway plays"] for v in splits.values())

    # ---------- 3. the fooled test: points per game takeaways save this year vs next ----------
    z = nx.copy()
    for c in ["to_rate", "epa_noto"]:
        z[c + "_sd"] = (z[c] - z[c].mean()) / z[c].std()
    same = ols(z.pa_pg, z[["epa_noto_sd", "to_rate_sd"]], groups=z.team)
    nxtm = ols(z.pa_pg_next, z[["epa_noto_sd", "to_rate_sd"]], groups=z.team)
    find["pa_per_sd_same_year"] = {c: [round(float(same.params[c]), 3)] + [round(float(x), 3) for x in same.conf_int().loc[c]] for c in ["epa_noto_sd", "to_rate_sd"]}
    find["pa_per_sd_next_year"] = {c: [round(float(nxtm.params[c]), 3)] + [round(float(x), 3) for x in nxtm.conf_int().loc[c]] for c in ["epa_noto_sd", "to_rate_sd"]}
    find["sd_to_rate"] = round(float(nx.to_rate.std()), 3); find["sd_epa_noto"] = round(float(nx.epa_noto.std()), 4)
    find["sd_takeaways_pg"] = round(float(nx.takeaways_pg.std()), 3)
    find["same_year_r2"] = round(float(same.rsquared), 3); find["next_year_r2"] = round(float(nxtm.rsquared), 3)

    def carry(d, c):
        A = lambda y: np.linalg.lstsq(np.column_stack([np.ones(len(d)), d.epa_noto, d.to_rate]), d[y].to_numpy(), rcond=None)[0]
        b0, b1 = A("pa_pg"), A("pa_pg_next")
        i = 1 if c == "epa_noto" else 2
        return b1[i] / b0[i]
    find["carry_share_to_rate"] = point_ci(nx, lambda d: carry(d, "to_rate"))
    find["carry_share_epa_noto"] = point_ci(nx, lambda d: carry(d, "epa_noto"))
    # the takeaway rate split into its parts: interceptions, forced fumbles, and who falls on the ball
    comp = ["epa_noto", "int_rate", "ff_rate", "fum_rec_share"]
    zc = nx.dropna(subset=comp + ["pa_pg_next"]).copy()
    def comp_coefs(d, y):
        return np.linalg.lstsq(np.column_stack([np.ones(len(d))] + [d[c] for c in comp]), d[y].to_numpy(), rcond=None)[0][1:]
    cs_ = comp_coefs(zc, "pa_pg"); cn_ = comp_coefs(zc, "pa_pg_next")
    sd_ = zc[comp].std()
    find["components_pa_per_sd"] = {c: {"same_year": round(float(cs_[i] * sd_[c]), 3), "next_year": round(float(cn_[i] * sd_[c]), 3)} for i, c in enumerate(comp)}
    for i, c in enumerate(comp):
        find["components_pa_per_sd"][c]["next_year_ci"] = point_ci(zc, lambda d, i=i, c=c: comp_coefs(d, "pa_pg_next")[i] * sd_[c])[1:]
        find["components_pa_per_sd"][c]["carry"] = point_ci(zc, lambda d, i=i: comp_coefs(d, "pa_pg_next")[i] / comp_coefs(d, "pa_pg")[i])
    find["components_n"] = len(zc)
    b_same_to = float(np.linalg.lstsq(np.column_stack([np.ones(len(nx)), nx.epa_noto, nx.to_rate]), nx.pa_pg.to_numpy(), rcond=None)[0][2])
    b_to_same = np.linalg.lstsq(np.column_stack([np.ones(len(full)), full.epa_noto, full.to_rate]), full.pa_pg.to_numpy(), rcond=None)[0]
    find["pa_per_takeaway_per_100_same_year"] = round(float(b_to_same[2]), 3)

    # ---------- 4. top-5 takeaway seasons ----------
    nr["tb"] = nr.takeaways_pg + 1e-6 * nr.to_rate        # ties on takeaways per game are broken by takeaways per play, not row order
    nr["rank_tpg"] = nr.groupby("season").tb.rank(ascending=False, method="first")
    nr["ties_at_cut"] = nr.groupby("season").takeaways_pg.transform(lambda x: int((x == x.nlargest(TOP_N).min()).sum() > 1))
    lgs = full.groupby("season").takeaways_pg.mean()
    nr["exc"] = nr.takeaways_pg - nr.season.map(lgs)
    nr["exc_next"] = nr.takeaways_pg_next - (nr.season + 1).map(lgs)
    top = nr.rank_tpg <= TOP_N
    ctrl = nr.rank_tpg > 2 * TOP_N
    t5 = nr[top]
    find["top5_n"] = int(top.sum())
    find["top5_takeaways_pg"] = [round(float(t5.takeaways_pg.mean()), 2), round(float(t5.takeaways_pg_next.mean()), 2)]
    find["league_takeaways_pg"] = round(float(lgs.mean()), 2)
    ret = lambda d: d[d.rank_tpg <= TOP_N].exc_next.mean() / d[d.rank_tpg <= TOP_N].exc.mean()
    find["top5_excess_retained"] = point_ci(nr, ret)
    find["top5_excess_pg"] = [round(float(t5.exc.mean()), 2), round(float(t5.exc_next.mean()), 2)]
    find["top5_pa_pg"] = [round(float(t5.pa_pg.mean()), 2), round(float(t5.pa_pg_next.mean()), 2)]
    find["top5_pa_change"] = point_ci(nr, lambda d: (d[d.rank_tpg <= TOP_N].pa_pg_next - d[d.rank_tpg <= TOP_N].pa_pg).mean(), d=2)
    find["top5_pa_change_vs_matched"] = point_ci(nr, lambda d: matched_change(d, d.rank_tpg <= TOP_N, d.rank_tpg > 2 * TOP_N), d=2)
    find["top5_matched_n_used"] = int(matched_change(nr, nr.rank_tpg <= TOP_N, nr.rank_tpg > 2 * TOP_N, count=True))
    find["top5_seasons_with_tie_at_cut"] = int(nr.groupby("season").ties_at_cut.first().sum())
    # what the hypothesis predicts: if takeaway points carried nothing while the rest carried like EPA, the top-5 teams'
    # points allowed would rise more than their controls' by (EPA carry share) x (points the takeaways saved this year)
    nxc = nx.set_index(["season", "team"])
    to_dev = nxc.loc[list(zip(nr[nr.rank_tpg <= TOP_N].season, nr[nr.rank_tpg <= TOP_N].team)), "to_rate"].to_numpy()
    saved = -b_same_to * to_dev
    find["top5_takeaway_points_saved"] = round(float(saved.mean()), 2)
    find["top5_gap_predicted_if_fooled"] = round(float(find["carry_share_epa_noto"][0] * saved.mean()), 2)
    find["top5_epa_noto_change"] = point_ci(nr, lambda d: (d[d.rank_tpg <= TOP_N].epa_noto_next - d[d.rank_tpg <= TOP_N].epa_noto).mean(), d=4)
    find["top5_still_top5_next"] = round(float((t5.takeaways_pg_next.values >= nr.groupby("season").takeaways_pg_next.transform(lambda x: x.nlargest(TOP_N).min())[top].values).mean()), 3)
    find["top5_above_league_next"] = round(float((t5.exc_next > 0).mean()), 3)
    find["match_window_ppg"] = MATCH_PA
    t5.assign(team_season=t5.team + " " + t5.season.astype(str))[["season", "team", "takeaways_pg", "takeaways_pg_next", "pa_pg", "pa_pg_next", "epa_noto", "epa_noto_next"]].round(3).to_csv(OUT / "top5_takeaway_seasons.csv", index=False)
    # robustness: other cutoffs, match windows and a per-play ranking
    rob = []
    for label, rk, n_, w, ss in [("Main: top 5, same season, within 1 pt", "tb", 5, 1.0, True), ("Top 3", "tb", 3, 1.0, True),
                                 ("Top 8", "tb", 8, 1.0, True), ("Within 2 pts", "tb", 5, 2.0, True),
                                 ("Within 3 pts", "tb", 5, 3.0, True), ("Top 5 per 100 plays", "to_rate", 5, 1.0, True),
                                 ("Top 5 by interception rate", "int_rate", 5, 1.0, True),
                                 ("Controls from any season", "tb", 5, 1.0, False)]:
        r_ = nr.groupby("season")[rk].rank(ascending=False, method="first")
        tmp = nr.assign(_r=r_.values)
        gap = point_ci(tmp, lambda d, n_=n_, w=w, ss=ss: matched_change(d, d._r <= n_, d._r > 2 * n_, window=w, same_season=ss), d=2)
        h = tmp[tmp._r <= n_]
        rob.append({"version": label, "n": int(matched_change(tmp, tmp._r <= n_, tmp._r > 2 * n_, window=w, same_season=ss, count=True)), "excess_retained": round(float(h.exc_next.mean() / h.exc.mean()), 3),
                    "pa_change": round(float((h.pa_pg_next - h.pa_pg).mean()), 2), "pa_change_vs_matched": gap})
    find["top5_robustness"] = rob
    pd.DataFrame([{**{k: v for k, v in r.items() if k != "pa_change_vs_matched"}, "vs_matched": r["pa_change_vs_matched"][0],
                   "ci_low": r["pa_change_vs_matched"][1], "ci_high": r["pa_change_vs_matched"][2]} for r in rob]).to_csv(OUT / "robustness_top5.csv", index=False)
    # bottom 5, for symmetry
    nr["rank_low"] = nr.groupby("season").takeaways_pg.rank(ascending=True, method="first")
    b5 = nr[nr.rank_low <= TOP_N]
    find["bottom5_takeaways_pg"] = [round(float(b5.takeaways_pg.mean()), 2), round(float(b5.takeaways_pg_next.mean()), 2)]
    find["bottom5_excess_retained"] = point_ci(nr, lambda d: d[d.rank_low <= TOP_N].exc_next.mean() / d[d.rank_low <= TOP_N].exc.mean())
    find["bottom5_pa_change_vs_matched"] = point_ci(nr, lambda d: matched_change(d, d.rank_low <= TOP_N, d.rank_low > 2 * TOP_N), d=2)

    # ---------- 5. players ----------
    pt = player_tables(pbp, last_full)
    a = pt[["gsis_id", "season", "grp", "player", "ints100", "pbu100", "ff100", "plays_on_ball100", "ints", "def_snaps"]]
    pp = a.merge(a.assign(season=a.season - 1), on=["gsis_id", "season"], suffixes=("", "_next"))
    pp = pp[pp.grp == pp.grp_next]
    find["player_seasons"] = len(pt); find["player_pairs"] = len(pp)
    find["player_seasons_range"] = f"2013-{last_full}"
    pr = {}
    for g_, dd in [("DB", pp[pp.grp == "DB"]), ("LB", pp[pp.grp == "LB"])]:
        pr[g_] = {"pairs": len(dd)}
        for c in ["ints100", "pbu100", "plays_on_ball100", "ff100"]:
            pr[g_][c] = point_ci(dd, corr(c, c + "_next"), key="gsis_id")
        pr[g_]["pbu_predicts_next_int"] = point_ci(dd, corr("pbu100", "ints100_next"), key="gsis_id")
        pr[g_]["ballplays_predicts_next_int"] = point_ci(dd, corr("plays_on_ball100", "ints100_next"), key="gsis_id")
    find["player_yoy"] = pr
    d18 = pp[(pp.grp == "DB") & (pp.season >= 2018)]
    find["db_ints100_yoy_2018on"] = point_ci(d18, corr("ints100", "ints100_next"), key="gsis_id")
    find["db_pairs_2018on"] = len(d18)
    db = pp[pp.grp == "DB"]
    big = db[db.ints >= 5]
    find["db_5plus_int_n"] = len(big)
    find["db_5plus_int_mean"] = [round(float(big.ints.mean()), 2), round(float(big.ints_next.mean()), 2)]
    find["db_5plus_int_per100"] = [round(float(big.ints100.mean()), 3), round(float(big.ints100_next.mean()), 3), round(float(db.ints100.mean()), 3)]
    find["db_5plus_int_retained"] = point_ci(db, lambda d: (d[d.ints >= 5].ints100_next.mean() - d.ints100_next.mean()) / (d[d.ints >= 5].ints100.mean() - d.ints100.mean()), key="gsis_id")
    # reconcile with study 07: the same PFR coverage numbers, recomputed here
    from projects.box_score_tax import player_seasons, next_year
    ps, plast = player_seasons()
    cov = ps[(ps.season < plast) & (ps.tgt >= 40) & ps.snap_pos.isin(DBS)].copy()
    cov["int_per_snap"] = cov["int"] / cov.def_snaps
    nc = next_year(cov, ["int_rate", "ypt", "cmp_pct", "int_per_snap"])
    find["pfr_seasons"] = f"2018-{plast - 1}"
    find["pfr_pairs"] = len(nc)
    find["pfr_yoy"] = {c: point_ci(nc, corr(c, c + "_next"), key="pfr_id") for c in ["int_rate", "cmp_pct", "ypt", "int_per_snap"]}
    find["team_vs_player_int"] = {"team_int_rate": yoy["int_rate"], "db_int_per_snap": pr["DB"]["ints100"], "pfr_int_per_target": find["pfr_yoy"]["int_rate"]}

    # ---------- 6. 2026 buy/sell ----------
    early = aggregate(s[s.week <= SPLIT_WEEK], pts[pts.week <= SPLIT_WEEK])
    late = pts[pts.week > SPLIT_WEEK].groupby(["season", "team"]).agg(rest_games=("pa", "size"), rest_pa=("pa", "sum")).reset_index()
    hist = early[early.season <= last_full].merge(late, on=["season", "team"])
    hist["rest_pa_pg"] = hist.rest_pa / hist.rest_games
    find["inseason_n"] = len(hist)
    cand = {"points allowed so far": ["pa_pg"], "takeaways per 100 plays": ["to_rate"], "EPA allowed, no-takeaway plays": ["epa_noto"],
            "EPA + success, no-takeaway plays": ["epa_noto", "succ_noto"],
            "points so far + EPA + success": ["pa_pg", "epa_noto", "succ_noto"],
            "points so far + EPA + success + takeaways": ["pa_pg", "epa_noto", "succ_noto", "to_rate"]}
    tr = hist[hist.season <= 2015]; te = hist[hist.season >= 2016].copy()
    ins = {}
    for name, xs in cand.items():
        te["p_" + name] = fit_predict(tr, te, xs, "rest_pa_pg")
        ins[name] = round(rmse(te.rest_pa_pg, te["p_" + name]), 3)
    find["inseason_oos_rmse"] = ins
    find["inseason_oos_rmse_pa_minus_combo"] = point_ci(te, lambda d: rmse(d.rest_pa_pg, d["p_points allowed so far"]) - rmse(d.rest_pa_pg, d["p_points so far + EPA + success"]))
    find["inseason_oos_rmse_combo_minus_with_to"] = point_ci(te, lambda d: rmse(d.rest_pa_pg, d["p_points so far + EPA + success"]) - rmse(d.rest_pa_pg, d["p_points so far + EPA + success + takeaways"]))
    # takeaway points: how many points per game a defense's takeaway rate is worth against the league, at week 10
    hist["lg_to"] = hist.groupby("season").to_rate.transform("mean")
    hist["to_dev"] = hist.to_rate - hist.lg_to
    hist["lg_epa"] = hist.groupby("season").epa_noto.transform("mean")
    hist["epa_dev"] = hist.epa_noto - hist.lg_epa
    Xw = lambda d: np.column_stack([np.ones(len(d)), d.epa_dev, d.to_dev])
    b_now = np.linalg.lstsq(Xw(hist), hist.pa_pg.to_numpy(), rcond=None)[0]
    find["inseason_pa_per_takeaway_per_100"] = round(float(b_now[2]), 3)
    find["inseason_carry_share_to"] = point_ci(hist, lambda d: np.linalg.lstsq(Xw(d), d.rest_pa_pg.to_numpy(), rcond=None)[0][2]
                                               / np.linalg.lstsq(Xw(d), d.pa_pg.to_numpy(), rcond=None)[0][2])
    find["inseason_carry_share_epa"] = point_ci(hist, lambda d: np.linalg.lstsq(Xw(d), d.rest_pa_pg.to_numpy(), rcond=None)[0][1]
                                                / np.linalg.lstsq(Xw(d), d.pa_pg.to_numpy(), rcond=None)[0][1])
    hist["to_pts"] = b_now[2] * hist.to_dev        # negative: takeaways took points off the board
    hist["flag"] = np.select([hist.to_pts <= -FLAG_PPG, hist.to_pts >= FLAG_PPG], ["sell", "buy"], "")
    hist["pa_change"] = hist.rest_pa_pg - hist.pa_pg

    def flag_test(d, side):
        hit = d[d.flag == side]; ctrl = d[d.flag == ""]
        if hit.empty:
            return np.nan
        cpa, cch, cse = ctrl.pa_pg.to_numpy(), ctrl.pa_change.to_numpy(), ctrl.season.to_numpy()
        gaps = []
        for pa, ch, se in zip(hit.pa_pg, hit.pa_change, hit.season):
            m = (np.abs(cpa - pa) <= 2 * MATCH_PA) & (cse == se)      # same season; a wider window, since a season has few controls at week 10
            if m.any():
                gaps.append(ch - cch[m].mean())
        return float(np.mean(gaps)) if gaps else np.nan
    find["backtest"] = {side: {"n": int((hist.flag == side).sum()),
                               "pa_change": round(float(hist[hist.flag == side].pa_change.mean()), 2),
                               "vs_matched": point_ci(hist, lambda d, side=side: flag_test(d, side), d=2)} for side in ["sell", "buy"]}
    hist[["season", "team", "games", "pa_pg", "rest_pa_pg", "to_rate", "epa_noto", "to_pts", "flag"]].round(3).to_csv(OUT / "backtest_week10_flags.csv", index=False)

    cur = ts[ts.season == last].copy()
    if len(cur) and wk >= 4:
        cur["to_dev"] = cur.to_rate - cur.to_rate.mean()
        cur["to_pts"] = b_now[2] * cur.to_dev
        cur["to_pts_carry"] = cur.to_pts * find["inseason_carry_share_to"][0]
        cur["to_rank"] = cur.to_rate.rank(ascending=False, method="min").astype(int)
        cur["pa_rank"] = cur.pa_pg.rank(method="min").astype(int)
        cur["epa_noto_rank"] = cur.epa_noto.rank(method="min").astype(int)
        lg_to = float(cur.to_rate.mean())
        rel = cur.plays / (cur.plays + k_to)
        cur["to_rate_regressed"] = lg_to + rel * (cur.to_rate - lg_to)
        cur["call"] = np.select([cur.to_pts <= -FLAG_PPG, cur.to_pts >= FLAG_PPG], ["sell", "buy"], "")
        keep = ["team", "games", "pa_pg", "pa_rank", "epa_noto", "epa_noto_rank", "succ_noto", "press_rate", "takeaways", "takeaways_pg",
                "to_rate", "to_rank", "to_rate_regressed", "to_pts", "to_pts_carry", "ints", "int_rate", "ff", "def_rec", "opp_fum_known", "fum_rec_share", "call"]
        cur = cur.sort_values("to_pts")
        cur[keep].round(3).to_csv(OUT / f"buy_sell_{last}.csv", index=False)
        row = lambda r: {"team": r.team, "games": int(r.games), "pa_pg": round(float(r.pa_pg), 1), "pa_rank": int(r.pa_rank),
                         "to_pts": round(float(r.to_pts), 1), "to_pts_carry": round(float(r.to_pts_carry), 1), "takeaways": int(r.takeaways),
                         "to_rank": int(r.to_rank), "ints": int(r.ints), "def_rec": int(r.def_rec), "opp_fum_known": int(r.opp_fum_known),
                         "epa_noto": round(float(r.epa_noto), 3), "epa_noto_rank": int(r.epa_noto_rank)}
        find["sell"] = [row(r) for r in cur[cur.call == "sell"].itertuples()]
        find["buy"] = [row(r) for r in cur[cur.call == "buy"].sort_values("to_pts", ascending=False).itertuples()]
        find["current_r_to_vs_epa_noto"] = round(float(cur.to_rate.corr(cur.epa_noto)), 3)
        find["current_league_to_rate"] = round(lg_to, 3)
        find["current_reliability_to_rate"] = round(float(rel.mean()), 3)
        find["flag_rule"] = {"to_pts_ppg": FLAG_PPG, "sell_n": int((cur.call == "sell").sum()), "buy_n": int((cur.call == "buy").sum())}
        find["current_games_range"] = [int(cur.games.min()), int(cur.games.max())]
    # 2026 interception leaders (individuals) with how much of their rate history says to expect
    c26 = pbp[(pbp.season == last) & (pbp.interception == 1)]
    names = data.load_players()[["gsis_id", "display_name"]].drop_duplicates("gsis_id").set_index("gsis_id").display_name
    lead = c26.groupby(["interception_player_id", "defteam"]).size().sort_values(ascending=False)
    lead = lead[lead >= lead.iloc[min(4, len(lead) - 1)]] if len(lead) else lead
    sc = data.load_snap_counts(last)
    sc = sc[(sc.game_type == "REG") & (sc.week <= wk)].sort_values("week")
    pfr = data.load_players()[["gsis_id", "pfr_id"]].dropna().drop_duplicates("gsis_id").set_index("gsis_id").pfr_id
    now = sc.groupby("pfr_player_id").team.last()
    def team_now(pid, team):
        t = now.get(pfr.get(pid), team)
        return team if t == team else f"{team}, now {t}"
    find["current_int_leaders"] = [[names.get(pid, pid), team_now(pid, team), int(v)] for (pid, team), v in lead.items()]

    # ---------- charts ----------
    order = ["fum_rec_share", "ff_rate", "int_rate", "to_rate", "takeaways_pg", "press_rate", "succ_noto", "epa_noto", "pa_pg"]
    fig, ax = plt.subplots(figsize=(9, 5.6))
    y = np.arange(len(order))
    vals = [yoy[m][0] for m in order]
    cols = [plot.ACCENT2 if m in TAKEAWAY_SIDE else plot.ACCENT for m in order]
    ax.barh(y, vals, color=cols)
    ax.errorbar(vals, y, xerr=[[v - yoy[m][1] for v, m in zip(vals, order)], [yoy[m][2] - v for v, m in zip(vals, order)]], fmt="none", ecolor=plot.INK, capsize=3, lw=1)
    ax.set_yticks(y, [LABELS[m] for m in order]); ax.axvline(0, color=plot.MUTED, lw=.8); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Year-to-year correlation (r), same defense, season N vs N+1")
    ttl = ("Takeaways repeat less than the rest of a defense; fumble recoveries not at all"
           if find["yoy_r_diff"]["epa_noto_minus_to_rate"][1] > 0 and yoy["fum_rec_share"][1] < 0 < yoy["fum_rec_share"][2] else
           "Takeaways repeat less than the rest of a defense" if find["yoy_r_diff"]["epa_noto_minus_to_rate"][1] > 0 else
           "Takeaways repeat about as much as the rest of a defense")
    plot.finish(fig, ax, ttl, f"{len(nx)} team-season pairs, {FIRST}-{last_full}, each season's league average taken out. Orange: takeaway side. Lines: 95% intervals",
                OUT / "stability.png", source=SRC)

    # prediction chart
    pm = ["to_rate", "takeaways_pg", "int_rate", "fum_rec_share", "press_rate", "succ_noto", "epa_noto", "pa_pg"]
    fig, ax = plt.subplots(figsize=(9, 5.4))
    vals = [abs(find["r_next_pa"][m][0]) for m in pm]
    los = [min(abs(find["r_next_pa"][m][1]), abs(find["r_next_pa"][m][2])) if np.sign(find["r_next_pa"][m][1]) == np.sign(find["r_next_pa"][m][2]) else 0 for m in pm]
    his = [max(abs(find["r_next_pa"][m][1]), abs(find["r_next_pa"][m][2])) for m in pm]
    y = np.arange(len(pm))
    ax.barh(y, vals, color=[plot.ACCENT2 if m in TAKEAWAY_SIDE else plot.ACCENT for m in pm])
    ax.errorbar(vals, y, xerr=[np.array(vals) - np.array(los), np.array(his) - np.array(vals)], fmt="none", ecolor=plot.INK, capsize=3, lw=1)
    ax.set_yticks(y, [LABELS[m] for m in pm]); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Correlation with NEXT season's points allowed per game (absolute r)")
    better = find["r_next_pa_diff_epa_noto_minus_to_rate"]
    oos_d = find["oos_rmse_to_minus_epa"]
    ttl = ("EPA allowed without turnovers predicts next year's points a bit better than takeaways" if better[1] > 0 and find["oos_epa_beats_to_in"] == len(find["oos_splits"]) else
           "Next year's points: EPA without turnovers edges takeaways, not in every test" if better[0] > 0 else
           "Takeaways predict next year's points as well as EPA without turnovers")
    plot.finish(fig, ax, ttl, f"{len(nx)} pairs, {FIRST}-{last_full}, league average taken out. Bars: absolute r; intervals that cross zero are drawn from 0",
                OUT / "predict_points.png", source=SRC)

    # top-5 regression chart: the takeaways themselves
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    lgn = round(float(lgs.mean()), 2)
    bars = [("Top-5 takeaway\nseason", find["top5_takeaways_pg"][0], plot.ACCENT2), ("Same defenses,\nnext season", find["top5_takeaways_pg"][1], plot.SOFT),
            ("Bottom-5 takeaway\nseason", find["bottom5_takeaways_pg"][0], plot.ACCENT), ("Same defenses,\nnext season\u00a0", find["bottom5_takeaways_pg"][1], plot.SOFT)]
    ax.bar([x[0] for x in bars], [x[1] for x in bars], color=[x[2] for x in bars])
    ax.axhline(lgn, color=plot.INK, ls="--", lw=1); ax.text(2, lgn + .02, f"league average {lgn:.2f}", va="bottom", ha="center", fontsize=9, color=plot.INK)
    for i, x in enumerate(bars):
        ax.text(i, x[1] - .03, f"{x[1]:.2f}", ha="center", va="top", fontsize=10, color="white", fontweight="bold")
    ax.set_ylabel("Takeaways per game"); ax.grid(axis="x", visible=False); ax.set_ylim(0, max(x[1] for x in bars) * 1.15)
    ax.tick_params(axis="x", labelsize=9)
    r_ = find["top5_excess_retained"]; rb = find["bottom5_excess_retained"]
    plot.finish(fig, ax, f"Top-5 takeaway defenses keep about {100 * r_[0]:.0f}% of their edge the next year",
                f"{find['top5_n']} seasons in each group, {FIRST}-{last_full - 1}. Gap to league average kept: top 5 {100 * r_[0]:.0f}% ({100 * r_[1]:.0f}% to {100 * r_[2]:.0f}%), bottom 5 {100 * rb[0]:.0f}% ({100 * rb[1]:.0f}% to {100 * rb[2]:.0f}%)",
                OUT / "top5_regression.png", source=SRC)

    # the fooled test: next-year change in points allowed, takeaway defenses minus same-points defenses
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    y = np.arange(len(rob))[::-1]
    v = np.array([r["pa_change_vs_matched"][0] for r in rob]); lo = np.array([r["pa_change_vs_matched"][1] for r in rob]); hi = np.array([r["pa_change_vs_matched"][2] for r in rob])
    ax.errorbar(v, y, xerr=[v - lo, hi - v], fmt="o", color=plot.ACCENT2, ecolor=plot.INK, capsize=3, lw=1, ms=7)
    ax.axvline(0, color=plot.MUTED, lw=1)
    pg = find["top5_gap_predicted_if_fooled"]
    ax.axvline(pg, color=plot.ACCENT, ls="--", lw=1.6)
    ax.text(pg + 0.03, 0.5, f"predicted if takeaway\npoints did not carry: {pg:+.2f}", color=plot.ACCENT, fontsize=9, va="center")
    ax.set_yticks(y, [f"{r['version']} (n={r['n']})" for r in rob]); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Extra change in points allowed per game next season\n(top takeaway defenses minus defenses that allowed the same points)")
    main = rob[0]["pa_change_vs_matched"]
    verdict = ("Takeaway defenses give back more points than same-points defenses" if main[1] > 0 else
               "A takeaway year did not make points allowed fall back faster" if main[2] < pg else
               "Inconclusive: the test cannot tell a takeaway year from any good year")
    find["fooled_verdict"] = "held" if main[1] > 0 else "failed" if main[2] < pg else "inconclusive"
    plot.finish(fig, ax, verdict,
                f"Dots: estimate. Lines: 95% intervals (franchises resampled). Dashed: the gap my hypothesis predicts",
                OUT / "fooled_test.png", source=SRC)

    # players chart
    rows = [("Team: INTs per dropback", yoy["int_rate"]), ("DB: INTs per snap", pr["DB"]["ints100"]), ("DB: pass breakups per snap", pr["DB"]["pbu100"]),
            ("DB: forced fumbles per snap", pr["DB"]["ff100"]), ("LB: INTs per snap", pr["LB"]["ints100"]),
            ("PFR: INTs per target (07)", find["pfr_yoy"]["int_rate"]), ("PFR: completion % allowed", find["pfr_yoy"]["cmp_pct"]), ("PFR: yards per target", find["pfr_yoy"]["ypt"])]
    fig, ax = plt.subplots(figsize=(9, 5.4))
    y = np.arange(len(rows))[::-1]
    v = [r[1][0] for r in rows]
    ax.barh(y, v, color=[plot.ACCENT2 if "INT" in r[0] else plot.ACCENT for r in rows])
    ax.errorbar(v, y, xerr=[[a_[1][0] - a_[1][1] for a_ in rows], [a_[1][2] - a_[1][0] for a_ in rows]], fmt="none", ecolor=plot.INK, capsize=3, lw=1)
    ax.set_yticks(y, [r[0] for r in rows]); ax.axvline(0, color=plot.MUTED, lw=.8); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Year-to-year correlation (r)")
    pt_ttl = ("Per snap, a defensive back's interceptions barely repeat; his pass breakups do"
              if pr["DB"]["ints100"][2] < pr["DB"]["pbu100"][1] else "A defensive back's interceptions repeat about like his pass breakups")
    plot.finish(fig, ax, pt_ttl, f"DBs and LBs with {MIN_SNAPS}+ snaps in back-to-back seasons (pbp 2013-{last_full}); PFR rows: 40+ targets, 2018-{plast - 1}. 95% intervals",
                OUT / "player_interceptions.png", source="Data: nflverse play-by-play and snap counts; Pro Football Reference via nflverse. Chart: Dylan Fanelli")

    # current season chart
    if "sell" in find:
        c = cur.sort_values("to_pts", ascending=False)
        fig, ax = plt.subplots(figsize=(8.5, 9))
        colr = [plot.ACCENT2 if k == "sell" else plot.ACCENT if k == "buy" else plot.SOFT for k in c.call]
        ax.barh(c.team, -c.to_pts, color=colr)
        ax.axvline(0, color=plot.MUTED); ax.grid(axis="y", visible=False)
        for xv in (-FLAG_PPG, FLAG_PPG):
            ax.axvline(xv, color=plot.MUTED, ls=":", lw=1)
        ax.set_xlabel("Points per game taken off the board by takeaways, vs a league-average takeaway rate")
        plot.finish(fig, ax, f"{last} through Week {wk}: whose points allowed lean on takeaways",
                    f"Orange: sell ({FLAG_PPG:g}+ points a game from takeaways). Green: buy (takeaways cost {FLAG_PPG:g}+). About {100 * find['inseason_carry_share_to'][0]:.0f}% of it carries to weeks 11+ ({100 * find['inseason_carry_share_to'][1]:.0f}% to {100 * find['inseason_carry_share_to'][2]:.0f}%)",
                    OUT / f"buy_sell_{last}.png", source=SRC)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    with open(OUT / "models.txt", "w") as f:
        for name, m in [("Same-year points allowed per game ~ EPA no-takeaway (SD) + takeaway rate (SD), clustered by franchise", same),
                        ("Next-year points allowed per game ~ this year's EPA no-takeaway (SD) + takeaway rate (SD), clustered by franchise", nxtm)]:
            f.write(f"=== {name}\n{m.summary()}\n\n")
    for k_, v in find.items():
        print(k_, v)


if __name__ == "__main__":
    main()
