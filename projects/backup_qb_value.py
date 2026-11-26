"""12 The Backup Quarterback: what is insurance worth?

Every March a club decides how much to spend on the quarterback who is not supposed to play. This study prices
that decision. How many wins does a team lose when its starter misses a game, how much does the backup's quality
change that, and what is a good backup worth in cap dollars?

Tests:
  1. The cost of a backup start: team efficiency and results in games a backup started, against the same team's
     games with its starter in the same season (team-season fixed effects, opponent and home controls, errors
     clustered by franchise). EPA per dropback is turned into points and points into wins, and the win effect is
     also estimated directly.
  2. How often it happens: backup starts per team-season, 2006 to the last full season, and how that depends on
     how many games the starter missed the season before.
  3. Does the backup matter: the drop against the backup's own prior efficiency (shrunk career EPA per dropback)
     and against his contract (APY as a share of the cap).
  4. Dollars per win from the quarterback market (veteran QB contracts priced against platform-season EPA per
     dropback), with a league-wide cap-per-win check.
  5. What a $2M and a $10M backup buy in expected wins, and the 2026 teams most exposed.
Definitions: the game's quarterback is the passer with the most dropbacks for his team in that game; a team's
season starter is the quarterback who was the game's quarterback most often (ties: more dropbacks).
Data: nflverse play-by-play 2006-2026, Over The Cap contracts via nflverse, nflverse injury reports and depth charts.
Run: python -m projects.backup_qb_value
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from nflan import data, plot
from projects.box_score_tax import ols, CAP_2026

OUT = Path("reports/12-backup-qb-value")
SRC = "Data: nflverse play-by-play, Over The Cap via nflverse. Chart: Dylan Fanelli"
FRANCHISE = {"STL": "LA", "SD": "LAC", "OAK": "LV"}
GAMES = 17                      # value is stated per 17-game season
CHEAP, PRICEY = 2.0, 10.0       # $M APY: the two backups the question asks about
N_BOOT = 1000
# Checked against news on 2026-11-26 for every team that can appear in the exposure chart. The data flag counts any
# missed start; this note says whether the absences were injuries, and what is happening now.
NEWS_CHECKED = "2026-11-26"
NEWS = {
    "CLE": ("injury", "Watson tore his Achilles in 2024 and missed all of 2025; Sanders started in Week 9 of 2026 while Watson was in the concussion protocol"),
    "HOU": ("injury", "Stroud missed games with a concussion in 2025"),
    "DAL": ("injury", "Prescott missed the second half of 2024 with a hamstring injury"),
    "TB": ("injury", "Mayfield missed three 2026 games with a thumb injury and is back"),
    "CHI": ("injury", "Williams missed three 2026 games with a hamstring injury and is back"),
    "JAX": ("injury", "Lawrence missed most of the second half of 2024 (shoulder, concussion)"),
    "SF": ("injury", "Purdy missed 2025 games with a toe injury; an ankle sprain has him uncertain for Week 12"),
    "NYJ": ("none", "Smith left the Week 10 game with an ankle injury and started Week 11; no full games missed"),
    "SEA": ("injury", "Darnold missed 2026 games with an oblique injury; reported on Nov. 25 as expected to start Week 12"),
    "CIN": ("injury", "Burrow missed much of 2025 with a turf toe injury; Flacco returned as his backup"),
    "CAR": ("benching", "Young's 2024 absences were a benching, not an injury"),
    "NO": ("none", "Shough has no missed starts as the starter"),
    "BAL": ("starter out now", "Lamar Jackson is on injured reserve with a fractured thumb; Brissett is starting"),
    "PIT": ("starter changed", "Aaron Rodgers was benched and released on Nov. 25; Rudolph is the starter"),
    "IND": ("starter changed", "Daniel Jones was released on Nov. 20; Richardson is the starter"),
    "MIA": ("starter out now", "Malik Willis is on injured reserve with a groin injury; McCord is starting"),
}
COLS = ["game_id", "season", "season_type", "week", "game_date", "posteam", "defteam", "home_team", "away_team",
        "home_score", "away_score", "spread_line", "qb_dropback", "passer_id", "passer", "epa", "down", "play_type"]


def franchise(s: pd.Series) -> pd.Series:
    return s.replace(FRANCHISE)


# ---------------------------------------------------------------- building blocks (tested in tests/test_reports.py)
def game_qbs(drop: pd.DataFrame) -> pd.DataFrame:
    """Dropbacks per team-game-passer -> one row per team-game naming the game's quarterback (most dropbacks)."""
    per = drop.groupby(["game_id", "team", "passer_id"]).agg(n=("epa", "size"), name=("passer", "last")).reset_index()
    per = per.sort_values(["game_id", "team", "n", "passer_id"], ascending=[True, True, False, True])
    top = per.drop_duplicates(["game_id", "team"]).rename(columns={"passer_id": "qb", "name": "qb_name", "n": "qb_dropbacks"})
    return top


def season_starters(tg: pd.DataFrame) -> pd.DataFrame:
    """The team's season starter: most games as the game's quarterback, ties broken by dropbacks."""
    s = tg.groupby(["season", "team", "qb"]).agg(starts=("game_id", "size"), db=("qb_dropbacks", "sum"),
                                                 name=("qb_name", "last")).reset_index()
    s = s.sort_values(["season", "team", "starts", "db"], ascending=[True, True, False, False])
    return s.drop_duplicates(["season", "team"]).rename(columns={"qb": "starter", "name": "starter_name", "starts": "starter_starts"})[
        ["season", "team", "starter", "starter_name", "starter_starts"]]


def shrink(epa_sum, n, mu, k):
    """Empirical-Bayes mean: (sum + k * mu) / (n + k); with no dropbacks it returns the prior mean."""
    return (np.asarray(epa_sum, float) + k * mu) / (np.asarray(n, float) + k)


def contract_in_force(history, season):
    """APY ($M) and year signed of the deal a player was playing on in a season, from Over The Cap contract_history.
    The latest deal signed on or before the season whose years cover it; an extension covers the years after the deal
    it extends. Returns (nan, nan) when no deal covers the season."""
    if history is None or len(history) == 0:
        return (np.nan, np.nan, None)
    rows, seen = [], set()
    for h in history:
        if h.get("year_signed") is None or h.get("yrs") is None or h.get("apy") is None:
            continue
        key = (h.get("contract_type"), int(h["year_signed"]), int(h["yrs"]), h.get("team"))
        if key in seen:
            continue
        seen.add(key); rows.append(h)
    rows.sort(key=lambda h: h["year_signed"])
    best, end = None, None
    for h in rows:
        y, n = int(h["year_signed"]), int(h["yrs"])
        if h.get("contract_type") == "Extension" and end is not None and end >= y:
            start, e = end + 1, end + n          # the extension starts once the deal it extends runs out
        else:
            start, e = y, y + n - 1
        if start <= season <= e:
            best = h
        end = e
    if best is None:
        return (np.nan, np.nan, None)
    return (float(best["apy"]), float(best["year_signed"]), best.get("contract_type"))


def value_of_upgrade(starts, wins_per_start_cheap, wins_per_start_pricey, usd_per_win):
    """Expected wins saved per season by the better backup, and what they are worth: starts x win gap x $/win.
    The per-start arguments are wins LOST per start (positive numbers)."""
    w = np.asarray(starts) * (np.asarray(wins_per_start_cheap) - np.asarray(wins_per_start_pricey))
    return w, w * np.asarray(usd_per_win)


