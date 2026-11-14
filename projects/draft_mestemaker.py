"""Draft 2027 prospect report: Drew Mestemaker, QB, Oklahoma State. Is he QB1?

Builds reports/draft-2027-drew-mestemaker/ (findings.json, figures, tables, README) from the CSVs in its data/ folder.
The CSVs were pulled from cfbstats.com (season tables, situational tables, game logs, splits) and nflverse draft picks;
`--refresh` pulls them again (see pull()). Every number on the page comes from findings.json.

    python -m projects.draft_mestemaker            # rebuild from data/
    python -m projects.draft_mestemaker --refresh  # re-pull the season in progress first
"""
from __future__ import annotations

import html
import io
import json
import re
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from nflan import plot as P

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "draft-2027-drew-mestemaker"
DATA = OUT / "data"
SRC = "Data: cfbstats.com, nflverse draft picks. Chart: Dylan Fanelli"
ME, SEASON, THROUGH = "Drew Mestemaker", 2026, "Nov. 13, 2026"
CLASS = [ME, "Darian Mensah", "CJ Carr", "Julian Sayin", "Arch Manning", "Sam Leavitt", "LaNorris Sellers"]
TRAIL = ["Losing By 1-7 Pts", "Losing By 8-14 Pts", "Losing By 15+ Pts"]
RZ = "Opp 20 To 1 Yd Ln (RZ)"
LABEL = {"YPG": "Passing yards per game", "YPA": "Yards per attempt", "AYA": "Adjusted yards per attempt",
         "Rating": "Passer rating (NCAA)", "Pct": "Completion %", "TDp": "Touchdown %", "INTp": "Interception %",
         "x25": "25+ yard completions per 100 attempts", "x15": "15+ yard completions per 100 attempts",
         "fd": "First downs per 100 attempts", "r3": "Third-down passer rating", "q4": "Fourth-quarter passer rating",
         "rz_td": "Red-zone touchdown %", "trail": "Passer rating when trailing"}
LOW_GOOD = {"INTp"}


def ncaa_rating(cmp_, att, yds, td, int_):
    return (8.4 * yds + 330 * td + 100 * cmp_ - 200 * int_) / att


# ---------------------------------------------------------------- data
def load():
    L = pd.read_csv(DATA / "qb_seasons_2020_2026.csv", dtype={"player_id": str, "team_id": str})
    L["TDp"] = 100 * L.TD / L.Att
    L["INTp"] = 100 * L.Int / L.Att
    L["AYA"] = (L.Yards + 20 * L.TD - 45 * L.Int) / L.Att
    S = pd.read_csv(DATA / "situational_2024_2026_and_first_rounders.csv", dtype={"player_id": str})
    num = ["Att", "Comp", "Yards", "TD", "Int", "1st", "15+", "25+", "Rating"]
    for c in num:
        S[c] = pd.to_numeric(S[c], errors="coerce")
    W = S.pivot_table(index=["player_id", "season"], columns="Situation", values=num)
    A = pd.DataFrame(index=W.index)
    att = W["Att"]["All Plays"]
    A["x25"] = 100 * W["25+"]["All Plays"] / att
    A["x15"] = 100 * W["15+"]["All Plays"] / att
    A["fd"] = 100 * W["1st"]["All Plays"] / att
    A["r3"], A["att3"] = W["Rating"]["3rd Down"], W["Att"]["3rd Down"]
    A["q4"], A["att_q4"] = W["Rating"]["4th Quarter"], W["Att"]["4th Quarter"]
    A["rz_td"] = 100 * W["TD"][RZ] / W["Att"][RZ]
    A["att_trail"] = W["Att"][TRAIL].sum(axis=1)
    A["trail"] = ncaa_rating(W["Comp"][TRAIL].sum(axis=1), A.att_trail, W["Yards"][TRAIL].sum(axis=1),
                             W["TD"][TRAIL].sum(axis=1), W["Int"][TRAIL].sum(axis=1))
    D = L.merge(A.reset_index(), on=["player_id", "season"], how="left").sort_values(["player_id", "season"])
    G = pd.read_csv(DATA / "gamelogs.csv")
    for c in ["Att", "Comp", "Yards", "TD", "Int", "Rating", "RushAtt", "RushYards", "RushTD"]:
        G[c] = pd.to_numeric(G[c], errors="coerce")
    SP = pd.read_csv(DATA / "splits.csv")
    FR = pd.read_csv(DATA / "first_round_qbs_2021_2026.csv")
    MV = pd.read_csv(DATA / "g5_to_p4_moves.csv", dtype={"player_id": str})
    return D, G, SP, FR, MV


def rank(df, col, name=ME):
    r = df[col].rank(ascending=col in LOW_GOOD, method="min")
    return int(r[df.Name == name].iloc[0]), int(df[col].notna().sum())


def yoy(D, col, seed=7, n_boot=2000):
    """Year-to-year correlation for QBs who qualified in back-to-back seasons; bootstrap resamples quarterbacks."""
    d = D[["player_id", "season", col]].dropna()
    nxt = d.assign(season=d.season - 1)
    p = d.merge(nxt, on=["player_id", "season"], suffixes=("", "_next")).set_index("player_id")
    ids = p.index.unique()
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n_boot):
        q = p.loc[rng.choice(ids, len(ids))]
        bs.append(np.corrcoef(q[col], q[col + "_next"])[0, 1])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(r=float(np.corrcoef(p[col], p[col + "_next"])[0, 1]), n=int(len(p)), qbs=int(len(ids)), lo=float(lo), hi=float(hi))


