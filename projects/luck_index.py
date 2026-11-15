"""04 Luck Index: how many wins does chance hand out?

Inspired by Michael MacKelvie, "We Measured 'Luck' in the NFL. It's a BIG deal." (2025),
which builds on the NFL's own luck framework (Tom Bliss). Public data has no drop charting
before 2022, so this version uses the luck events play-by-play can see for 20 seasons:
  - fumble recoveries (who falls on the ball is close to a coin flip),
  - opponent field goals vs a make-probability model,
  - record in one-score games,
and compares actual wins with Pythagorean (points-based) wins.
Test: if it is luck, it should not repeat next year, and next year's record should follow
points, not wins.
Run: python -m projects.luck_index
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression

from nflan import data, plot
from nflan.stats import pythag_wins

OUT = Path("reports/04-luck-index")
LAST = data.latest_season_available()
COLS = ["game_id", "season", "season_type", "week", "home_team", "away_team", "home_score", "away_score", "result",
        "posteam", "defteam", "fumble", "fumble_lost", "fumble_recovery_1_team", "fumbled_1_team", "play_type",
        "field_goal_attempt", "field_goal_result", "kick_distance", "roof", "aborted_play"]


def team_games(g: pd.DataFrame) -> pd.DataFrame:
    h = g.assign(team=g.home_team, opp=g.away_team, pf=g.home_score, pa=g.away_score)
    a = g.assign(team=g.away_team, opp=g.home_team, pf=g.away_score, pa=g.home_score)
    t = pd.concat([h, a])[["game_id", "season", "week", "team", "opp", "pf", "pa"]]
    t["win"] = np.select([t.pf > t.pa, t.pf < t.pa], [1.0, 0.0], 0.5)
    t["one_score"] = (t.pf - t.pa).abs() <= 8
    t["os_win"] = np.where(t.one_score, t.win, 0.0)
    return t.reset_index(drop=True)


LUCKY = 2.0          # wins above or below Pythagorean that count as a lucky or unlucky season
MATCH_WINDOW = 1.0   # controls must be within this many wins (per 17 games) of the lucky team
N_BOOT = 1000


def matched_gap(d: pd.DataFrame, side: int) -> float:
    """Next-year change for lucky (side=1) or unlucky (side=-1) teams minus the change for
    same-record teams whose record matched their points (within 1 win of Pythagorean)."""
    hit = d[side * d.luck17 >= LUCKY]
    ctrl = d[d.luck17.abs() < 1.0]
    if hit.empty or ctrl.empty:
        return np.nan
    cw = ctrl.w17.to_numpy(); cc = (ctrl.w17_next - ctrl.w17).to_numpy()
    gaps = []
    for w, ch in zip(hit.w17.to_numpy(), (hit.w17_next - hit.w17).to_numpy()):
        m = np.abs(cw - w) <= MATCH_WINDOW
        if m.any():
            gaps.append(ch - cc[m].mean())
    return float(np.mean(gaps)) if gaps else np.nan


def _ols(y, X):
    A = np.column_stack([np.ones(len(X)), X])
    return np.linalg.lstsq(A, y, rcond=None)[0][1:]


def _luck_stats(d: pd.DataFrame) -> dict:
    y = d.w17_next.to_numpy()
    b = _ols(y, d[["p17", "luck17"]].to_numpy())
    c = _ols(y, d[["p17", "fumble_luck", "fg_luck", "one_score_luck"]].to_numpy())
    return {
        "lucky_minus_matched_wins": matched_gap(d, 1),
        "unlucky_minus_matched_wins": matched_gap(d, -1),
        "next_wins_per_pythag_win": b[0],
        "next_wins_per_luck_win": b[1],
        "next_wins_per_fumble_recovery_over_exp": c[1],
        "next_wins_per_fg_point_of_luck": c[2],
        "next_wins_per_one_score_win_over_half": c[3],
        "r_pythag_minus_r_wins": d.pyth_pct.corr(d.winpct_next) - d.winpct.corr(d.winpct_next),
    }


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pbp = data.load_pbp(range(2006, LAST + 1), columns=COLS)
    pbp = pbp[pbp.season_type == "REG"]
    find = {}
    g = pbp.drop_duplicates("game_id")[["game_id", "season", "week", "home_team", "away_team", "home_score", "away_score"]]
    tg = team_games(g)

    # fumbles: share of all fumbles in a team's games that the team recovered (fumble came loose, someone recovered)
    f = pbp[(pbp.fumble == 1) & pbp.fumble_recovery_1_team.notna() & pbp.fumbled_1_team.notna()]
    f = f[(f.fumbled_1_team == f.posteam) | (f.fumbled_1_team == f.defteam)].copy()
    f["other"] = np.where(f.fumbled_1_team == f.posteam, f.defteam, f.posteam)
    f["own_rec"] = (f.fumble_recovery_1_team == f.fumbled_1_team).astype(int)
    own = f.groupby(["season", "fumbled_1_team"]).agg(own_fum=("own_rec", "size"), own_rec=("own_rec", "sum")).rename_axis(["season", "team"])
    dfn = f.assign(def_rec=1 - f.own_rec).groupby(["season", "other"]).agg(opp_fum=("def_rec", "size"), def_rec=("def_rec", "sum")).rename_axis(["season", "team"])
    fum = own.join(dfn, how="outer").fillna(0)
    fum["recovered"] = fum.own_rec + fum.def_rec
    fum["total"] = fum.own_fum + fum.opp_fum
    fum["exp_rec"] = 0.5 * fum.total  # simplification: every loose ball is a coin flip
    fum["fumble_luck"] = fum.recovered - fum.exp_rec

    # opponent field goals vs expectation (points the defense 'got lucky' on)
    k = pbp[(pbp.field_goal_attempt == 1) & pbp.kick_distance.notna() & pbp.field_goal_result.isin(["made", "missed", "blocked"])].copy()
    k["made"] = (k.field_goal_result == "made").astype(int)
    k["indoor"] = k.roof.isin(["dome", "closed"]).astype(int)
    X = np.column_stack([k.kick_distance, k.kick_distance ** 2, k.indoor, k.season - 2006])
    lr = LogisticRegression(max_iter=3000).fit(X, k.made)
    k["p"] = lr.predict_proba(X)[:, 1]
    k["pts_over_exp"] = 3 * (k.made - k.p)
    opp_fg = k.groupby(["season", "defteam"]).pts_over_exp.sum().rename("opp_fg_pts_over_exp").rename_axis(["season", "team"])

    ts = tg.groupby(["season", "team"]).agg(games=("win", "size"), wins=("win", "sum"), pf=("pf", "sum"), pa=("pa", "sum"),
                                             os_games=("one_score", "sum"),
                                             os_wins=("os_win", "sum"))
    ts["pythag"] = pythag_wins(ts.pf, ts.pa, ts.games)
    ts["wins_over_pythag"] = ts.wins - ts.pythag
    ts["one_score_luck"] = ts.os_wins - ts.os_games / 2
    ts = ts.join(fum[["fumble_luck", "recovered", "total"]]).join(opp_fg).fillna(0)
    ts["fg_luck"] = -ts.opp_fg_pts_over_exp
    ts = ts.reset_index()
    ts.to_csv(OUT / "team_season_luck.csv", index=False)

    full = ts[ts.season <= LAST - 1]
    nxt = full.merge(full.assign(season=full.season - 1), on=["season", "team"], suffixes=("", "_next"))
    nxt["winpct"] = nxt.wins / nxt.games; nxt["winpct_next"] = nxt.wins_next / nxt.games_next
    nxt["pyth_pct"] = nxt.pythag / nxt.games
    for c in ["fumble_luck", "fg_luck", "one_score_luck", "wins_over_pythag"]:
        find[f"yoy_r_{c}"] = round(float(nxt[c].corr(nxt[c + "_next"])), 3)
    find["r_next_winpct_from_winpct"] = round(float(nxt.winpct.corr(nxt.winpct_next)), 3)
    find["r_next_winpct_from_pythag"] = round(float(nxt.pyth_pct.corr(nxt.winpct_next)), 3)
    lucky = nxt[nxt.wins_over_pythag >= LUCKY]; unlucky = nxt[nxt.wins_over_pythag <= -LUCKY]
    find["lucky_teams_n"] = len(lucky); find["lucky_change_wins_per17"] = round(float(17 * (lucky.winpct_next - lucky.winpct).mean()), 2)
    find["unlucky_teams_n"] = len(unlucky); find["unlucky_change_wins_per17"] = round(float(17 * (unlucky.winpct_next - unlucky.winpct).mean()), 2)
    find["team_season_pairs"] = len(nxt)

    # Any team with a lot of wins falls back next year. The fair test compares lucky teams with teams
    # that had the same record without the luck, and asks whether luck adds to the fall.
    nxt["w17"] = 17 * nxt.winpct; nxt["w17_next"] = 17 * nxt.winpct_next; nxt["p17"] = 17 * nxt.pyth_pct
    nxt["luck17"] = nxt.w17 - nxt.p17
    stats = lambda d: _luck_stats(d)
    point = stats(nxt)
    rng = np.random.default_rng(7)
    by_team = {t: d for t, d in nxt.groupby("team")}
    teams = list(by_team)
    boots = []
    for _ in range(N_BOOT):
        d = pd.concat([by_team[t] for t in rng.choice(teams, len(teams))], ignore_index=True)
        boots.append(stats(d))
    boots = pd.DataFrame(boots)
    for k_, v in point.items():
        lo, hi = np.nanpercentile(boots[k_], [2.5, 97.5])
        find[k_] = [round(float(v), 3), round(float(lo), 3), round(float(hi), 3)]
    find["boot_n"] = N_BOOT
    find["lucky_cutoff_wins"] = LUCKY
    find["match_window_wins"] = MATCH_WINDOW

    # chart: this year's luck vs next year's change
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(nxt.wins_over_pythag, 17 * (nxt.winpct_next - nxt.winpct), s=14, alpha=0.45, color=plot.ACCENT)
    b = np.polyfit(nxt.wins_over_pythag, 17 * (nxt.winpct_next - nxt.winpct), 1)
    xs = np.linspace(-5, 5, 20); ax.plot(xs, np.polyval(b, xs), color=plot.ACCENT2, lw=2.4)
    ax.axhline(0, color=plot.MUTED, lw=.8); ax.axvline(0, color=plot.MUTED, lw=.8)
    ax.set_xlabel("Wins above Pythagorean expectation, season N"); ax.set_ylabel("Change in wins next season (per 17 games)")
    plot.finish(fig, ax, "Teams that beat their point differential win fewer games next year",
                f"Each dot is a team-season, 2006-{LAST - 1}. Slope {b[0]:.2f}. Part of this is plain regression to the mean", OUT / "luck_regression.png")
    find["slope_change_per_lucky_win"] = round(float(b[0]), 2)

    # season in progress
    cur = ts[ts.season == LAST].sort_values("wins_over_pythag")
    cur[["team", "games", "wins", "pythag", "wins_over_pythag", "one_score_luck", "fumble_luck", "fg_luck"]].round(2).to_csv(OUT / f"luck_{LAST}.csv", index=False)
    find["current_luckiest"] = cur.tail(3)[["team", "wins", "pythag"]].round(1).values.tolist()
    find["current_unluckiest"] = cur.head(3)[["team", "wins", "pythag"]].round(1).values.tolist()
    fig, ax = plt.subplots(figsize=(8, 8.5))
    c = cur.sort_values("wins_over_pythag")
    ax.barh(c.team, c.wins_over_pythag, color=[plot.ACCENT2 if v > 0 else plot.ACCENT for v in c.wins_over_pythag])
    ax.axvline(0, color=plot.MUTED); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Actual wins minus Pythagorean wins")
    plot.finish(fig, ax, f"{LAST} so far: who is winning more than their scoring says?",
                "Orange = record better than points. Green = record worse than points.", OUT / f"luck_{LAST}.png")

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k_, v in find.items():
        print(k_, v)


if __name__ == "__main__":
    main()