# ---------------------------------------------------------------- data
def load_games(last_full: int, current: int):
    pbp = data.load_pbp(range(data.FIRST_SEASON, current + 1), columns=COLS)
    pbp = pbp[pbp.season_type == "REG"].copy()
    for c in ["posteam", "defteam", "home_team", "away_team"]:
        pbp[c] = franchise(pbp[c])
    drop = pbp[(pbp.qb_dropback == 1) & pbp.epa.notna() & pbp.down.notna() & pbp.passer_id.notna()].rename(columns={"posteam": "team"})
    g = pbp.drop_duplicates("game_id")[["game_id", "season", "week", "game_date", "home_team", "away_team", "home_score", "away_score", "spread_line"]]
    g = g[g.home_score.notna()]
    rows = []
    for side, opp, pf, pa in (("home_team", "away_team", "home_score", "away_score"), ("away_team", "home_team", "away_score", "home_score")):
        x = g[["game_id", "season", "week", "game_date"]].copy()
        x["team"] = g[side]; x["opp"] = g[opp]; x["pf"] = g[pf]; x["pa"] = g[pa]; x["home"] = int(side == "home_team")
        x["spread"] = g.spread_line if side == "home_team" else -g.spread_line   # points this team was favored by (closing line)
        rows.append(x)
    tg = pd.concat(rows, ignore_index=True)
    tg["margin"] = tg.pf - tg.pa
    tg["win"] = np.where(tg.margin > 0, 1.0, np.where(tg.margin < 0, 0.0, 0.5))
    agg = drop.groupby(["game_id", "team"]).agg(db=("epa", "size"), epa_sum=("epa", "sum")).reset_index()
    tg = tg.merge(agg, on=["game_id", "team"], how="left").merge(game_qbs(drop), on=["game_id", "team"], how="left")
    tg = tg[tg.qb.notna()].copy()
    tg["epa_db"] = tg.epa_sum / tg.db
    # opponent defense: EPA per dropback allowed and point margin per game that season, leaving this game out
    od = tg.groupby(["season", "opp"]).agg(d_sum=("epa_sum", "sum"), d_n=("db", "sum")).reset_index()
    tg = tg.merge(od, on=["season", "opp"])
    tg["opp_def_epa"] = (tg.d_sum - tg.epa_sum) / (tg.d_n - tg.db)
    om = tg.groupby(["season", "team"]).agg(m_sum=("margin", "sum"), m_n=("margin", "size")).reset_index().rename(columns={"team": "opp"})
    tg = tg.merge(om, on=["season", "opp"])
    tg = tg.merge(tg[["game_id", "team", "margin"]].rename(columns={"team": "opp", "margin": "opp_margin_here"}), on=["game_id", "opp"])
    tg["opp_margin_pg"] = (tg.m_sum - tg.opp_margin_here) / (tg.m_n - 1)
    tg = tg.drop(columns=["d_sum", "d_n", "m_sum", "m_n", "opp_margin_here"])
    st = season_starters(tg)
    tg = tg.merge(st, on=["season", "team"])
    tg["backup"] = (tg.qb != tg.starter).astype(int)
    tg["last_game"] = tg.week == tg.groupby(["season", "team"]).week.transform("max")
    return tg, drop, st


def qb_priors(drop: pd.DataFrame):
    """Each passer's career EPA per dropback before each season (from 2006), and the shrinkage constant k.

    k = per-dropback noise variance / between-QB variance of true EPA per dropback (method of moments on QB-seasons
    with 100+ dropbacks), so a career of k dropbacks is half signal."""
    qs = drop.groupby(["passer_id", "season"]).agg(n=("epa", "size"), s=("epa", "sum"), ss=("epa", lambda x: (x ** 2).sum())).reset_index()
    big = qs[qs.n >= 100].copy()
    big["m"] = big.s / big.n
    mu_all = big.s.sum() / big.n.sum()
    play_var = float((drop.epa.var()))
    var_obs = np.average((big.m - mu_all) ** 2, weights=big.n)
    var_noise = np.average(play_var / big.n, weights=big.n)
    k = play_var / max(var_obs - var_noise, 1e-6)
    qs = qs.sort_values(["passer_id", "season"])
    qs["cum_n"] = qs.groupby("passer_id").n.cumsum() - qs.n
    qs["cum_s"] = qs.groupby("passer_id").s.cumsum() - qs.s
    return qs[["passer_id", "season", "n", "s", "cum_n", "cum_s"]], float(k), float(play_var)


def prior_for(qs, ids, seasons, mu, k):
    """Shrunk career EPA per dropback before the season, and career dropbacks (seasons before it, from 2006)."""
    key = pd.DataFrame({"passer_id": list(ids), "season": np.asarray(seasons, int), "_i": range(len(ids))})
    q = qs[["passer_id", "season", "n", "s"]].sort_values(["passer_id", "season"]).copy()
    q["cn"] = q.groupby("passer_id").n.cumsum(); q["cs"] = q.groupby("passer_id").s.cumsum()
    q["season"] = q.season.astype(int)
    m = pd.merge_asof(key.sort_values("season"), q[["passer_id", "season", "cn", "cs"]].sort_values("season"),
                      on="season", by="passer_id", allow_exact_matches=False).sort_values("_i")
    n = m.cn.fillna(0).to_numpy(float); sm_ = m.cs.fillna(0).to_numpy(float)
    return shrink(sm_, n, mu, k), n


# ---------------------------------------------------------------- models
def fe_model(d: pd.DataFrame, y: str, extra=(), opp="opp_def_epa"):
    """y on backup (+ interactions) with team-season fixed effects, home and opponent controls; errors clustered by franchise."""
    X = d[["backup", *extra, "home", opp]].astype(float)
    X = pd.concat([X, pd.get_dummies(d.ts, prefix="ts", drop_first=True, dtype=float)], axis=1)
    return ols(d[y].astype(float), X, groups=d.team)


def fe_beta(d, y, cols, opp="opp_def_epa"):
    """Point estimates only (fast, for the bootstrap): demean within team-season, then least squares."""
    X = d[["backup", *cols, "home", opp]].astype(float)
    Xd = X - X.groupby(d.ts.values).transform("mean")
    yd = d[y].astype(float) - d[y].astype(float).groupby(d.ts.values).transform("mean")
    b = np.linalg.lstsq(Xd.values, yd.values, rcond=None)[0]
    return dict(zip(X.columns, b))


def boot_franchises(d: pd.DataFrame, fn, n=N_BOOT, seed=12):
    """Resample franchises with all their seasons; team-seasons get new ids so a franchise drawn twice is two clusters."""
    rng = np.random.default_rng(seed)
    teams = d.team.unique()
    by = {t: d[d.team == t] for t in teams}
    out = []
    for _ in range(n):
        pick = rng.choice(teams, len(teams))
        parts = []
        for j, t in enumerate(pick):
            p = by[t].copy(); p["ts"] = p.ts + f"#{j}"; p["team"] = p.team + f"#{j}"; parts.append(p)
        out.append(fn(pd.concat(parts, ignore_index=True)))
    return out


def pct_ci(x, lo=2.5, hi=97.5, d=4):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return [round(float(np.percentile(x, lo)), d), round(float(np.percentile(x, hi)), d)]


def trip(point, draws, d=4):
    return [round(float(point), d)] + pct_ci(draws, d=d)