# ---------------------------------------------------------------- analysis
def analyze():
    D, G, SP, FR, MV = load()
    f = dict(player=ME, school="Oklahoma State", season=SEASON, through=THROUGH)
    cur = D[D.season == SEASON]
    me = cur[cur.Name == ME].iloc[0]
    me25 = D[(D.Name == ME) & (D.season == 2025)].iloc[0]
    metrics = ["YPG", "YPA", "AYA", "Rating", "Pct", "TDp", "INTp", "x25", "x15", "fd", "r3", "q4", "rz_td", "trail"]

    f["line"] = {k: (float(me[k]) if k not in ("G", "Att", "Comp", "Yards", "TD", "Int") else int(me[k]))
                 for k in ["G", "Att", "Comp", "Yards", "TD", "Int", "Pct", "YPA", "AYA", "Rating", "YPG", "TDp", "INTp",
                           "x25", "x15", "fd", "r3", "att3", "q4", "att_q4", "rz_td", "trail", "att_trail"]}
    f["line_2025"] = {k: float(me25[k]) for k in ["G", "Att", "Yards", "TD", "Int", "Pct", "YPA", "Rating", "YPG", "TDp", "INTp", "x25", "x15", "r3", "q4"]}
    f["pool"], f["n_seasons"] = int(len(cur)), int(len(D))
    f["ranks"] = {m: rank(cur, m) for m in metrics}
    f["ranks"]["Yards"], f["ranks"]["TD"] = rank(cur, "Yards"), rank(cur, "TD")
    c25 = D[D.season == 2025]
    f["ranks_2025"] = {m: rank(c25, m) for m in ["YPG", "YPA", "Rating", "x25", "INTp", "r3"]}

    # rushing and game log
    g = G[(G.player == ME) & (G.season == SEASON)].reset_index(drop=True)
    f["rush"] = dict(att=int(g.RushAtt.sum()), yards=int(g.RushYards.sum()), td=int(g.RushTD.sum()))
    f["games_300"] = int((g.Yards >= 300).sum())
    last = g.iloc[2:]
    f["last7"] = dict(games=int(len(last)), att=int(last.Att.sum()), comp=int(last.Comp.sum()), yards=int(last.Yards.sum()),
                      td=int(last.TD.sum()), int=int(last.Int.sum()), min_rating=float(last.Rating.min()),
                      rating=float(ncaa_rating(last.Comp.sum(), last.Att.sum(), last.Yards.sum(), last.TD.sum(), last.Int.sum())),
                      ypa=float(last.Yards.sum() / last.Att.sum()))
    first2 = g.iloc[:2]
    f["first2"] = dict(rating=float(ncaa_rating(first2.Comp.sum(), first2.Att.sum(), first2.Yards.sum(), first2.TD.sum(), first2.Int.sum())),
                       int=int(first2.Int.sum()), att=int(first2.Att.sum()))
    res = g.Result.str.extract(r"([WL]) (\d+)-(\d+)")
    f["team"] = dict(wins=int((res[0] == "W").sum()), losses=int((res[0] == "L").sum()), ppg=float(res[1].astype(int).mean()))
    ore = g[g.Opponent.str.contains("Oregon")].iloc[0]
    f["oregon"] = dict(yards=int(ore.Yards), td=int(ore.TD), int=int(ore.Int), rush=int(ore.RushYards), rush_td=int(ore.RushTD), result=ore.Result)
    sp = SP[(SP.player == ME) & (SP.season == SEASON)].set_index("Split")
    f["splits"] = {k: dict(g=int(sp.loc[k, "G"]), att=int(sp.loc[k, "Att"]), ypa=float(sp.loc[k, "YPA"]), td=int(sp.loc[k, "TD"]),
                           int=int(sp.loc[k, "Int"]), rating=float(sp.loc[k, "Rating"]))
                   for k in ["vs. FBS Power 5", "vs. Ranked (AP)", "vs. FBS Winning", "in Wins", "in Losses", "at Home", "on Road/Neutral Site"]}
    sit = pd.read_csv(DATA / "situational_2024_2026_and_first_rounders.csv", dtype={"player_id": str})
    sit = sit[(sit.player == ME) & (sit.season == SEASON)].set_index("Situation")
    f["downs"] = {k: dict(att=int(sit.loc[k, "Att"]), comp=int(sit.loc[k, "Comp"]), yards=int(sit.loc[k, "Yards"]), rating=float(sit.loc[k, "Rating"]))
                  for k in ["1st Down", "2nd Down", "3rd Down", "3rd Down, 1-3 To Go", "3rd Down, 10+ To Go"]}
    f["sit_att_all_plays"] = int(sit.loc["All Plays", "Att"])
    f["pace_12"] = dict(yards=int(round(me.Yards / me.G * 12)), td=int(round(me.TD / me.G * 12)))

    # the class
    cls = cur[cur.Name.isin(CLASS)].set_index("Name").loc[CLASS]
    f["class"] = [dict(name=n, team=r.Team, g=int(r.G), att=int(r.Att), yards=int(r.Yards), td=int(r.TD), int=int(r.Int),
                       **{m: float(r[m]) for m in metrics}) for n, r in cls.iterrows()]
    f["class_leads"] = [m for m in metrics if rank(cls.reset_index(), m)[0] == 1]
    two = D[D.season.isin([2025, 2026]) & D.Name.isin(CLASS)].groupby("Name").agg(
        seasons=("season", "nunique"), G=("G", "sum"), Att=("Att", "sum"), Comp=("Comp", "sum"), Yards=("Yards", "sum"), TD=("TD", "sum"), Int=("Int", "sum"))
    two["YPA"], two["Rating"] = two.Yards / two.Att, ncaa_rating(two.Comp, two.Att, two.Yards, two.TD, two.Int)
    two["TDp"], two["INTp"], two["YPG"] = 100 * two.TD / two.Att, 100 * two.Int / two.Att, two.Yards / two.G
    two = two.loc[[n for n in CLASS if n in two.index]]
    f["two_year"] = [dict(name=n, **{k: (int(v) if k in ("seasons", "G", "Att", "Comp", "Yards", "TD", "Int") else float(v)) for k, v in r.items()}) for n, r in two.iterrows()]
    moore = G[(G.player == "Dante Moore") & (G.season == SEASON) & G.Att.notna()]
    f["moore"] = dict(games=int(len(moore)), att=int(moore.Att.sum()), yards=int(moore.Yards.sum()), td=int(moore.TD.sum()), int=int(moore.Int.sum()))

    # first-round quarterbacks, final college season
    fr = FR[FR.in_fbs_data].merge(D, left_on=["cfbstats_name", "final_season"], right_on=["Name", "season"], how="left")
    assert fr.Rating.notna().all() and len(fr) == 18
    f["first_round_n"] = int(len(fr))
    f["vs_first_round"] = {m: dict(me=float(me[m]), median=float(fr[m].median()),
                                   beats=int((fr[m] > me[m]).sum() if m in LOW_GOOD else (fr[m] < me[m]).sum())) for m in metrics}
    comp_cols = ["YPA", "Pct", "TDp", "INTp", "x25", "YPG"]
    z = (fr[comp_cols] - fr[comp_cols].mean()) / fr[comp_cols].std()
    zme = (me[comp_cols].astype(float) - fr[comp_cols].mean()) / fr[comp_cols].std()
    fr["dist"] = np.sqrt(((z - zme) ** 2).sum(axis=1))
    f["comps"] = [dict(name=r.Name, season=int(r.season), pick=int(r.pick), dist=float(r.dist), rating=float(r.Rating), ypa=float(r.YPA),
                       tdp=float(r.TDp), intp=float(r.INTp), x25=float(r.x25)) for r in fr.nsmallest(3, "dist").itertuples()]
    f["age"] = dict(at_draft=21, born="January 2006", first_round_median_nflverse=float(FR.age.median()), first_round_total=int(len(FR)))

    # does it repeat?
    f["stability"] = {m: yoy(D, m) for m in ["YPG", "Pct", "YPA", "Rating", "AYA", "TDp", "INTp", "fd", "q4", "r3", "rz_td", "x15", "x25"]}

    # Group of Five to Power Four
    mv = MV.merge(D[["player_id", "season", "Rating", "YPA", "INTp"]], left_on=["player_id", "season_before"], right_on=["player_id", "season"])
    mv = mv.merge(D[["player_id", "season", "Rating", "YPA", "INTp"]], left_on=["player_id", "season_after"], right_on=["player_id", "season"], suffixes=("_b", "_a"))
    mv["d_rating"], mv["d_ypa"] = mv.Rating_a - mv.Rating_b, mv.YPA_a - mv.YPA_b
    oth = mv[mv.name != ME]
    mine = mv[mv.name == ME].iloc[0]
    f["move"] = dict(n=int(len(mv)), mean_d_rating=float(oth.d_rating.mean()), median_d_rating=float(oth.d_rating.median()),
                     mean_d_ypa=float(oth.d_ypa.mean()), improved=int((oth.d_rating > 0).sum()), others=int(len(oth)),
                     me_d_rating=float(mine.d_rating), me_d_ypa=float(mine.d_ypa), me_before=float(mine.Rating_b), me_after=float(mine.Rating_a),
                     held_165=int(((mv.Rating_b >= 165) & (mv.Rating_a >= 165)).sum()), started_165=int((mv.Rating_b >= 165).sum()),
                     me_rank_after=int(mv.Rating_a.rank(ascending=False).loc[mv.name == ME].iloc[0]),
                     mean_d_rating_ex_mateer=float(oth[oth.name != "John Mateer"].d_rating.mean()), declined=int((oth.d_rating < 0).sum()))
    x25 = cur.sort_values("x25", ascending=False).iloc[0]
    f["x25_leader"] = dict(name=x25.Name, team=x25.Team, x25=float(x25.x25), att=int(x25.Att))
    assert f["move"]["held_165"] == 1
    return f, D, G, fr, mv, cls


# ---------------------------------------------------------------- figures
def figures(f, D, G, fr, mv, cls):
    P.style()
    cur = D[D.season == SEASON]
    me = cur[cur.Name == ME].iloc[0]

    # 1 hero: explosive passing against first-round quarterbacks
    d = pd.concat([fr[["Name", "season", "x25"]], pd.DataFrame([dict(Name=ME, season=SEASON, x25=me.x25)])]).sort_values("x25")
    fig, ax = plt.subplots(figsize=(9, 6.6))
    cols = [P.ACCENT2 if n == ME else P.ACCENT for n in d.Name]
    ax.barh([f"{n} ({s})" for n, s in zip(d.Name, d.season)], d.x25, color=cols, height=0.68)
    for y, v in enumerate(d.x25):
        ax.text(v + 0.12, y, f"{v:.1f}", va="center", fontsize=9, color=P.INK)
    ax.set_xlabel("Completions of 25+ yards per 100 attempts")
    ax.grid(axis="y", visible=False)
    P.finish(fig, ax, "Mestemaker hits the big play more often than first-round QBs did",
             f"Final college season of the {len(fr)} FBS quarterbacks drafted in round 1, 2021-2026, and Mestemaker through {THROUGH}", OUT / "explosive_vs_first_round.png", SRC)

    # 2 where he ranks among FBS passers
    order = ["YPG", "x25", "TDp", "fd", "x15", "YPA", "Rating", "trail", "AYA", "rz_td", "Pct", "q4", "r3", "INTp"]
    pct = [100 * (1 - (f["ranks"][m][0] - 1) / (f["ranks"][m][1] - 1)) for m in order]
    fig, ax = plt.subplots(figsize=(9, 6))
    ys = np.arange(len(order))[::-1]
    ax.hlines(ys, 0, pct, color=P.GRID, lw=2.2)
    ax.scatter(pct, ys, s=90, color=[P.ACCENT if p >= 50 else P.ACCENT2 for p in pct], zorder=3)
    for y, m, p in zip(ys, order, pct):
        ax.text(min(p + 2.5, 101), y, f"#{f['ranks'][m][0]}", va="center", fontsize=9)
    ax.set_yticks(ys, [LABEL[m] for m in order])
    ax.set_xlim(0, 108)
    ax.axvline(50, color=P.SOFT, lw=1, ls="--")
    ax.set_xlabel(f"Percentile among the top {f['pool']} FBS passers by yards per game (100 = best)")
    ax.grid(axis="y", visible=False)
    P.finish(fig, ax, "Top 10 in the volume and big-play numbers, below average in two", f"Mestemaker's national rank in each measure, {SEASON} through {THROUGH}", OUT / "national_ranks.png", SRC)

    # 3 stability
    st = pd.DataFrame(f["stability"]).T.sort_values("r")
    fig, ax = plt.subplots(figsize=(9, 5.6))
    flags = {"INTp", "r3", "q4"}
    ys = np.arange(len(st))
    ax.barh(ys, st.r, color=[P.ACCENT2 if m in flags else P.ACCENT for m in st.index], height=0.62)
    ax.errorbar(st.r, ys, xerr=[st.r - st.lo, st.hi - st.r], fmt="none", ecolor=P.INK, lw=1, capsize=2.5)
    ax.set_yticks(ys, [LABEL[m] for m in st.index])
    ax.axvline(0, color=P.SOFT, lw=1)
    ax.set_xlabel("Year-to-year correlation for the same quarterback (95% interval)")
    ax.grid(axis="y", visible=False)
    P.finish(fig, ax, "Interception rate, his biggest knock, barely repeats", "Orange: his three weakest measures. FBS quarterbacks who qualified in back-to-back seasons",
             OUT / "stability.png", SRC)

    # 4 moving up a level
    m2 = mv.sort_values("d_rating")
    fig, ax = plt.subplots(figsize=(9, 6.2))
    for y, r in enumerate(m2.itertuples()):
        c = P.ACCENT2 if r.name == ME else P.ACCENT
        ax.plot([r.Rating_b, r.Rating_a], [y, y], color=c, lw=2.4 if r.name == ME else 1.6, alpha=1 if r.name == ME else 0.75)
        ax.scatter([r.Rating_b], [y], s=34, facecolor=P.PLATE, edgecolor=c, zorder=3)
        ax.scatter([r.Rating_a], [y], s=46, color=c, zorder=3)
    ax.set_yticks(range(len(m2)), [f"{r.name} ({r.to_team}, {r.season_after})" for r in m2.itertuples()], fontsize=8.5)
    ax.axvline(165, color=P.SOFT, lw=1, ls="--")
    ax.set_xlabel("Passer rating: open dot = last Group of Five season, filled dot = first Power Four season")
    ax.grid(axis="y", visible=False)
    P.finish(fig, ax, "His production came with him to the Big 12", f"All {len(mv)} transfers who made the top-100 list before and after a Group of Five to Power Four move, 2021-2026",
             OUT / "g5_to_p4.png", SRC)

    # 5 game log
    g = G[(G.player == ME) & (G.season.isin([2025, 2026]))].copy()
    g = g.assign(d=pd.to_datetime(g.Date, format="%m/%d/%y")).sort_values("d").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(g))
    ax.bar(x, g.Rating, color=[P.ACCENT if s == 2025 else P.ACCENT2 for s in g.season], width=0.7)
    ax.axhline(fr.Rating.median(), color=P.INK, lw=1, ls="--")
    ax.set_xticks(x, [o.replace("@ ", "@").replace("+ ", "") for o in g.Opponent], rotation=62, ha="right", fontsize=8)
    ax.set_ylabel("Passer rating")
    ax.grid(axis="x", visible=False)
    P.finish(fig, ax, "Two bad starts to 2026, then seven straight above 160", f"Passer rating by game. Green: North Texas 2025. Orange: Oklahoma State 2026. Dashed: first-round median ({fr.Rating.median():.0f})",
             OUT / "game_log.png", SRC)

    # 6 class scatter
    fig, ax = plt.subplots(figsize=(9, 5.6))
    ax.scatter(cur.x25, cur.YPA, s=22, color=P.SOFT, alpha=0.55)
    for r in cls.reset_index().itertuples():
        c = P.ACCENT2 if r.Name == ME else P.ACCENT
        ax.scatter([r.x25], [r.YPA], s=80, color=c, zorder=3)
        ax.annotate(r.Name.split()[-1], (r.x25, r.YPA), xytext=(6, 5), textcoords="offset points", fontsize=9.5, fontweight="semibold")
    ax.set_xlabel("Completions of 25+ yards per 100 attempts")
    ax.set_ylabel("Yards per attempt")
    P.finish(fig, ax, "The 2027 class: Mensah and Sayin more efficient, Mestemaker more big plays", f"Top {f['pool']} FBS passers in grey; draft-eligible names labeled. {SEASON} through {THROUGH}",
             OUT / "class_map.png", SRC)