# ---------------------------------------------------------------- main
def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    current = data.latest_season_available()
    data.pbp_path(current, refresh=True)
    last_full = current - 1
    tg_all, drop, st = load_games(last_full, current)
    pulled = dt.date.today().isoformat()
    tg = tg_all[tg_all.season <= last_full].copy()
    tg["ts"] = tg.season.astype(str) + tg.team
    find = {"seasons": f"{data.FIRST_SEASON}-{last_full}", "current_season": current, "pbp_pulled": pulled,
            "team_games": int(len(tg)), "team_seasons": int(tg.ts.nunique()), "cap_2026_musd": CAP_2026,
            "cheap_musd": CHEAP, "pricey_musd": PRICEY}
    cur = tg_all[tg_all.season == current]
    find["current_through_week"] = int(cur.week.max()); find["current_last_game"] = str(cur.game_date.max())

    # ---------- 1. how often: backup starts per team-season
    ts = tg.groupby(["season", "team", "ts"]).agg(games=("game_id", "size"), bstarts=("backup", "sum"),
                                                 starter=("starter", "first"), starter_name=("starter_name", "first")).reset_index()
    ts["bstarts17"] = ts.bstarts * GAMES / ts.games
    find["backup_games"] = int(tg.backup.sum())
    find["backup_share_of_games"] = round(float(tg.backup.mean()), 4)
    rate_draws = boot_franchises(ts.assign(ts=ts.ts), lambda d: d.bstarts.sum() / d.games.sum(), n=N_BOOT)
    r = tg.backup.mean()
    find["backup_starts_per_17"] = trip(GAMES * r, GAMES * np.array(rate_draws), 2)
    recent = ts[ts.season >= last_full - 9]
    find["recent_label"] = f"{last_full - 9}-{last_full}"
    find["backup_starts_per_17_recent"] = round(float(GAMES * recent.bstarts.sum() / recent.games.sum()), 2)
    find["share_seasons_with_backup_start"] = round(float((ts.bstarts > 0).mean()), 3)
    find["share_seasons_4plus"] = round(float((ts.bstarts >= 4).mean()), 3)
    find["dist_backup_starts"] = {str(k): int(v) for k, v in ts.bstarts.clip(upper=10).value_counts().sort_index().items()}
    find["by_season_per_17"] = {str(int(s)): round(float(GAMES * g.bstarts.sum() / g.games.sum()), 2) for s, g in ts.groupby("season")}

    # starter's games missed the season before (after his first start, as his team's season starter)
    ms_hist = missed_as_starter(tg, set(zip(drop.game_id, drop.passer_id)))
    pv = ms_hist.sort_values("missed", ascending=False).drop_duplicates(["season", "qb"])
    ts2 = ts.merge(pv[["season", "qb", "missed"]].assign(season=pv.season + 1).rename(columns={"qb": "starter", "missed": "prev_missed"}),
                   on=["season", "starter"], how="left")

    def grp(x):
        if not np.isfinite(x):
            return "not a season starter the year before"
        return "missed 0 the year before" if x == 0 else ("missed 1-3" if x <= 3 else "missed 4+")
    ts2["history"] = ts2.prev_missed.map(grp)
    ts2 = ts2[ts2.season > data.FIRST_SEASON]
    order = ["missed 0 the year before", "missed 1-3", "missed 4+", "not a season starter the year before"]
    hist = {}
    for h in order:
        g = ts2[ts2.history == h]
        draws = boot_franchises(g, lambda d: GAMES * d.bstarts.sum() / d.games.sum(), n=N_BOOT)
        hist[h] = {"n": int(len(g)), "per_17": trip(GAMES * g.bstarts.sum() / g.games.sum(), draws, 2),
                   "share_4plus": round(float((g.bstarts >= 4).mean()), 3)}
    find["starts_by_history"] = hist
    ts2[["season", "team", "starter_name", "games", "bstarts", "prev_missed", "history"]].to_csv(OUT / "team_seasons.csv", index=False)

    # ---------- 2. the cost of a backup start, within team-season
    both = tg.groupby("ts").backup.transform(lambda b: (b.sum() > 0) & (b.sum() < len(b)))
    d = tg[both].copy()
    find["fe_team_seasons"] = int(d.ts.nunique()); find["fe_games"] = int(len(d)); find["fe_backup_games"] = int(d.backup.sum())
    raw = d.groupby("backup").agg(epa_db=("epa_db", "mean"), pf=("pf", "mean"), margin=("margin", "mean"), win=("win", "mean"),
                                  db=("db", "mean")).round(4)
    find["raw_means"] = {("backup" if k else "starter"): v for k, v in raw.to_dict("index").items()}
    models = {}
    eff = {}
    for y, opp in (("epa_db", "opp_def_epa"), ("pf", "opp_margin_pg"), ("margin", "opp_margin_pg"), ("win", "opp_margin_pg")):
        m = fe_model(d, y, opp=opp); models[y] = m
        eff[y] = [round(float(m.params["backup"]), 4)] + [round(float(x), 4) for x in m.conf_int().loc["backup"]]
    find["effect"] = eff
    # conversions: EPA per dropback -> points (EPA is in points; x dropbacks per game), points -> wins (team-season fit)
    full_ts = tg.groupby("ts").agg(margin_pg=("margin", "mean"), winpct=("win", "mean"), team=("team", "first")).reset_index()
    wm = ols(full_ts.winpct, full_ts[["margin_pg"]], groups=full_ts.team)
    wpp = float(wm.params["margin_pg"])
    find["wins_per_point_margin"] = [round(wpp, 4)] + [round(float(x), 4) for x in wm.conf_int().loc["margin_pg"]]
    find["dropbacks_per_game_backup"] = round(float(d[d.backup == 1].db.mean()), 1)
    find["epa_points_per_game"] = round(eff["epa_db"][0] * find["dropbacks_per_game_backup"], 2)
    find["wins_per_start_via_epa"] = round(find["epa_points_per_game"] * wpp, 3)
    find["wins_per_start_via_margin"] = round(eff["margin"][0] * wpp, 3)
    find["wins_per_start_direct"] = eff["win"][0]

    def cost(dd):
        bm = fe_beta(dd, "margin", [], opp="opp_margin_pg")["backup"]
        be = fe_beta(dd, "epa_db", [])["backup"]
        bw = fe_beta(dd, "win", [], opp="opp_margin_pg")["backup"]
        return be, bm, bw
    cb = np.array(boot_franchises(d, cost))
    wpp_draws = np.array(boot_franchises(full_ts.rename(columns={"ts": "ts"}), lambda x: np.polyfit(x.margin_pg, x.winpct, 1)[0]))
    per_start_win = cb[:, 1] * wpp_draws                      # wins lost per backup start (margin route), draws
    find["wins_per_start_via_margin_ci"] = pct_ci(per_start_win, d=3)
    find["effect_boot"] = {"epa_db": pct_ci(cb[:, 0]), "margin": pct_ci(cb[:, 1], d=2), "win": pct_ci(cb[:, 2], d=3)}

    # robustness: the margin and win cost under other definitions
    inj = injury_out(data.FIRST_SEASON, last_full)
    d = d.merge(inj, left_on=["season", "week", "starter"], right_on=["season", "week", "gsis_id"], how="left")
    d["starter_out"] = d.report_status.isin(["Out", "Doubtful"])
    first_b = d[d.backup == 1].groupby("ts").week.min(); last_s = d[d.backup == 0].groupby("ts").week.max()
    returned = set(first_b.index[(first_b < last_s.reindex(first_b.index)).fillna(False)])
    st_share = d.groupby("ts").backup.mean()
    versions = {
        "all backup starts (base)": d,
        "final week dropped": d[~d.last_game],
        "starter returned later": d[d.ts.isin(returned)],
        "starter started half or more": d[d.ts.isin(st_share.index[st_share <= 0.5])],
        "starter listed Out or Doubtful (2009+)": d[(d.season >= 2009) & ((d.backup == 0) | d.starter_out)],
        f"{last_full - 9}-{last_full}": d[d.season >= last_full - 9],
        "no opponent control": d,
        "pregame spread as the opponent control": d[d.spread.notna()],
    }
    rob = []
    for name, dd in versions.items():
        keep = dd.groupby("ts").backup.transform(lambda b: (b.sum() > 0) & (b.sum() < len(b)))
        dd = dd[keep]
        opp = "opp_margin_pg"
        if name == "no opponent control":
            dd = dd.assign(zero=0.0); opp = "zero"
            X = dd[["backup", "home"]].astype(float)
            X = pd.concat([X, pd.get_dummies(dd.ts, prefix="ts", drop_first=True, dtype=float)], axis=1)
            mm = ols(dd.margin.astype(float), X, groups=dd.team)
            me = ols(dd.epa_db.astype(float), X, groups=dd.team)
        elif name.startswith("pregame spread"):
            mm = fe_model(dd, "margin", opp="spread"); me = fe_model(dd, "epa_db", opp="spread")
        else:
            mm = fe_model(dd, "margin", opp=opp); me = fe_model(dd, "epa_db")
        ci_m = mm.conf_int().loc["backup"]
        rob.append({"version": name, "team_seasons": int(dd.ts.nunique()), "backup_games": int(dd.backup.sum()),
                    "epa_db": round(float(me.params["backup"]), 3), "margin": round(float(mm.params["backup"]), 2),
                    "margin_lo": round(float(ci_m.iloc[0]), 2), "margin_hi": round(float(ci_m.iloc[1]), 2),
                    "wins_per_start": round(float(mm.params["backup"]) * wpp, 3)})
    rob = pd.DataFrame(rob); rob.to_csv(OUT / "robustness_cost_per_start.csv", index=False)
    find["robustness"] = rob.to_dict("records")
    find["injury_report_backup_games"] = int(versions["starter listed Out or Doubtful (2009+)"].backup.sum())

    # ---------- 3. does the backup matter? prior efficiency and contract
    qs, k, play_var = qb_priors(drop[drop.season <= last_full])
    find["shrink_k_dropbacks"] = round(k, 0)
    bk = d[d.backup == 1]
    mu_b = float(bk.epa_sum.sum() / bk.db.sum())  # what backups do when they start: the prior mean for an unknown backup
    find["backup_epa_db_when_starting"] = round(mu_b, 3)
    mu_s = float(d[d.backup == 0].epa_sum.sum() / d[d.backup == 0].db.sum())
    d["bp"], d["bp_n"] = prior_for(qs, d.qb.values, d.season.values, mu_b, k)
    d["sp"], d["sp_n"] = prior_for(qs, d.starter.values, d.season.values, mu_s, k)
    find["backup_prior_sd"] = round(float(d[d.backup == 1].bp.std()), 3)
    find["backup_prior_n_zero_share"] = round(float((d[d.backup == 1].bp_n == 0).mean()), 3)
    d["bp_c"] = np.where(d.backup == 1, d.bp - mu_b, 0.0)
    d["sp_c"] = np.where(d.backup == 1, d.sp - mu_s, 0.0)
    qm = {}
    for y, opp in (("epa_db", "opp_def_epa"), ("margin", "opp_margin_pg")):
        m = fe_model(d, y, extra=("bp_c", "sp_c"), opp=opp); models[f"{y}_quality"] = m
        qm[y] = {c: [round(float(m.params[c]), 4)] + [round(float(x), 4) for x in m.conf_int().loc[c]] for c in ("backup", "bp_c", "sp_c")}
    find["quality_model"] = qm
    # a backup 0.10 EPA per dropback better (prior), in margin and wins per start
    find["margin_per_010_backup_prior"] = [round(0.1 * v, 2) for v in qm["margin"]["bp_c"]]
    find["wins_per_start_per_010_backup_prior"] = [round(0.1 * v * wpp, 3) for v in qm["margin"]["bp_c"]]

    # contract in force for each backup start (APY as % of the cap in the year signed)
    con = data.load_contracts()
    con = con[con.position == "QB"]
    hist_by = con.dropna(subset=["gsis_id"]).groupby("gsis_id").contract_history.apply(lambda s: [h for x in s for h in (x if x is not None else [])])
    caps = cap_by_year(con)
    find["cap_by_year_musd"] = {str(k_): round(v, 1) for k_, v in caps.items()}
    bs = d[d.backup == 1][["ts", "season", "team", "qb", "qb_name"]].drop_duplicates(["ts", "qb"])
    apy = [contract_in_force(hist_by.get(q), s) for q, s in zip(bs.qb, bs.season)]
    bs["apy"] = [a[0] for a in apy]; bs["signed"] = [a[1] for a in apy]; bs["ctype"] = [a[2] for a in apy]
    bs["apy_pct"] = 100 * bs.apy / bs.signed.map(caps)
    bs["rookie_deal"] = bs.ctype.isin(["Drafted", "UDFA"])
    d = d.merge(bs[["ts", "qb", "apy_pct", "rookie_deal"]], on=["ts", "qb"], how="left")
    find["backup_contracts_found_share"] = round(float(d[d.backup == 1].apy_pct.notna().mean()), 3)
    dc = d[(d.backup == 0) | d.apy_pct.notna()].copy()
    keep = dc.groupby("ts").backup.transform(lambda b: (b.sum() > 0) & (b.sum() < len(b)))
    dc = dc[keep].copy()
    mean_pct = float(dc[dc.backup == 1].apy_pct.mean())
    dc["apy_c"] = np.where(dc.backup == 1, dc.apy_pct - mean_pct, 0.0)
    dc["sp_c"] = np.where(dc.backup == 1, dc.sp - mu_s, 0.0)
    mc = fe_model(dc, "margin", extra=("apy_c", "sp_c"), opp="opp_margin_pg"); models["margin_contract"] = mc
    dc["bp_c"] = np.where(dc.backup == 1, dc.bp - mu_b, 0.0)
    mcr = fe_model(dc, "margin", extra=("apy_c", "bp_c", "sp_c"), opp="opp_margin_pg"); models["margin_contract_and_record"] = mcr
    me_c = fe_model(dc, "epa_db", extra=("apy_c", "sp_c")); models["epa_contract"] = me_c
    find["contract_model"] = {"team_seasons": int(dc.ts.nunique()), "backup_games": int(dc.backup.sum()), "mean_apy_pct": round(mean_pct, 2),
                              "margin_per_pct_cap": [round(float(mc.params["apy_c"]), 3)] + [round(float(x), 3) for x in mc.conf_int().loc["apy_c"]],
                              "margin_per_pct_cap_with_record": [round(float(mcr.params["apy_c"]), 3)] + [round(float(x), 3) for x in mcr.conf_int().loc["apy_c"]],
                              "epa_per_pct_cap": [round(float(me_c.params["apy_c"]), 4)] + [round(float(x), 4) for x in me_c.conf_int().loc["apy_c"]]}
    # does pay buy prior efficiency? backup prior on APY share, one row per backup team-season
    pq = d[d.backup == 1].drop_duplicates(["ts", "qb"]).dropna(subset=["apy_pct"])
    pm = ols(pq.bp, pq[["apy_pct"]], groups=pq.team)
    find["prior_per_pct_cap"] = [round(float(pm.params["apy_pct"]), 4)] + [round(float(x), 4) for x in pm.conf_int().loc["apy_pct"]]
    find["prior_backups_n"] = int(len(pq))

    # ---------- 4. dollars per win from the QB market
    usd_win, usd_draws, qbm = dollars_per_win(drop[drop.season <= current], con, caps, wpp, wpp_draws, k)
    models["qb_market"] = qbm.pop("_model", None); find.update(qbm)
    find["usd_per_win_qb_market"] = [round(usd_win, 2)] + pct_ci(usd_draws, d=2)
    # check: league-wide cap above a minimum roster, over wins above a replacement team (assumptions stated)
    find["usd_per_win_league_check"] = league_check()

    # ---------- 5. $2M vs $10M backup
    pct_cheap, pct_pricey = 100 * CHEAP / CAP_2026, 100 * PRICEY / CAP_2026
    gap_pct = pct_pricey - pct_cheap
    def contract_draw(dd):
        b = fe_beta(dd, "margin", ["apy_c", "sp_c"], opp="opp_margin_pg")
        return b["apy_c"]
    cdraws = np.array(boot_franchises(dc, contract_draw))
    find["contract_model"]["margin_per_pct_cap_boot"] = pct_ci(cdraws, d=3)
    starts = find["backup_starts_per_17"][0]
    starts_draws = GAMES * np.array(rate_draws)
    wins_gap_draws = starts_draws * cdraws * gap_pct * wpp_draws         # wins saved per season by the $10M backup
    wins_gap = starts * float(mc.params["apy_c"]) * gap_pct * wpp
    rng = np.random.default_rng(3)
    usd_pair = rng.choice(usd_draws, len(wins_gap_draws))
    _, val_draws = value_of_upgrade(starts_draws, np.zeros_like(cdraws), -cdraws * gap_pct * wpp_draws, usd_pair)
    find["upgrade"] = {"apy_pct_cheap": round(pct_cheap, 2), "apy_pct_pricey": round(pct_pricey, 2),
                       "margin_per_start_gap": trip(float(mc.params["apy_c"]) * gap_pct, cdraws * gap_pct, 2),
                       "wins_per_season": trip(wins_gap, wins_gap_draws, 3),
                       "value_musd": trip(wins_gap * usd_win, val_draws, 2),
                       "cost_gap_musd": PRICEY - CHEAP,
                       "share_draws_value_above_cost": round(float(np.mean(val_draws > PRICEY - CHEAP)), 3),
                       "share_draws_positive": round(float(np.mean(wins_gap_draws > 0)), 3)}
    # the same through quality: what the APY gap buys in prior efficiency, times what prior efficiency is worth
    qfull = np.array(boot_franchises(d, lambda dd: [fe_beta(dd, "margin", ["bp_c", "sp_c"], opp="opp_margin_pg")[c] for c in ("backup", "bp_c", "sp_c")]))
    qd = qfull[:, 1]
    eff_gap = float(pm.params["apy_pct"]) * gap_pct
    pq_b = pq.assign(ts=pq.ts)
    pm_draws = np.array(boot_franchises(pq_b, lambda x: np.polyfit(x.apy_pct, x.bp, 1)[0]))
    find["upgrade_via_quality"] = {"prior_gap": round(eff_gap, 4),
                                   "wins_per_season": trip(starts * eff_gap * float(qm["margin"]["bp_c"][0]) * wpp,
                                                           starts_draws * pm_draws * gap_pct * qd * wpp_draws, 3)}
    # break-even: expected backup starts at which the $8M gap pays for itself (contract route)
    wpg = float(mc.params["apy_c"]) * gap_pct * wpp
    find["upgrade"]["breakeven_starts"] = round((PRICEY - CHEAP) / (wpg * usd_win), 1) if wpg > 0 else None
    lg = find["usd_per_win_league_check"]["replacement_3_wins"]
    find["upgrade"]["value_musd_league_price"] = round(wins_gap * lg, 2)
    find["upgrade"]["breakeven_starts_league_price"] = round((PRICEY - CHEAP) / (wpg * lg), 1) if wpg > 0 else None
    # robustness of the $2M vs $10M gap: other samples of backup starts and contracts, and both prices per win
    vers = {"base": dc, "veteran deals only": dc[(dc.backup == 0) | (dc.rookie_deal == False)],  # noqa: E712
            "final week dropped": dc[~dc.last_game], "starter returned later": dc[dc.ts.isin(returned)],
            f"{last_full - 9}-{last_full}": dc[dc.season >= last_full - 9],
            "starter listed Out or Doubtful (2009+)": dc[(dc.season >= 2009) & ((dc.backup == 0) | dc.starter_out)]}
    urob = []
    for name, dd in vers.items():
        dd = dd[dd.groupby("ts").backup.transform(lambda b: (b.sum() > 0) & (b.sum() < len(b)))].copy()
        mean_v = float(dd[dd.backup == 1].apy_pct.mean())
        dd["apy_c"] = np.where(dd.backup == 1, dd.apy_pct - mean_v, 0.0)
        mv = fe_model(dd, "margin", extra=("apy_c", "sp_c"), opp="opp_margin_pg")
        lo_, hi_ = mv.conf_int().loc["apy_c"]
        w = starts * gap_pct * wpp
        urob.append({"version": name, "team_seasons": int(dd.ts.nunique()), "backup_games": int(dd.backup.sum()),
                     "margin_per_pct_cap": round(float(mv.params["apy_c"]), 3), "lo": round(float(lo_), 3), "hi": round(float(hi_), 3),
                     "wins_per_season_gap": round(float(mv.params["apy_c"]) * w, 3),
                     "value_musd_qb_market": round(float(mv.params["apy_c"]) * w * usd_win, 2),
                     "value_musd_league": round(float(mv.params["apy_c"]) * w * lg, 2)})
    urob = pd.DataFrame(urob); urob.to_csv(OUT / "robustness_two_vs_ten.csv", index=False)
    find["upgrade_robustness"] = urob.to_dict("records")

    # ---------- 6. 2026 exposure: rest-of-season rate, measured the same way in past seasons
    played = set(zip(drop.game_id, drop.passer_id))
    ms = missed_as_starter(tg_all, played)
    cut = int(np.median(tg_all[tg_all.season == current].groupby("team").size()))
    ros = rest_of_season(tg_all, ms, data.FIRST_SEASON + 2, last_full, cut, played)
    ros.to_csv(OUT / "rest_of_season_history.csv", index=False)
    rates, rate_draws_ros = {}, {}
    for flag in (False, True):
        g = ros[ros.history == flag]
        dr = boot_franchises(g.assign(ts=g.season.astype(str) + g.team), lambda x: x.other.sum() / x.left.sum())
        rates[flag] = {"n": int(len(g)), "rate": trip(g.other.sum() / g.left.sum(), dr, 4), "share_any": round(float((g.other > 0).mean()), 3)}
        rate_draws_ros[flag] = np.array(dr)
    find["rest_of_season"] = {"cut_game": cut, "seasons": f"{data.FIRST_SEASON + 2}-{last_full}",
                              "no_history": rates[False], "history": rates[True]}
    exp = exposure(tg_all, drop, k, mu_b, mu_s, hist_by, find, qm, wpp, current, ms, rates, (qfull, rate_draws_ros, wpp_draws), played)
    exp.to_csv(OUT / f"exposure_{current}.csv", index=False)
    elig = exp[~exp.already_on_backup]
    find["spotlight"] = elig[elig.news_reason == "injury"].head(5)[["team", "starter", "backup", "exp_backup_starts_rest", "wins_lost_per_start",
                                                                   "exp_wins_lost_rest", "exp_wins_lost_rest_lo", "exp_wins_lost_rest_hi", "backup_prior_epa", "news_note"]].round(3).to_dict("records")
    find["already_on_backup"] = exp[exp.already_on_backup][["team", "starter", "season_starter_so_far", "news_note"]].to_dict("records")
    find["news_checked"] = NEWS_CHECKED
    chart = elig.head(10)
    find["chart_teams"] = chart.team.tolist()
    find["chart_notes_other"] = chart[~chart.team.isin([x["team"] for x in find["spotlight"]])][["team", "starter", "backup", "exp_wins_lost_rest", "news_note"]].round(3).to_dict("records")
    find["exposure_max_eligible"] = round(float(-elig.exp_wins_lost_rest.min()), 3)
    find["exposure_min_eligible"] = round(float(-elig.exp_wins_lost_rest.max()), 3)
    find["exposure_rows"] = exp.round(3).to_dict("records")

    # ---------- figures
    fig_cost(rob, find)
    fig_starts(ts, find, hist)
    fig_quality(d, find, wpp)
    fig_upgrade(find)
    fig_exposure(exp, find)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    with open(OUT / "models.txt", "w") as fh:
        fh.write(f"Data pulled {pulled}. Team-season fixed effects are in each model but not printed.\n\n")
        for name, m in models.items():
            if m is None:
                continue
            keep_rows = [i for i in m.params.index if not str(i).startswith("ts_")]
            tab = pd.DataFrame({"coef": m.params[keep_rows], "se": m.bse[keep_rows], "p": m.pvalues[keep_rows]}).round(4)
            fh.write(f"=== {name} (n = {int(m.nobs)}, clustered by franchise)\n{tab.to_string()}\n\n")
        tab = pd.DataFrame({"coef": wm.params, "se": wm.bse, "p": wm.pvalues}).round(4)
        fh.write(f"=== win% ~ point margin per game (n = {int(wm.nobs)} team-seasons, clustered by franchise)\n{tab.to_string()}\n")
    for kk, v in find.items():
        if kk != "exposure_rows":
            print(kk, v)