# ---------------------------------------------------------------- README
def readme(f):
    L, r, s, v, mv = f["line"], f["ranks"], f["stability"], f["vs_first_round"], f["move"]

    def rk(m):
        return f"#{r[m][0]} of {r[m][1]}"

    cls_rows = "\n".join(
        f"| {'**' + c['name'] + '**' if c['name'] == ME else c['name']} | {c['team']} | {c['g']} | {c['yards']:,} | {c['td']} | {c['int']} | {c['Pct']:.1f} | {c['YPA']:.1f} | {c['Rating']:.1f} | {c['x25']:.1f} | {c['INTp']:.1f} | {c['r3']:.0f} |"
        for c in f["class"])
    two_rows = "\n".join(
        f"| {'**' + t['name'] + '**' if t['name'] == ME else t['name']} | {t['seasons']} | {t['Att']:,} | {t['Yards']:,} | {t['TD']} | {t['Int']} | {t['YPA']:.1f} | {t['Rating']:.1f} | {t['YPG']:.0f} |"
        for t in f["two_year"])
    fr_rows = "\n".join(
        f"| {LABEL[m]} | {v[m]['me']:.1f} | {v[m]['median']:.1f} | {v[m]['beats']} of {f['first_round_n']} |"
        for m in ["YPG", "YPA", "Rating", "TDp", "x25", "x15", "fd", "Pct", "q4", "INTp", "r3"])
    st_rows = "\n".join(
        f"| {LABEL[m]} | {x['r']:.2f} | {x['lo']:.2f} to {x['hi']:.2f} | {x['n']} |"
        for m, x in sorted(s.items(), key=lambda kv: -kv[1]["r"]))
    comps = ", ".join(f"{c['name']} ({c['season']}, pick {c['pick']})" for c in f["comps"])
    sp = f["splits"]
    n_above = sum(1 for m in v if (v[m]['me'] < v[m]['median'] if m in LOW_GOOD else v[m]['me'] > v[m]['median']))
    mens = next(c for c in f["class"] if c["name"] == "Darian Mensah")
    sayin = next(c for c in f["class"] if c["name"] == "Julian Sayin")
    two_best_rate = max(f["two_year"], key=lambda t: t["Rating"])
    two_me = next(t for t in f["two_year"] if t["name"] == ME)
    assert max(f["two_year"], key=lambda t: t["YPA"])["name"] == two_best_rate["name"] and max(f["two_year"], key=lambda t: t["TD"])["name"] == ME == max(f["two_year"], key=lambda t: t["Yards"])["name"]

    def img(file, cap):
        return f'<p align="center"><img src="{file}" width="720" alt="{cap}"></p>\n<p align="center"><sub>{cap}</sub></p>'

    return f"""<sub>[← Portfolio](../../README.md)</sub>

# Draft 2027: Drew Mestemaker, QB, Oklahoma State
### The case for QB1: first-round production at 20, more big plays than any quarterback he is compared with, and it traveled up a level

![status: published](https://img.shields.io/badge/status-published-0b6e4f) ![season: 2026 through 9 games](https://img.shields.io/badge/season-2026%20through%209%20games-1d2433) ![method: first-round comps](https://img.shields.io/badge/method-first--round%20comps-c2410c) ![method: year-to-year stability](https://img.shields.io/badge/method-year--to--year%20stability-c2410c) ![method: bootstrap](https://img.shields.io/badge/method-bootstrap-c2410c)

**TL;DR**

- **He is my QB1.** Through {L['G']} games he has {L['Yards']:,} yards ({rk('Yards')} FBS passers), {L['TD']} touchdown passes ({rk('TD')}) and {L['YPA']:.1f} yards per attempt ({rk('YPA')}). He completes a pass of 25+ yards on {L['x25']:.1f}% of his attempts ({rk('x25')}), a higher rate than {v['x25']['beats']} of the {f['first_round_n']} first-round quarterbacks since 2021 managed in their final college season.
- **It came with him to the Big 12.** {mv['others']} other transfers made the top-100 list before and after a Group of Five to Power Four move; their passer rating changed by {mv['mean_d_rating']:+.1f} on average. His went from {mv['me_before']:.1f} to {mv['me_after']:.1f} ({mv['me_d_rating']:+.1f}).
- **The knocks are real, and the biggest one is mostly noise year to year.** His interception rate ({L['INTp']:.1f}%, {rk('INTp')}) and third-down rating ({L['r3']:.0f}, {rk('r3')}) are below average. Year to year those two repeat at r = {s['INTp']['r']:.2f} and {s['r3']['r']:.2f}; in 2025 he was at {f['line_2025']['INTp']:.1f}% and {f['line_2025']['r3']:.0f}. Darian Mensah ({mens['Rating']:.1f} rating) and Julian Sayin ({sayin['Rating']:.1f}) have been more efficient in 2026 than Mestemaker ({L['Rating']:.1f}); the case for him is volume, big plays, the tools scouts grade, and age.

{img('explosive_vs_first_round.png', 'Completions of 25+ yards per 100 attempts: Mestemaker in 2026 against the final college season of every FBS quarterback drafted in round 1 since 2021.')}

## Key numbers

| Measure | Value |
|---|---|
| 2026 passing line ({L['G']} games) | **{L['Comp']}-of-{L['Att']}, {L['Yards']:,} yards, {L['TD']} TD, {L['Int']} INT** |
| Yards per attempt / passer rating | **{L['YPA']:.1f} ({rk('YPA')}) / {L['Rating']:.1f} ({rk('Rating')})** |
| 25+ yard completions per 100 attempts | **{L['x25']:.1f} ({rk('x25')}); first-round median {v['x25']['median']:.1f}** |
| Measures (of 14) where he beats the first-round median | **{n_above}** |
| Rating change, Group of Five to Power Four (other movers' average) | **{mv['me_d_rating']:+.1f} ({mv['mean_d_rating']:+.1f})** |
| Last {f['last7']['games']} games | **{f['last7']['yards']:,} yards, {f['last7']['td']} TD, {f['last7']['int']} INT, {f['last7']['rating']:.1f} rating** |
| Interception % / third-down rating | **{L['INTp']:.1f} ({rk('INTp')}) / {L['r3']:.0f} ({rk('r3')})** |
| Year-to-year r: interception % / third-down rating / yards per game | **{s['INTp']['r']:.2f} / {s['r3']['r']:.2f} / {s['YPG']['r']:.2f}** |
| Age at the April 2027 draft (born {f['age']['born']}) | **{f['age']['at_draft']}**; nflverse lists a median age of {f['age']['first_round_median_nflverse']:.0f} for the {f['age']['first_round_total']} first-round QBs, 2021-2026 |
| NFL scouts and executives who named him the first QB off the board (ESPN, Oct. 31) | **17 of 25** |

## Why it matters for a club

- **College scouting:** the public numbers agree with the tape consensus on the strengths (arm, big plays, production) and put a size on the two concerns (interceptions, third down), so the area scout's report can be checked against a baseline.
- **General manager:** a quarterback who is 21 on draft day plays his rookie contract and fifth-year option at ages 21 through 25, a year younger than the typical first-round quarterback (nflverse lists a median age of {f['age']['first_round_median_nflverse']:.0f} for the last {f['age']['first_round_total']}).
- **Offensive staff:** he is at his best on early downs (passer rating {f['downs']['1st Down']['rating']:.0f} on first down, {f['downs']['2nd Down']['rating']:.0f} on second, {f['downs']['3rd Down']['rating']:.0f} on third). What he needs is a third-and-long plan and a staff that lives with some interceptions in exchange for the big plays.

## The question

**Is Drew Mestemaker the best quarterback in the 2027 draft?**

The league is leaning that way. ESPN's midseason poll of 25 scouts and executives gave him 17 votes as the first quarterback taken, the most in the poll's three years; he had none in August. Dane Brugler's November board has him as the top quarterback and No. 2 overall. This report asks whether the public production data backs that up, where it disagrees, and how much weight the disagreements deserve.

The background is part of the evaluation. He did not start a varsity game at quarterback at Vandegrift High in Austin, walked on at North Texas in 2024, led FBS in passing yards as a redshirt freshman in 2025, and followed Eric Morris to Oklahoma State, which went 1-11 last year and is {f['team']['wins']}-{f['team']['losses']} with him, scoring {f['team']['ppg']:.1f} points a game.

## Data

- **Season tables:** the top 100 FBS passers by yards per game in each season, 2020-2026 ({f['n_seasons']} quarterback seasons), from [cfbstats.com](https://cfbstats.com). The 2026 season runs through {THROUGH} (nine games for Oklahoma State, before Texas Tech).
- **Situational tables** (down, quarter, field zone, score, completions of 15+ and 25+ yards) for every quarterback in the 2024, 2025 and 2026 lists and for each first-round quarterback's final season.
- **Game logs and splits** for Mestemaker (2024-2026) and the 2027 class.
- **Draft results:** [nflverse](https://github.com/nflverse/nflverse-data) draft picks, 2021-2026: 19 first-round quarterbacks, 18 of them from FBS (Trey Lance played in FCS).
- **Scouting consensus,** cited where used: ESPN (Pete Thamel, Oct. 31, 2026), The Athletic's Dane Brugler via Bleacher Report (Nov. 12, 2026), PFF (Oct. 6, 2026).

## Results

### 1. His production is at the first-round standard, and his big-play rate is above it.

Against the final college season of the {f['first_round_n']} FBS quarterbacks drafted in round 1 since 2021, Mestemaker's 2026 beats the median in yards per game, yards per attempt, passer rating, touchdown rate, first downs per attempt and both explosive measures. He trails it in completion percentage, interception rate, third down and the fourth quarter.

| Measure | Mestemaker 2026 | First-round median | First-rounders he beats |
|---|---|---|---|
{fr_rows}

His closest statistical matches in that group (distance on yards per attempt, completion %, touchdown %, interception %, 25+ rate and yards per game) are {comps}. At his nine-game pace a 12-game regular season ends near {f['pace_12']['yards']:,} yards and {f['pace_12']['td']} touchdowns.

{img('national_ranks.png', 'National rank in each measure among the top 100 FBS passers by yards per game, 2026.')}

### 2. In this class, Mensah and Sayin are the more efficient passers; Mestemaker has the most volume and big plays.

| Quarterback | Team | G | Yards | TD | INT | Cmp % | Y/A | Rating | 25+ per 100 | INT % | 3rd-down rating |
|---|---|---|---|---|---|---|---|---|---|---|---|
{cls_rows}

Mensah leads this group in rating and completion percentage, Sayin in yards per attempt, and Carr in interception rate; that has to be said plainly. Mestemaker leads it in yards, touchdowns, yards per game, 25+ yard completions and rating when trailing. These seven are the quarterbacks named in ESPN's poll plus Sayin, not every eligible passer; nationally {f['x25_leader']['name']} ({f['x25_leader']['team']}) has the top 25+ rate ({f['x25_leader']['x25']:.1f} on {f['x25_leader']['att']} attempts). Dante Moore, the August favorite, played {f['moore']['games']} games ({f['moore']['yards']} yards, {f['moore']['td']} TD) before a concussion that is expected to end his season; Oklahoma State beat his Oregon team {f['oregon']['result'].split()[1]} with Mestemaker throwing for {f['oregon']['yards']} and running for {f['oregon']['rush']}.

Over the last two seasons Mestemaker has the most yards ({two_me['Yards']:,}) and touchdowns ({two_me['TD']}) of the group on {two_me['Att']:,} attempts, with a {two_me['Rating']:.1f} rating. {two_best_rate['name']} has the best two-year rating ({two_best_rate['Rating']:.1f}) and yards per attempt.

| Quarterback | Seasons in data | Att | Yards | TD | INT | Y/A | Rating | Yards per game |
|---|---|---|---|---|---|---|---|---|
{two_rows}

{img('class_map.png', 'Yards per attempt against 25+ yard completion rate for the top FBS passers; the draft-eligible class is labeled.')}

### 3. More often than not, quarterbacks lose production moving up a level. He gained.

{mv['n']} quarterbacks since 2021 transferred from a Group of Five school to a Power Four school and made the top-100 list in both seasons. The other {mv['others']} changed by {mv['mean_d_rating']:+.1f} rating points on average (median {mv['median_d_rating']:+.1f}) and {mv['mean_d_ypa']:+.2f} yards per attempt; {mv['declined']} of {mv['others']} declined. Leaving out John Mateer, whose Washington State was a two-team Pac-12 in 2024, the average is {mv['mean_d_rating_ex_mateer']:+.1f}. Mestemaker went {mv['me_before']:.1f} to {mv['me_after']:.1f} and {mv['me_d_ypa']:+.1f} yards per attempt, and his first Power Four season ranks #{mv['me_rank_after']} of the {mv['n']}. Of the {mv['started_165']} who left with a rating of 165 or better, he is the only one who kept it.

Against Power conference opponents this year: {sp['vs. FBS Power 5']['att']} attempts, {sp['vs. FBS Power 5']['ypa']:.1f} yards per attempt, {sp['vs. FBS Power 5']['td']} touchdowns, {sp['vs. FBS Power 5']['int']} interceptions, {sp['vs. FBS Power 5']['rating']:.1f} rating.

{img('g5_to_p4.png', 'Passer rating in the last Group of Five season and the first Power Four season for every quarterback who qualified in both.')}

### 4. His biggest knock, interception rate, is one of the least repeatable numbers a quarterback has.

He ranks {rk('INTp')} in interception rate and {rk('r3')} in third-down rating ({L['att3']:.0f} attempts), and his fourth-quarter rating ({L['q4']:.0f}) is {rk('q4')}. Before pricing those, check how much of each is the quarterback. For the same quarterback in back-to-back seasons:

| Measure | Year-to-year r | 95% interval | Pairs |
|---|---|---|---|
{st_rows}

Interception rate barely carries over (r = {s['INTp']['r']:.2f}), and third-down rating is weak (r = {s['r3']['r']:.2f}, on a small sample: {L['att3']:.0f} third-down attempts for him this year). His own history says the same: in 2025 he threw interceptions on {f['line_2025']['INTp']:.1f}% of attempts with a {f['line_2025']['r3']:.0f} third-down rating. Fourth-quarter rating is different: on a smaller sample it repeats about as well as overall rating (r = {s['q4']['r']:.2f}), so his drop from {f['line_2025']['q4']:.0f} in 2025 to {L['q4']:.0f} this year is the split I would watch. Volume and accuracy repeat best (yards per game r = {s['YPG']['r']:.2f}, completion % r = {s['Pct']['r']:.2f}), and he has been top two in yards per game in both seasons.

The same test cuts against his headline strength. The 25+ yard completion rate repeats at only r = {s['x25']['r']:.2f} across quarterbacks, so one season of it is weak evidence. He was #{f['ranks_2025']['x25'][0]} of {f['ranks_2025']['x25'][1]} in 2025 and is {rk('x25')} now, so there are two seasons behind it, but yards per attempt (r = {s['YPA']['r']:.2f}) is the safer number to project, and he led FBS in it in 2025 (#{f['ranks_2025']['YPA'][0]} of {f['ranks_2025']['YPA'][1]}).

{img('stability.png', 'Year-to-year correlation of each passing measure, with 95% bootstrap intervals.')}

### 5. After two rough games to open 2026, he has been the best version of himself.

Weeks 1 and 2 (Tulsa, Oregon): a {f['first2']['rating']:.1f} rating with {f['first2']['int']} interceptions on {f['first2']['att']} attempts. The {f['last7']['games']} games since: {f['last7']['comp']}-of-{f['last7']['att']}, {f['last7']['yards']:,} yards, {f['last7']['ypa']:.1f} per attempt, {f['last7']['td']} touchdowns, {f['last7']['int']} interceptions, a {f['last7']['rating']:.1f} rating, and no game below {f['last7']['min_rating']:.0f}. He has thrown for 300 yards in {f['games_300']} of {L['G']} games. On the ground: {f['rush']['att']} carries, {f['rush']['yards']} yards, {f['rush']['td']} touchdowns.

{img('game_log.png', 'Game-by-game passer rating, North Texas 2025 and Oklahoma State 2026.')}

### 6. Where the numbers say to be careful.

- **Better opponents have slowed him.** Against AP-ranked teams: {sp['vs. Ranked (AP)']['att']} attempts, {sp['vs. Ranked (AP)']['rating']:.1f} rating, {sp['vs. Ranked (AP)']['td']} touchdowns, {sp['vs. Ranked (AP)']['int']} interceptions. Against FBS teams with winning records: {sp['vs. FBS Winning']['rating']:.1f}. In losses: {sp['in Losses']['rating']:.1f}.
- **Third and long.** On third and 10 or more he is {f['downs']['3rd Down, 10+ To Go']['comp']}-of-{f['downs']['3rd Down, 10+ To Go']['att']} for {f['downs']['3rd Down, 10+ To Go']['yards']} yards ({f['downs']['3rd Down, 10+ To Go']['rating']:.0f} rating). His third-down rating is the lowest of the seven quarterbacks in the class table and would rank ahead of only {v['r3']['beats']} of the {f['first_round_n']} first-rounders.
- **Pressure.** PFF had him at a 48.8 passing grade under pressure against 90.3 from a clean pocket through Week 5 (PFF, Oct. 6, 2026), when its board had him behind Manning, Moore and Carr among quarterbacks. That is PFF's charting, not mine, and it covers his first four games.
- **Experience.** ESPN projects 27 career starts by the end of 2026. Scouts told ESPN and Brugler the same thing: the tools are there and the sample is short.
- **He may not come out.** He is a redshirt sophomore; Brugler reports scouts believe there is a good chance he declares, which is not the same as declaring.

## Verdict

**QB1, with a first-round grade.** The production is at or above the first-round median on {n_above} of 14 measures, he leads the quarterbacks compared here in yards, touchdowns and big plays, his overall efficiency held up after the step to the Big 12, he will be 21 on draft day, and ESPN's scout poll and Brugler's board both have him first. The interception and third-down numbers are worth a hard look on tape, and the data says not to overweight one season of either.

**What would change my mind:** an interception rate that stays above 2.5% over the last three regular-season games and the postseason, or Mensah holding a rating near 190 through the postseason. Mensah and Sayin are the alternatives, and on 2026 efficiency alone both are ahead of him.

## Method

- **Rates.** Touchdown % and interception % are per attempt. Adjusted yards per attempt is (yards + 20 x TD - 45 x INT) / attempts. Passer rating is the NCAA formula: (8.4 x yards + 330 x TD + 100 x completions - 200 x INT) / attempts.
- **Explosive rates** are completions of 15+ and 25+ yards per 100 attempts, from the cfbstats situational tables. Rating when trailing pools the three "losing by" score states.
- **National ranks** are among the top {f['pool']} FBS passers by yards per game, so a rank of #8 means eighth among high-volume starters, not among every quarterback who threw a pass.
- **First-round comparison.** Each first-round quarterback's final college season against Mestemaker's season in progress. Similarity is Euclidean distance on six z-scored measures.
- **Stability.** Pearson r between season t and t+1 for the same quarterback when he made the top-100 list in both, 2020-2026 for the season-table measures and 2024-2026 for the situational ones; intervals from 2,000 bootstrap samples that resample quarterbacks.
- **Moving up.** Transfers only (a quarterback whose school changed conferences is not counted). Power conferences are the ACC, Big Ten, Big 12, SEC, Notre Dame and the Pac-12 through 2023. The list of moves is in `data/g5_to_p4_moves.csv`.

## Validation

- Season totals reproduce from the game logs (the sum of nine games equals the season line), and my computed passer rating matches the cfbstats rating for the season.
- The cfbstats line ({L['Comp']}-of-{L['Att']}, {L['Yards']:,} yards, {L['TD']} TD, {L['Int']} INT) matches the line reported by USA Today on Nov. 14, 2026 and by Bleacher Report on Nov. 12.
- The cfbstats situational table counts {f['sit_att_all_plays']} attempts against {L['Att']} in the season table; the per-attempt situational rates use the situational count, and the difference does not move any figure at one decimal.
- First-round names, picks and ages come from nflverse and were checked against the 2025 and 2026 first rounds reported by ESPN.
- Stability is reported for every measure, including the one that hurts the argument (25+ rate, r = {s['x25']['r']:.2f}).

## Limitations

- **Nine games.** Every 2026 number is a partial season, and several 2026 quarterbacks in the stability and transfer samples are also mid-season.
- **Box-score data.** No air yards, pressure, drops or time to throw. The explosive measures count completions by total gain, so they include yards after the catch and credit the receivers and scheme as well as the passer.
- **System and supporting cast.** He has played both seasons in Eric Morris's offense. North Texas's 2026 quarterback, Tayven Jackson, has a {f['context']['unt_2026_rating']:.1f} rating in the offense Mestemaker left, which says the environment is quarterback-friendly. No adjustment for receivers, line or schedule strength is made here.
- **Survivor samples.** The stability and transfer samples only include quarterbacks who kept a starting job and stayed in the top 100; players who lost their jobs after moving up are missing, which makes the average mover look better than the true average.
- **Small comparison group.** Eighteen first-round quarterbacks is enough for a ranking, not for a model of NFL success.
- **No tape grades of my own** are in this report. Tools and traits are cited from published evaluations.

## Next steps

- Refresh after Texas Tech (Nov. 14) and the rest of the Big 12 schedule; the verdict section says what would move it.
- Add play-by-play: expected points per dropback, air yards, and performance under pressure and against the blitz.
- Opponent adjustment by defensive pass efficiency allowed.
- The same page for Mensah and Carr, so the class is ranked on one method.

## Reproduce

```bash
python -m projects.draft_mestemaker            # rebuilds this folder from data/
python -m projects.draft_mestemaker --refresh  # pulls the current season from cfbstats first
```

Code: [`projects/draft_mestemaker.py`](../../projects/draft_mestemaker.py). Numbers: [`findings.json`](findings.json).

## Files in this folder

| File | What it holds |
|---|---|
| `findings.json` | Every number on this page |
| `explosive_vs_first_round.png`, `national_ranks.png`, `class_map.png`, `g5_to_p4.png`, `stability.png`, `game_log.png` | The six figures |
| `class_table.csv`, `first_round_final_seasons.csv`, `g5_to_p4_table.csv`, `stability_table.csv` | The tables behind the figures |
| `data/qb_seasons_2020_2026.csv` | Top-100 passer tables, 2020-2026 |
| `data/situational_2024_2026_and_first_rounders.csv` | Situational passing tables |
| `data/gamelogs.csv`, `data/splits.csv` | Game logs and splits for Mestemaker and the class |
| `data/first_round_qbs_2021_2026.csv`, `data/g5_to_p4_moves.csv` | Draft picks and the list of moves |

**Sources:** [cfbstats.com](https://cfbstats.com/2026/player/521/50259623/index.html); [nflverse draft picks](https://github.com/nflverse/nflverse-data); [ESPN, "NFL scouts favor Drew Mestemaker as first QB taken in draft"](https://www.espn.com/college-football/story/_/id/50335830/nfl-scouts-favor-drew-mestemaker-first-qb-taken-draft); [Bleacher Report on Brugler's board](https://bleacherreport.com/articles/25532576-drew-mestemakers-nfl-draft-2027-status-addressed-nfl-scouts-brugler-ranks-qb-new-big-board); [PFF, top 10 quarterback prospects after Week 5](https://www.pff.com/news/draft-top-10-quarterback-prospects-after-week-5); [Oklahoma State roster bio](https://okstate.com/sports/football/roster/drew-mestemaker/14374); [USA Today via Yahoo Sports, Nov. 14, 2026](https://sports.yahoo.com/articles/drew-mestemaker-one-win-away-100703900.html); birth month from [Wikipedia](https://en.wikipedia.org/wiki/Drew_Mestemaker).

<sub>[← Portfolio](../../README.md)</sub>
"""


# ---------------------------------------------------------------- pull (cfbstats)
def pull(seasons=(SEASON,)):
    """Re-pull the season tables, situational tables, game logs and splits for the given seasons from cfbstats.com."""
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"

    def get(url):
        for k in range(6):
            resp = s.get(url, timeout=40)
            if resp.status_code == 200:
                time.sleep(2.5)
                return resp.text
            time.sleep(15 * (k + 1))
        resp.raise_for_status()

    seas = pd.read_csv(DATA / "qb_seasons_2020_2026.csv", dtype={"player_id": str, "team_id": str})
    sit = pd.read_csv(DATA / "situational_2024_2026_and_first_rounders.csv", dtype={"player_id": str})
    logs, splits = pd.read_csv(DATA / "gamelogs.csv"), pd.read_csv(DATA / "splits.csv")
    for y in seasons:
        h = get(f"https://cfbstats.com/{y}/leader/national/player/split01/category02/sort01.html")
        t = pd.read_html(io.StringIO(h))[0].drop(columns=["Unnamed: 0"]).rename(columns={"Pct.": "Pct", "Yards/Att": "YPA", "Yards/G": "YPG", "Att/G": "AttG"})
        ids = {html.unescape(n).strip(): (a, b) for a, b, n in re.findall(r'href="/%d/player/(\d+)/(\d+)/[^"]*">([^<]+)<' % y, h)}
        t["season"], t["team_id"], t["player_id"] = y, t.Name.map(lambda n: ids.get(n, (None, None))[0]), t.Name.map(lambda n: ids.get(n, (None, None))[1])
        t = t[t.player_id.notna()]
        seas = pd.concat([seas[seas.season != y], t])
        new = []
        for r in t.itertuples():
            tb = pd.read_html(io.StringIO(get(f"https://cfbstats.com/{y}/player/{r.team_id}/{r.player_id}/passing/situational.html")))[0]
            tb = tb[~tb.Situation.str.startswith("1st: First")].rename(columns={"Pct.": "Pct"})
            tb.insert(0, "player", r.Name), tb.insert(1, "season", y), tb.insert(2, "player_id", r.player_id)
            new.append(tb)
        sit = pd.concat([sit[sit.season != y]] + new)
        gl, spl = [], []
        for r in t[t.Name.isin(CLASS + ["Dante Moore"])].itertuples():
            base = f"https://cfbstats.com/{y}/player/{r.team_id}/{r.player_id}"
            keep = lambda d: d[d.Date.astype(str).str.match(r"\d\d/\d\d/\d\d")]  # noqa: E731
            p = keep(pd.read_html(io.StringIO(get(base + "/passing/gamelog.html")))[0]).drop(columns=["Surface"]).rename(columns={"Pct.": "Pct", "Yards/Att": "YPA"})
            ru = keep(pd.read_html(io.StringIO(get(base + "/rushing/gamelog.html")))[0]).rename(columns={"Att": "RushAtt", "Yards": "RushYards", "TD": "RushTD"})
            p = p.merge(ru[["Date", "RushAtt", "RushYards", "RushTD"]], on="Date", how="left")
            p.insert(0, "player", r.Name), p.insert(1, "season", y)
            gl.append(p)
            sp = pd.read_html(io.StringIO(get(base + "/passing/split.html")))[0].rename(columns={"Pct.": "Pct", "Yards/Att": "YPA"})
            sp = sp[~sp.Split.astype(str).str.startswith("@")]
            sp.insert(0, "player", r.Name), sp.insert(1, "season", y)
            spl.append(sp)
        logs = pd.concat([logs[logs.season != y]] + gl)
        splits = pd.concat([splits[splits.season != y]] + spl)
    seas.to_csv(DATA / "qb_seasons_2020_2026.csv", index=False)
    sit.to_csv(DATA / "situational_2024_2026_and_first_rounders.csv", index=False)
    logs.to_csv(DATA / "gamelogs.csv", index=False)
    splits.to_csv(DATA / "splits.csv", index=False)