def injury_out(first, last):
    rows = []
    for s in range(max(first, 2009), last + 1):
        try:
            i = data._release("injuries", f"injuries_{s}.parquet")
        except Exception:
            continue
        i = i[(i.game_type == "REG") & (i.position == "QB")][["season", "week", "gsis_id", "report_status"]]
        rows.append(i)
    return pd.concat(rows).drop_duplicates(["season", "week", "gsis_id"]) if rows else pd.DataFrame(columns=["season", "week", "gsis_id", "report_status"])


def cap_by_year(con: pd.DataFrame) -> dict:
    """The salary cap each year, from Over The Cap: APY / (APY share of the cap) on deals of 5%+ of the cap, median by year signed.
    2026 is set to the announced cap."""
    c = con[(con.apy_cap_pct >= 0.05) & con.apy.notna()]
    caps = (c.apy / c.apy_cap_pct).groupby(c.year_signed).median().to_dict()
    caps = {int(k): float(v) for k, v in caps.items()}
    caps[2026] = CAP_2026
    for y in range(2000, 2027):
        if y not in caps:
            caps[y] = caps.get(y - 1, np.nan)
    return caps


def dollars_per_win(drop, con, caps, wpp, wpp_draws, k):
    """Veteran QB deals (2011+, 2%+ of the cap, signed by a QB with 200+ platform dropbacks) priced on platform-season
    EPA per dropback (shrunk) and dropbacks. $ per +0.10 EPA per dropback over a 17-game season, divided by the wins
    that +0.10 is worth (0.10 x dropbacks per game x 17 x wins per point of margin per game)."""
    qs = drop.groupby(["passer_id", "season"]).agg(n=("epa", "size"), s=("epa", "sum")).reset_index()
    mu = qs.s.sum() / qs.n.sum()
    # a season's EPA per dropback is shrunk toward the league with the prior k estimated in qb_priors
    qs["epa_s"] = shrink(qs.s, qs.n, mu, k)
    c = con[con.gsis_id.notna() & con.apy_cap_pct.notna()].copy()
    rookie = c.draft_year.notna() & (c.year_signed == c.draft_year)
    c = c[~rookie & (c.year_signed >= 2011) & (c.apy_cap_pct >= 0.02)]
    c = c.sort_values(["years", "apy"], ascending=False, kind="mergesort").drop_duplicates(["gsis_id", "year_signed"])
    m = c.merge(qs.rename(columns={"passer_id": "gsis_id"}).assign(year_signed=lambda x: x.season + 1), on=["gsis_id", "year_signed"])
    m = m[m.n >= 200].copy()
    m["pct"] = 100 * m.apy_cap_pct
    mod = ols(m.pct, m[["epa_s", "n"]], groups=m.gsis_id)
    db_pg = float(drop.groupby(["game_id", "team"]).size().mean())
    wins_per_010 = 0.10 * db_pg * GAMES * wpp
    usd_per_010 = float(mod.params["epa_s"]) * 0.10 / 100 * CAP_2026
    rng = np.random.default_rng(9)
    ids = m.gsis_id.unique(); by = {i: m[m.gsis_id == i] for i in ids}
    draws = []
    for b in range(N_BOOT):
        mm = pd.concat([by[i] for i in rng.choice(ids, len(ids))])
        A = np.column_stack([np.ones(len(mm)), mm.epa_s, mm.n])
        beta = np.linalg.lstsq(A, mm.pct.values, rcond=None)[0][1]
        w = 0.10 * db_pg * GAMES * wpp_draws[b % len(wpp_draws)]
        draws.append(beta * 0.10 / 100 * CAP_2026 / w)
    out = {"qb_market_contracts": int(len(m)), "qb_market_players": int(m.gsis_id.nunique()),
           "qb_market_pct_per_010": [round(float(mod.params["epa_s"]) * 0.1, 3)] + [round(float(x) * 0.1, 3) for x in mod.conf_int().loc["epa_s"]],
           "musd_per_010_epa": round(usd_per_010, 2), "wins_per_010_epa_season": round(wins_per_010, 2),
           "dropbacks_per_game": round(db_pg, 1), "_model": mod}
    return usd_per_010 / wins_per_010, np.array(draws), out


def league_check():
    """Cap above a minimum-salary roster per team, divided by wins above a replacement-level team (stated assumptions)."""
    roster_min = 53 * 0.885          # 2026 minimum for a first-year player is $0.885M (CBA); veterans earn more, so this is a floor
    above = 0.98 * CAP_2026 - roster_min
    out = {}
    for rep in (2.0, 3.0, 4.0):
        out[f"replacement_{rep:g}_wins"] = round(above / (GAMES / 2 - rep), 1)
    out["roster_min_musd"] = round(roster_min, 1); out["cap_spent_share"] = 0.98
    return out


def missed_as_starter(tg: pd.DataFrame, played: set) -> pd.DataFrame:
    """For each season a QB was his team's season starter: team games after his first start in which he had no dropback.
    Games before his first start are left out (a mid-season takeover is not missed games), and a game he left hurt
    after playing is not counted as missed."""
    st = season_starters(tg)
    rows = []
    g = tg[["season", "team", "week", "game_id", "qb"]].merge(st[["season", "team", "starter"]], on=["season", "team"]).sort_values(["season", "team", "week"])
    for (s_, t), x in g.groupby(["season", "team"]):
        q = x.starter.iloc[0]
        mine = np.flatnonzero(x.qb.values == q)
        rows.append({"season": s_, "team": t, "qb": q, "missed": int(sum((gid, q) not in played for gid in x.game_id.values[mine[0]:]))})
    return pd.DataFrame(rows)