def main():
    if "--refresh" in sys.argv:
        pull()
    f, D, G, fr, mv, cls = analyze()
    unt = D[(D.season == SEASON) & (D.Team == "N Texas")]
    f["context"] = dict(unt_2026_qb=unt.Name.iloc[0], unt_2026_rating=float(unt.Rating.iloc[0]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "findings.json").write_text(json.dumps(f, indent=1))
    cols = ["Name", "Team", "G", "Att", "Comp", "Yards", "TD", "Int", "Pct", "YPA", "AYA", "Rating", "YPG", "TDp", "INTp", "x25", "x15", "fd", "r3", "q4", "rz_td", "trail"]
    cls.reset_index()[cols].round(2).to_csv(OUT / "class_table.csv", index=False)
    fr[["Name", "season", "pick", "team", "age"] + cols[2:]].round(2).to_csv(OUT / "first_round_final_seasons.csv", index=False)
    mv[["name", "from_team", "to_team", "season_before", "season_after", "Rating_b", "Rating_a", "d_rating", "YPA_b", "YPA_a", "d_ypa"]].round(2).to_csv(OUT / "g5_to_p4_table.csv", index=False)
    pd.DataFrame(f["stability"]).T.round(3).to_csv(OUT / "stability_table.csv")
    figures(f, D, G, fr, mv, cls)
    (OUT / "README.md").write_text(readme(f))
    print(json.dumps({k: f[k] for k in ["line", "ranks", "move", "last7", "first2", "team", "age", "comps", "class_leads"]}, indent=1)[:3000])


if __name__ == "__main__":
    main()