def injury_history(qb, season, ms, tg_season, cut, team, played):
    """A record of missed games: 4+ games missed as his team's season starter in either of the two seasons before, or a
    game this season, after his first start and through the cut, in which he had no dropback."""
    prev = ms[(ms.qb == qb) & ms.season.isin([season - 1, season - 2])]
    hist = bool((prev.missed >= 4).any())
    g = tg_season[(tg_season.team == team)].sort_values("week").head(cut)
    mine = np.flatnonzero(g.qb.values == qb)
    gap = bool(len(mine) and any((gid, qb) not in played for gid in g.game_id.values[mine[0]:]))
    return hist or gap, hist, gap


def rest_of_season(tg: pd.DataFrame, ms: pd.DataFrame, first: int, last: int, cut: int, played: set):
    """Historical version of the 2026 question: the QB who started a team's game number `cut`, when he was also the
    team's starter so far (most starts in its first `cut` games, as the 2026 teams in the exposure table are), and how
    many of the remaining games someone else started, split by his record of missed games."""
    rows = []
    for (s, t), g in tg[(tg.season >= first) & (tg.season <= last)].groupby(["season", "team"]):
        g = g.sort_values("week")
        if len(g) <= cut:
            continue
        q = g.qb.values[cut - 1]
        so_far = pd.Series(g.qb.values[:cut]).value_counts()
        if so_far.get(q, 0) < so_far.max():
            continue                     # a fill-in started game `cut`: his starter's return is not a backup start
        rest = g.iloc[cut:]
        flag, h, gap = injury_history(q, s, ms, g, cut, t, played)
        rows.append({"season": s, "team": t, "qb": q, "left": len(rest), "other": int((rest.qb != q).sum()), "history": flag,
                     "prior_4plus": h, "gap_this_season": gap})
    return pd.DataFrame(rows)


def exposure(tg_all, drop, k, mu_b, mu_s, hist_by, find, qm, wpp, current, ms, rates, draws, played):
    """Current starter and backup from the latest nflverse depth chart; expected backup starts over the rest of the season
    from the historical rest-of-season rate for starters with or without an injury history; expected wins lost =
    starts x wins lost per start for that backup behind that starter."""
    dc = data._release("depth_charts", f"depth_charts_{current}.parquet", refresh=True)
    dc = dc[dc.pos_abb == "QB"]
    latest = dc.dt.max(); find["depth_chart_date"] = str(latest)[:10]
    dc = dc[dc.dt == latest].copy()
    dc["team"] = franchise(dc.team)
    dc = dc.sort_values(["team", "pos_rank"]).drop_duplicates(["team", "gsis_id"])
    cur = tg_all[tg_all.season == current]
    qs_cur, _, _ = qb_priors(drop)  # priors include the season in progress
    rows = []
    for t, g in dc.groupby("team"):
        g = g.sort_values("pos_rank")
        if len(g) < 2:
            continue
        tc = cur[cur.team == t].sort_values("week")
        listed = list(g.gsis_id)
        s_id, b_id = listed[0], listed[1]   # the depth chart's order (ESPN moves an injured, benched or released QB down)
        name = dict(zip(tc.qb, tc.qb_name)) | dict(zip(g.gsis_id, g.player_name))
        s = pd.Series({"gsis_id": s_id, "player_name": name[s_id]}); b = pd.Series({"gsis_id": b_id, "player_name": name[b_id]})
        depth_qb1 = g.iloc[0].player_name
        played_n = len(tc)
        flag, h, gap = injury_history(s.gsis_id, current, ms, tc, played_n, t, played)
        if NEWS.get(t, ("",))[0] == "benching":
            flag = False                    # the news check says the missed starts were a benching, not an injury
        counts = tc.qb.value_counts()
        season_starter = counts.index[0] if len(counts) else s.gsis_id
        on_backup = bool(season_starter != s.gsis_id)
        rate = rates[flag]["rate"][0]
        left = GAMES - played_n
        bpri, bn = prior_for(qs_cur, [b.gsis_id], [current + 1], mu_b, k)
        spri, sn = prior_for(qs_cur, [s.gsis_id], [current + 1], mu_s, k)
        apy = contract_in_force(hist_by.get(b.gsis_id), current)
        m = qm["margin"]
        wps = (m["backup"][0] + m["bp_c"][0] * (bpri[0] - mu_b) + m["sp_c"][0] * (spri[0] - mu_s)) * wpp
        qf, rd, wd = draws
        n_ = min(len(qf), len(rd[flag]), len(wd))
        ew = rd[flag][:n_] * left * (qf[:n_, 0] + qf[:n_, 1] * (bpri[0] - mu_b) + qf[:n_, 2] * (spri[0] - mu_s)) * wd[:n_]
        ew_lo, ew_hi = np.percentile(ew, [2.5, 97.5])
        prev = {y: ms[(ms.qb == s.gsis_id) & (ms.season == y)].missed for y in (current - 2, current - 1)}
        rows.append({"team": t, "depth_chart_qb1": depth_qb1, "starter": s.player_name, "starter_id": s.gsis_id, "backup": b.player_name, "backup_id": b.gsis_id,
                     "started_last_game": bool(len(tc) and tc.qb.values[-1] == s.gsis_id), "last_game_qb": tc.qb_name.values[-1] if len(tc) else None,
                     f"starter_missed_{current - 2}": int(prev[current - 2].iloc[0]) if len(prev[current - 2]) else None,
                     f"starter_missed_{current - 1}": int(prev[current - 1].iloc[0]) if len(prev[current - 1]) else None,
                     f"starter_starts_{current}": int((tc.qb == s.gsis_id).sum()), "games_played": played_n,
                     "season_starter_so_far": name.get(season_starter, season_starter), "already_on_backup": on_backup,
                     "news_reason": NEWS.get(t, (None, None))[0], "news_note": NEWS.get(t, (None, None))[1],
                     "injury_history": flag, "prior_4plus_missed": h, "missed_this_season": gap,
                     "backup_career_dropbacks": int(bn[0]), "backup_prior_epa": round(float(bpri[0]), 3),
                     "starter_prior_epa": round(float(spri[0]), 3), "backup_apy_musd": apy[0],
                     "wins_lost_per_start": round(float(wps), 3), "games_left": left,
                     "exp_backup_starts_rest": round(rate * left, 2), "exp_wins_lost_rest": round(float(rate * left * wps), 3),
                     "exp_wins_lost_rest_lo": round(float(ew_lo), 3), "exp_wins_lost_rest_hi": round(float(ew_hi), 3)})
    return pd.DataFrame(rows).sort_values("exp_wins_lost_rest")


# ---------------------------------------------------------------- figures
def fig_cost(rob, find):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    r = rob.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(r))
    ax.errorbar(r.margin, y, xerr=[r.margin - r.margin_lo, r.margin_hi - r.margin], fmt="o", color=plot.ACCENT, ecolor=plot.ACCENT, capsize=3)
    ax.axvline(0, color=plot.SOFT, lw=1)
    ax.set_yticks(y); ax.set_yticklabels([f"{v} ({n} games)" for v, n in zip(r.version, r.backup_games)])
    for i, row in r.iterrows():
        ax.text(row.margin_hi + 0.3, i, f"{row.margin:+.1f} pts = {row.wins_per_start:+.2f} wins", va="center", fontsize=8.5, color=plot.MUTED)
    ax.set_xlabel("Point margin per game, backup start vs the same team's starter games (95% interval)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(min(r.margin_lo.min() - 1, -10), max(3.5, r.margin_hi.max() + 4.5))
    b = find["effect"]["margin"]
    plot.finish(fig, ax, f"A backup start costs {abs(r.margin).min():.1f} to {abs(r.margin).max():.1f} points of margin under every definition",
                f"Team-season fixed effects, opponent and home controls; {find['seasons']} regular seasons", OUT / "cost_per_start.png", source=SRC)


def fig_starts(ts, find, hist):
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10, 5), gridspec_kw={"width_ratios": [1.3, 1]})
    v = ts.bstarts.clip(upper=10).value_counts().sort_index()
    ax.bar(v.index, v.values / v.sum(), color=plot.ACCENT)
    ax.set_xticks(range(0, 11)); ax.set_xticklabels([str(i) for i in range(10)] + ["10+"])
    ax.set_xlabel("Backup starts in a team-season"); ax.set_ylabel("Share of team-seasons")
    ax.grid(axis="x", visible=False)
    labs = ["Missed 0\nyear before", "Missed 1-3", "Missed 4+", "New starter"]
    vals = [hist[h]["per_17"] for h in hist]
    ax2.bar(range(4), [x[0] for x in vals], color=[plot.ACCENT, plot.ACCENT, plot.ACCENT2, plot.SOFT],
            yerr=[[x[0] - x[1] for x in vals], [x[2] - x[0] for x in vals]], capsize=3)
    for i, x in enumerate(vals):
        ax2.text(i, x[2] + 0.1, f"{x[0]:.1f}", ha="center", fontsize=9)
    ax2.set_xticks(range(4)); ax2.set_xticklabels(labs, fontsize=8.5); ax2.set_ylabel("Backup starts per 17 games (95% interval)")
    ax2.grid(axis="x", visible=False)
    s = find["backup_starts_per_17"]
    plot.finish(fig, ax, f"Teams average {s[0]:.1f} backup starts a season; {100 * find['share_seasons_with_backup_start']:.0f}% get at least one",
                f"{find['seasons']}, {find['team_seasons']} team-seasons; right: by the starter's games missed the year before", OUT / "backup_starts.png", source=SRC)


def fig_quality(d, find, wpp):
    b = d[d.backup == 1].copy()
    g = b.groupby(["ts", "qb"]).agg(bp=("bp", "first"), n=("db", "sum"), games=("game_id", "size")).reset_index()
    sres = d[d.backup == 0].groupby("ts").epa_db.mean()
    bres = b.groupby(["ts", "qb"]).epa_db.mean()
    g["drop"] = bres.values - g.ts.map(sres).values
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.scatter(g.bp, g["drop"], s=10 + 6 * g.games, color=plot.ACCENT, alpha=0.35, edgecolor="none")
    g["bin"] = pd.qcut(g.bp, 6, duplicates="drop")
    bb = g.groupby("bin", observed=True).apply(lambda x: pd.Series({"x": np.average(x.bp, weights=x.n), "y": np.average(x["drop"], weights=x.n)}))
    ax.plot(bb.x, bb.y, "o-", color=plot.ACCENT2, lw=2, label=f"Average in sixths of backup record (model slope {find['quality_model']['epa_db']['bp_c'][0]:+.2f})")
    ax.axhline(0, color=plot.SOFT, lw=1)
    ax.set_xlabel("Backup's career EPA per dropback before the season (shrunk)")
    ax.set_ylabel("Team EPA per dropback: backup games minus starter games")
    ax.legend(loc="lower right", fontsize=8.5)
    q = find["quality_model"]["epa_db"]["bp_c"]
    ax.text(find["backup_epa_db_when_starting"], 0.55, "backups with no record", fontsize=8, color=plot.MUTED, ha="center")
    ax.set_ylim(-0.9, 0.6)   # a few stints beyond this range are cut off; they are in the bins and the model
    plot.finish(fig, ax, "Backups with better records lose less on average",
                f"{len(g)} backup stints, {find['seasons']}; dot size = games; y axis cut at -0.9 and +0.6", OUT / "backup_quality.png", source=SRC)


def fig_upgrade(find):
    u = find["upgrade"]; v = find["upgrade_via_quality"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labs = ["Through the contract\n(drop vs APY share)", "Through prior efficiency\n(APY to career EPA to drop)"]
    vals = [u["wins_per_season"], v["wins_per_season"]]
    y = [1, 0]
    for yy, x in zip(y, vals):
        ax.errorbar(x[0], yy, xerr=[[x[0] - x[1]], [x[2] - x[0]]], fmt="o", color=plot.ACCENT, capsize=4, ms=8)
        ax.text(x[2] + 0.01, yy + 0.12, f"{x[0]:+.3f} wins ({x[1]:+.3f} to {x[2]:+.3f})", va="bottom", fontsize=9)
    ax.axvline(0, color=plot.SOFT, lw=1)
    gap = u["cost_gap_musd"]
    for price, lab, yy in ((find["usd_per_win_qb_market"][0], "QB market", 1.55), (find["usd_per_win_league_check"]["replacement_3_wins"], "league-wide", 1.55)):
        need = gap / price
        ax.axvline(need, color=plot.ACCENT2, lw=1.4, ls="--")
        ax.text(need - 0.01, yy, f"wins \\${gap:.0f}M buys\n{lab}: \\${price:.1f}M a win", color=plot.ACCENT2, fontsize=8.5, ha="right", va="bottom")
    ax.set_yticks(y); ax.set_yticklabels(labs); ax.set_ylim(-0.6, 2.05)
    ax.set_xlabel(f"Expected wins a season saved by a \\${PRICEY:.0f}M backup over a \\${CHEAP:.0f}M one (95% interval)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(min(vals[0][1], vals[1][1], 0) - 0.05, gap / find["usd_per_win_qb_market"][0] + 0.1)
    plot.finish(fig, ax, f"A \\${PRICEY:.0f}M backup saves about {u['wins_per_season'][0]:.2f} wins a season, far less than \\${gap:.0f}M buys",
                f"Expected backup starts ({find['backup_starts_per_17'][0]:.1f} a season) x the per-start gap; 2026 cap (\\${CAP_2026}M)", OUT / "two_vs_ten.png", source=SRC)


def fig_exposure(e, find):
    top = e[~e.already_on_backup].sort_values("exp_wins_lost_rest").head(10).iloc[::-1].reset_index(drop=True)
    missing = [t for t in top.team if t not in NEWS]
    assert not missing, f"news-check these teams before publishing: {missing}"
    fig, ax = plt.subplots(figsize=(9.5, 6))
    x = -top.exp_wins_lost_rest
    col = [plot.ACCENT2 if h else plot.ACCENT for h in top.injury_history]
    ax.scatter(x, range(len(top)), color=col, zorder=3, s=36)
    ax.hlines(range(len(top)), -top.exp_wins_lost_rest_hi, -top.exp_wins_lost_rest_lo, color=col, lw=1.6)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels([f"{r.team}: {r.starter} / {r.backup}" for r in top.itertuples()], fontsize=8.5)
    for i, r in top.iterrows():
        ax.text(-r.exp_wins_lost_rest_lo + 0.01, i, f"{r.exp_backup_starts_rest:.1f} starts x {-r.wins_lost_per_start:.2f} wins", va="center", fontsize=8, color=plot.MUTED)
    ax.set_xlabel("Expected wins lost to backup starts, rest of the regular season (95% interval)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, (-top.exp_wins_lost_rest_lo).max() * 1.5)
    ax.scatter([], [], color=plot.ACCENT2, label="starter has a record of missed games (higher rate)"); ax.scatter([], [], color=plot.ACCENT, label="no record (lower rate)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, fontsize=8.5)
    worst = (-top.exp_wins_lost_rest).max()
    plot.finish(fig, ax, f"The most exposed team stands to lose about {worst:.2f} wins the rest of {find['current_season']}",
                f"Starter and backup as of {find['depth_chart_date']} (teams already on a backup left out); starts from history, cost from both QBs' records",
                OUT / f"exposure_{find['current_season']}.png", source="Data: nflverse play-by-play and depth charts, Over The Cap via nflverse. Chart: Dylan Fanelli")


if __name__ == "__main__":
    main()
