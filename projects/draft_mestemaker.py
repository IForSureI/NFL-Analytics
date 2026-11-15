"""Draft 2027 evaluation: Drew Mestemaker, QB, Oklahoma State. Is he QB1?

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
import math
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
                     mean_d_rating_ex_mateer=float(oth[oth.name != "John Mateer"].d_rating.mean()), declined=int((oth.d_rating < 0).sum()),
                     sd=float(oth.d_rating.std()), me_rank_change=int(mv.d_rating.rank(ascending=False).loc[mv.name == ME].iloc[0]))
    x25 = cur.sort_values("x25", ascending=False).iloc[0]
    f["x25_leader"] = dict(name=x25.Name, team=x25.Team, x25=float(x25.x25), att=int(x25.Att))
    assert f["move"]["held_165"] == 1
    return f, D, G, fr, mv, cls


# ---------------------------------------------------------------- evaluation: base rates, opponents, system
def _key(name: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", name.lower()))


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, 100 * (c - h)), min(100.0, 100 * (c + h))


def with_outcomes(D):
    """Attach each quarterback's NFL draft result (2021-2026 drafts) by name."""
    dp = pd.read_csv(DATA / "qb_draft_picks_2021_2026.csv")
    dp["k"] = dp.name.map(_key)
    D = D.assign(k=D.Name.map(_key)).merge(dp[["k", "draft", "round", "pick"]], on="k", how="left")
    now = set(D[D.season == SEASON].player_id)

    def outcome(r):
        if pd.notna(r["round"]):
            return f"round {int(r['round'])}, pick {int(r['pick'])} ({int(r['draft'])})"
        return f"in college in {SEASON}" if r.player_id in now else "not drafted"

    D["outcome"] = D.apply(outcome, axis=1)
    D["still_in_college"] = D.player_id.isin(now) & D["round"].isna()
    return D


def opp_adjusted(G, T, player, season, first_n=None):
    """FBS games only. Expected line = what each opponent allowed in its other games, weighted by his attempts."""
    g = G[(G.player == player) & (G.season == season) & G.Att.notna()].copy()
    g["d"] = pd.to_datetime(g.Date, format="%m/%d/%y")
    g = g.sort_values("d")
    if first_n:
        g = g.head(first_n)
    g["opp"] = g.Opponent.str.replace(r"^[@+] ", "", regex=True).str.replace(r"^\d+ ", "", regex=True)
    t = T[T.season == season].set_index("Name")
    g = g[g.opp.isin(t.index)]
    e = np.zeros(4)
    for r in g.itertuples():
        o = t.loc[r.opp]
        rest = o.Att - r.Att
        e += r.Att * np.array([o.Comp - r.Comp, o.Yards - r.Yards, o.TD - r.TD, o.Int - r.Int]) / rest
    att = g.Att.sum()
    act = ncaa_rating(g.Comp.sum(), att, g.Yards.sum(), g.TD.sum(), g.Int.sum())
    exp = ncaa_rating(e[0], att, e[1], e[2], e[3])
    return dict(name=player, season=int(season), games=int(len(g)), att=int(att), fbs_rating=float(act), opp_allowed=float(exp), over=float(act - exp))


def evaluate(f, D, G, SP, FR, MV):
    D = with_outcomes(D)
    me = D[(D.Name == ME) & (D.season == SEASON)].iloc[0]
    L = f["line"]

    # intervals on the two rates that carry the argument
    x25_n = int(round(L["x25"] * f["sit_att_all_plays"] / 100))
    lo, hi = wilson(x25_n, f["sit_att_all_plays"])
    ilo, ihi = wilson(L["Int"], L["Att"])
    v = f["vs_first_round"]
    f["intervals"] = dict(x25_n=x25_n, x25_att=f["sit_att_all_plays"], x25_lo=lo, x25_hi=hi, x25_contains_fr_median=bool(lo <= v["x25"]["median"] <= hi),
                          int_lo=ilo, int_hi=ihi, int_contains_fr_median=bool(ilo <= v["INTp"]["median"] <= ihi))

    # nearest seasons in the full pool, with what happened next
    prior = D[D.season < SEASON].copy()
    cols = ["YPA", "Pct", "TDp", "INTp", "YPG"]
    mu, sd = prior[cols].mean(), prior[cols].std()
    prior["dist"] = np.sqrt(((((prior[cols] - mu) / sd) - ((me[cols].astype(float) - mu) / sd)) ** 2).sum(axis=1))
    near = prior[prior.Name != ME].nsmallest(12, "dist")
    f["pool_comps"] = [dict(name=r.Name, team=r.Team, season=int(r.season), rating=float(r.Rating), ypa=float(r.YPA), tdp=float(r.TDp), intp=float(r.INTp),
                            ypg=float(r.YPG), dist=float(r.dist), outcome=r.outcome) for r in near.itertuples()]
    done = near[~near.still_in_college]
    f["pool_comps_summary"] = dict(n=int(len(near)), decided=int(len(done)), round1=int((done["round"] == 1).sum()),
                                   drafted=int(done["round"].notna().sum()), not_drafted=int(done["round"].isna().sum()), prior_seasons=int(len(prior)))

    # prior seasons at or above his rating and yards per attempt
    hi_ = prior[(prior.Rating >= me.Rating) & (prior.YPA >= me.YPA)].sort_values("Rating", ascending=False)
    qb = hi_.drop_duplicates("player_id")
    dec = qb[~qb.still_in_college]
    f["at_or_above"] = dict(seasons=int(len(hi_)), qbs=int(len(qb)), decided=int(len(dec)), round1=int((dec["round"] == 1).sum()),
                            drafted_later=int(((dec["round"] > 1)).sum()), not_drafted=int(dec["round"].isna().sum()),
                            rows=[dict(name=r.Name, team=r.Team, season=int(r.season), rating=float(r.Rating), ypa=float(r.YPA), outcome=r.outcome) for r in hi_.itertuples()])

    # P(first round) by passer rating in a quarterback's last qualifying college season
    last = prior.sort_values("season").groupby("player_id").tail(1)
    fin = last[~last.still_in_college].copy()
    bands = [(0, 130, "under 130"), (130, 145, "130 to 145"), (145, 160, "145 to 160"), (160, 175, "160 to 175"), (175, 400, "175 and up")]
    f["base_rate"] = []
    for a, b, lab in bands:
        x = fin[(fin.Rating >= a) & (fin.Rating < b)]
        f["base_rate"].append(dict(band=lab, n=int(len(x)), round1=int((x["round"] == 1).sum()), drafted=int(x["round"].notna().sum()),
                                   his_band=bool(a <= me.Rating < b)))
    f["base_rate_n"] = int(len(fin))

    # opponent adjustment
    T = pd.read_csv(DATA / "team_pass_defense_2020_2026.csv")
    cls = [opp_adjusted(G, T, n, SEASON) for n in CLASS]
    frs = [opp_adjusted(G, T, r.cfbstats_name, r.final_season) for r in FR[FR.in_fbs_data].itertuples()]
    mine = cls[0]
    f["opp"] = dict(cls=cls, first_round=frs, me_2025=opp_adjusted(G, T, ME, 2025),
                    class_rank=int(1 + sum(c["over"] > mine["over"] for c in cls)), class_n=len(cls),
                    fr_median=float(np.median([x["over"] for x in frs])), fr_beats=int(sum(x["over"] < mine["over"] for x in frs)),
                    sched_rank_easiest=int(1 + sum(c["opp_allowed"] > mine["opp_allowed"] for c in cls)))
    sp = SP[(SP.player == ME) & (SP.season == SEASON)].set_index("Split")
    f["fcs_game"] = dict(att=int(sp.loc["vs. FCS (I-AA)", "Att"]), rating=float(sp.loc["vs. FCS (I-AA)", "Rating"]))

    # first-rounders through the same number of games
    n = int(L["G"])
    rows = []
    for r in FR[FR.in_fbs_data].itertuples():
        g = G[(G.player == r.cfbstats_name) & (G.season == r.final_season) & G.Att.notna()].copy()
        g["d"] = pd.to_datetime(g.Date, format="%m/%d/%y")
        g = g.sort_values("d").head(n)
        rows.append(dict(name=r.cfbstats_name, season=int(r.final_season), games=int(len(g)), att=int(g.Att.sum()), yards=int(g.Yards.sum()), td=int(g.TD.sum()), int=int(g.Int.sum()),
                         rating=float(ncaa_rating(g.Comp.sum(), g.Att.sum(), g.Yards.sum(), g.TD.sum(), g.Int.sum())), ypa=float(g.Yards.sum() / g.Att.sum()),
                         ypg=float(g.Yards.sum() / len(g)), tdp=float(100 * g.TD.sum() / g.Att.sum()), intp=float(100 * g.Int.sum() / g.Att.sum())))
    t = pd.DataFrame(rows)
    f["same_games"] = dict(games=n, rows=rows, **{k: dict(me=float(L[m]), median=float(t[k].median()), beats=int((t[k] > L[m]).sum() if k == "intp" else (t[k] < L[m]).sum()))
                                                    for k, m in [("rating", "Rating"), ("ypa", "YPA"), ("ypg", "YPG"), ("tdp", "TDp"), ("intp", "INTp")]})

    # moving up, FBS opponents only
    fb = SP[SP.Split == "vs. FBS (I-A)"][["player", "season", "Rating"]].copy()
    fb["Rating"] = pd.to_numeric(fb.Rating)
    m = MV.merge(fb, left_on=["name", "season_before"], right_on=["player", "season"]).merge(fb, left_on=["name", "season_after"], right_on=["player", "season"], suffixes=("_b", "_a"))
    assert len(m) == len(MV)
    m["d"] = m.Rating_a - m.Rating_b
    oth, mi = m[m.name != ME], m[m.name == ME].iloc[0]
    f["move_fbs"] = dict(n=int(len(m)), me_before=float(mi.Rating_b), me_after=float(mi.Rating_a), me_d=float(mi.d), mean=float(oth.d.mean()), median=float(oth.d.median()),
                         sd=float(oth.d.std()), declined=int((oth.d < 0).sum()), others=int(len(oth)), me_rank=int(m.d.rank(ascending=False)[m.name == ME].iloc[0]),
                         me_rank_after=int(m.Rating_a.rank(ascending=False)[m.name == ME].iloc[0]), top_after=m.sort_values('Rating_a').iloc[-1]['name'],
                         z=float((mi.d - oth.d.mean()) / oth.d.std()))

    # the North Texas and Eric Morris baseline
    unt = D[(D.Team == "N Texas") & (D.season >= 2023)].sort_values("season")
    f["system"] = dict(unt=[dict(name=r.Name, season=int(r.season), rating=float(r.Rating), ypa=float(r.YPA), att=int(r.Att),
                                 coach="Eric Morris" if r.season <= 2025 else "Neal Brown") for r in unt.itertuples()])
    tj = D[(D.Name == "Tayven Jackson")].sort_values("season")
    f["system"]["successor_prior"] = dict(team=tj.iloc[-2].Team, season=int(tj.iloc[-2].season), rating=float(tj.iloc[-2].Rating)) if len(tj) > 1 else None
    f["system"]["morris_other_mean"] = float(unt[(unt.season <= 2025) & (unt.Name != ME)].Rating.mean())
    return m


# ---------------------------------------------------------------- figures
def figures(f, D, G, fr, mv, cls, mvf):
    P.style()
    cur = D[D.season == SEASON]
    me = cur[cur.Name == ME].iloc[0]

    # 1 hero: rating against what the same opponents allowed
    o = f["opp"]
    rows = [dict(lab=f"{x['name']} ({x['season']})", over=x["over"], kind="fr") for x in o["first_round"]] + \
           [dict(lab=f"{x['name']} ({x['season']})", over=x["over"], kind="me" if x["name"] == ME else "cls") for x in o["cls"]]
    d = pd.DataFrame(rows).sort_values("over")
    fig, ax = plt.subplots(figsize=(9, 8))
    col = {"fr": P.ACCENT, "cls": P.SOFT, "me": P.ACCENT2}
    ax.barh(d.lab, d.over, color=[col[k] for k in d.kind], height=0.68)
    for y, val in enumerate(d.over):
        ax.text(val + (0.8 if val >= 0 else -0.8), y, f"{val:+.0f}", va="center", ha="left" if val >= 0 else "right", fontsize=8.5)
    ax.axvline(o["fr_median"], color=P.INK, lw=1, ls="--")
    ax.set_xlabel("Passer rating minus the rating his FBS opponents allowed in their other games")
    ax.grid(axis="y", visible=False)
    P.finish(fig, ax, "Against schedule, he is mid-class and below the first-round median",
             f"Green: final season of first-round QBs, 2021-2026. Grey: 2027 class. Orange: Mestemaker. Dashed: first-round median ({o['fr_median']:+.0f})",
             OUT / "opponent_adjusted.png", SRC)

    # 1b explosive rate with its interval
    iv = f["intervals"]
    d = pd.concat([fr[["Name", "season", "x25"]], pd.DataFrame([dict(Name=ME, season=SEASON, x25=me.x25)])]).sort_values("x25").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 6.6))
    cols = [P.ACCENT2 if n == ME else P.ACCENT for n in d.Name]
    ax.barh([f"{n} ({s})" for n, s in zip(d.Name, d.season)], d.x25, color=cols, height=0.68)
    yme = int(d.index[d.Name == ME][0])
    ax.errorbar([me.x25], [yme], xerr=[[me.x25 - iv["x25_lo"]], [iv["x25_hi"] - me.x25]], fmt="none", ecolor=P.INK, lw=1.2, capsize=3)
    ax.axvline(f["vs_first_round"]["x25"]["median"], color=P.INK, lw=1, ls="--")
    ax.set_xlabel("Completions of 25+ yards per 100 attempts")
    ax.grid(axis="y", visible=False)
    P.finish(fig, ax, "His big-play rate is high, on a sample that still reaches the median",
             f"Final college season of the {len(fr)} first-round QBs, 2021-2026 (dashed: their median). His bar: {iv['x25_n']} of {iv['x25_att']} attempts, 95% interval shown",
             OUT / "explosive_vs_first_round.png", SRC)

    # 1c base rate
    b = pd.DataFrame(f["base_rate"])
    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = np.arange(len(b))
    ax.bar(x - 0.2, 100 * b.drafted / b.n, width=0.4, color=P.SOFT, label="drafted, any round")
    ax.bar(x + 0.2, 100 * b.round1 / b.n, width=0.4, color=[P.ACCENT2 if h else P.ACCENT for h in b.his_band], label="drafted in round 1")
    for i, r in b.iterrows():
        ax.text(i + 0.2, 100 * r.round1 / r.n + 1.5, f"{r.round1} of {r.n}", ha="center", fontsize=9)
    ax.set_xticks(x, b.band)
    ax.set_ylabel("% of quarterbacks")
    ax.set_xlabel("Passer rating in the last qualifying college season, 2020-2025")
    ax.legend(loc="upper left")
    ax.grid(axis="x", visible=False)
    P.finish(fig, ax, "A rating like his has meant round 1 about a third of the time",
             f"{f['base_rate_n']} quarterbacks whose last top-100 season was 2020-2025. Orange: the band his {me.Rating:.0f} falls in", OUT / "base_rate.png", SRC)

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
    P.finish(fig, ax, "Top 10 in volume and big plays, below average in two (all games)", f"Mestemaker's national rank in each measure, {SEASON} through {THROUGH}", OUT / "national_ranks.png", SRC)

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

    # 4 moving up a level, FBS opponents only
    m2 = mvf.sort_values("d").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 6.4))
    for y, r in enumerate(m2.itertuples()):
        c = P.ACCENT2 if r.name == ME else P.ACCENT
        ax.plot([r.Rating_b, r.Rating_a], [y, y], color=c, lw=2.4 if r.name == ME else 1.6, alpha=1 if r.name == ME else 0.75)
        ax.scatter([r.Rating_b], [y], s=34, facecolor=P.PLATE, edgecolor=c, zorder=3)
        ax.scatter([r.Rating_a], [y], s=46, color=c, zorder=3)
    ax.set_yticks(range(len(m2)), [f"{r.name} ({r.to_team}, {r.season_after})" for r in m2.itertuples()], fontsize=8.5)
    ax.set_xlabel("Passer rating vs FBS opponents: open dot = last Group of Five season, filled dot = first Power Four season")
    ax.grid(axis="y", visible=False)
    P.finish(fig, ax, "He held his level moving up, inside the usual spread",
             f"All {len(m2)} transfers who made the top-100 list before and after a Group of Five to Power Four move, 2021-2026, sorted by change",
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
    o, iv, sg, mf, ao, pc, sy = f["opp"], f["intervals"], f["same_games"], f["move_fbs"], f["at_or_above"], f["pool_comps_summary"], f["system"]
    N = f["first_round_n"]

    def rk(m):
        return f"#{r[m][0]} of {r[m][1]}"

    def b(name):
        return f"**{name}**" if name == ME else name

    opp = {c["name"]: c for c in o["cls"]}
    me_o = opp[ME]
    cls_rows = "\n".join(
        f"| {b(c['name'])} | {c['team']} | {c['g']} | {c['yards']:,} | {c['td']} | {c['int']} | {c['Pct']:.1f} | {c['YPA']:.1f} | {c['Rating']:.1f} | {opp[c['name']]['fbs_rating']:.1f} | {opp[c['name']]['opp_allowed']:.1f} | {opp[c['name']]['over']:+.1f} | {c['x25']:.1f} | {c['INTp']:.1f} |"
        for c in sorted(f["class"], key=lambda c: -opp[c["name"]]["over"]))
    two_rows = "\n".join(
        f"| {b(t['name'])} | {t['seasons']} | {t['Att']:,} | {t['Yards']:,} | {t['TD']} | {t['Int']} | {t['YPA']:.1f} | {t['Rating']:.1f} | {t['YPG']:.0f} |"
        for t in f["two_year"])
    sg_lab = [("ypg", "Passing yards per game"), ("ypa", "Yards per attempt"), ("rating", "Passer rating"), ("tdp", "Touchdown %"), ("intp", "Interception %")]
    sg_rows = "\n".join(f"| {lab} | {sg[k]['me']:.1f} | {sg[k]['median']:.1f} | {sg[k]['beats']} of {N} |" for k, lab in sg_lab)
    full_rows = "\n".join(f"| {LABEL[m]} | {v[m]['me']:.1f} | {v[m]['median']:.1f} | {v[m]['beats']} of {N} |" for m in ["x25", "x15", "fd", "Pct", "q4", "r3"])
    comp_rows = "\n".join(f"| {c['name']} | {c['team']} | {c['season']} | {c['rating']:.1f} | {c['ypa']:.1f} | {c['tdp']:.1f} | {c['intp']:.1f} | {c['outcome']} |" for c in f["pool_comps"])
    ao_rows = "\n".join(f"| {c['name']} | {c['team']} | {c['season']} | {c['rating']:.1f} | {c['ypa']:.1f} | {c['outcome']} |" for c in ao["rows"])
    br_rows = "\n".join(f"| {'**' + x['band'] + '**' if x['his_band'] else x['band']} | {x['n']} | {x['drafted']} | {x['round1']} | {100 * x['round1'] / x['n']:.0f}% |" for x in f["base_rate"])
    his_band = next(x for x in f["base_rate"] if x["his_band"])
    st_rows = "\n".join(f"| {LABEL[m]} | {x['r']:.2f} | {x['lo']:.2f} to {x['hi']:.2f} | {x['n']} |" for m, x in sorted(s.items(), key=lambda kv: -kv[1]["r"]))
    unt_rows = "\n".join(f"| {u['season']} | {u['name']} | {u['coach']} | {u['att']} | {u['ypa']:.1f} | {u['rating']:.1f} |" for u in sy["unt"])
    sp = f["splits"]
    mens, sayin, carr = (next(c for c in f["class"] if c["name"] == n) for n in ["Darian Mensah", "Julian Sayin", "CJ Carr"])
    two_best = max(f["two_year"], key=lambda t: t["Rating"])
    two_me = next(t for t in f["two_year"] if t["name"] == ME)
    assert max(f["two_year"], key=lambda t: t["TD"])["name"] == ME == max(f["two_year"], key=lambda t: t["Yards"])["name"]
    raw_rank = 1 + sum(c["Rating"] > L["Rating"] for c in f["class"])
    succ = sy["successor_prior"]
    unt26 = sy["unt"][-1]
    succ_txt = (", up from " + format(succ["rating"], ".1f") + " at " + succ["team"] + " in " + str(succ["season"])) if succ else ""
    contains = "contains" if iv["x25_contains_fr_median"] else "sits above"
    int_contains = "contains" if iv["int_contains_fr_median"] else "sits above"

    def img(file, cap):
        return f'<p align="center"><img src="{file}" width="720" alt="{cap}"></p>\n<p align="center"><sub>{cap}</sub></p>'

    return f"""<sub>[← Portfolio](../../README.md)</sub>

# Draft 2027 evaluation: Drew Mestemaker, QB, Oklahoma State
### Is he QB1? The scouts say yes. The production says first-round candidate, and does not separate him from Mensah or Sayin

![status: published](https://img.shields.io/badge/status-published-0b6e4f) ![season: 2026 through {L['G']} games](https://img.shields.io/badge/season-2026%20through%20{L['G']}%20games-1d2433) ![method: base rates](https://img.shields.io/badge/method-base%20rates-c2410c) ![method: opponent adjustment](https://img.shields.io/badge/method-opponent%20adjustment-c2410c) ![method: year-to-year stability](https://img.shields.io/badge/method-year--to--year%20stability-c2410c)

**TL;DR**

- **Grade: first-round candidate. The numbers alone do not make him QB1.** Through {L['G']} games he has {L['Yards']:,} yards ({rk('Yards')} FBS passers), {L['TD']} touchdown passes ({rk('TD')}) and a {L['Rating']:.1f} rating, close to what the {N} first-round quarterbacks since 2021 had through the same {sg['games']} games (median {sg['rating']['median']:.1f}; he is ahead of {sg['rating']['beats']} of {N} on rating and {sg['ypg']['beats']} of {N} on yards per game).
- **Against schedule he is #{o['class_rank']} of {o['class_n']} in this class.** His rating against FBS opponents is {me_o['over']:+.1f} above what those defenses allowed in their other games. Darian Mensah is {opp['Darian Mensah']['over']:+.1f} and Julian Sayin {opp['Julian Sayin']['over']:+.1f}; the first-round median is {o['fr_median']:+.1f}, and he is ahead of {o['fr_beats']} of {N}. His opponents have been the easiest pass defenses any of the seven has faced.
- **Similar college lines have gone anywhere from pick 1 to undrafted.** Of the {his_band['n']} quarterbacks since 2020 whose last college season had a rating of {his_band['band']}, {his_band['round1']} went in round 1. The case for QB1 is outside the box score: 17 of 25 NFL scouts and executives named him the first quarterback off the board (ESPN, Oct. 31), he leads the country in touchdown passes, and he will be 21 on draft day.

{img('opponent_adjusted.png', 'Passer rating against FBS opponents minus the rating those opponents allowed in their other games: first-round quarterbacks in their final college season, the 2027 class, and Mestemaker.')}

## Key numbers

| Measure | Value |
|---|---|
| 2026 passing line ({L['G']} games, before Texas Tech) | **{L['Comp']}-of-{L['Att']}, {L['Yards']:,} yards, {L['TD']} TD, {L['Int']} INT** |
| Passer rating: all games / FBS opponents only | **{L['Rating']:.1f} ({rk('Rating')}) / {me_o['fbs_rating']:.1f}** |
| Rating over what his FBS opponents allowed | **{me_o['over']:+.1f}** (#{o['class_rank']} of {o['class_n']} in the class; first-round median {o['fr_median']:+.1f}) |
| Rating through {sg['games']} games vs first-round QBs through {sg['games']} games | **{sg['rating']['me']:.1f} vs median {sg['rating']['median']:.1f}** (ahead of {sg['rating']['beats']} of {N}) |
| Round 1 rate, last-season rating {his_band['band']} | **{his_band['round1']} of {his_band['n']}** |
| Nearest {pc['n']} prior seasons in the full pool: round 1 / drafted later / not drafted / still in college | **{pc['round1']} / {pc['drafted'] - pc['round1']} / {pc['not_drafted']} / {pc['n'] - pc['decided']}** |
| 25+ yard completions per 100 attempts (95% interval) | **{L['x25']:.1f} ({iv['x25_lo']:.1f} to {iv['x25_hi']:.1f})**; first-round median {v['x25']['median']:.1f} |
| Interception % (95% interval) | **{L['INTp']:.1f} ({iv['int_lo']:.1f} to {iv['int_hi']:.1f})**, {rk('INTp')} |
| Rating change vs FBS opponents, North Texas to Oklahoma State | **{mf['me_d']:+.1f}** (other {mf['others']} movers: mean {mf['mean']:+.1f}, SD {mf['sd']:.1f}) |
| NFL scouts and executives naming him the first QB taken (ESPN, Oct. 31) | **17 of 25** |
| Age at the April 2027 draft (born {f['age']['born']}) | **{f['age']['at_draft']}** |

## Why it matters for a club

- **College scouting:** the tape consensus has him first. This page gives the area scout the base rates and the schedule context to test that against, and names the two quarterbacks whose production is better.
- **General manager:** production like his has been a first-round profile about a third of the time. Taking him first is a bet on traits and age, so the tape and the interviews have to carry it.
- **Offensive staff:** he is at his best on early downs (passer rating {f['downs']['1st Down']['rating']:.0f} on first down, {f['downs']['2nd Down']['rating']:.0f} on second, {f['downs']['3rd Down']['rating']:.0f} on third) and has needed a third-and-long answer.

## The question

**Is Drew Mestemaker the best quarterback in the 2027 draft?**

The league is leaning that way. ESPN's midseason poll of 25 scouts and executives gave him 17 votes as the first quarterback taken, the most in the poll's three years; he had none in August. Dane Brugler's November board has him as the top quarterback and No. 2 overall. I started this page expecting the production data to agree. It agrees that he belongs in the first-round conversation. It does not show that he is better than Mensah or Sayin, and this page says so.

The background is part of the evaluation. He did not start a varsity game at quarterback at Vandegrift High in Austin, walked on at North Texas in 2024, led FBS in passing yards as a redshirt freshman in 2025, and followed Eric Morris to Oklahoma State, which went 1-11 last year and is {f['team']['wins']}-{f['team']['losses']} with him, scoring {f['team']['ppg']:.1f} points a game.

## Data

- **Season tables:** the top 100 FBS passers by yards per game in each season, 2020-2026 ({f['n_seasons']} quarterback seasons), from [cfbstats.com](https://cfbstats.com). The 2026 season runs through {THROUGH}: nine games for Oklahoma State. The Texas Tech game on Nov. 14 is not in these numbers.
- **Situational tables** for every quarterback in the 2024, 2025 and 2026 lists and for each first-round quarterback's final season.
- **Game logs and splits** for Mestemaker (2024-2026), the 2027 class, every first-round quarterback's final season, and the 20 transfers in result 5.
- **Team pass defense,** every FBS team, 2020-2026 (cfbstats national tables), for the opponent adjustment.
- **Draft results:** [nflverse](https://github.com/nflverse/nflverse-data) draft picks, 2021-2026: 68 drafted quarterbacks, 19 in round 1, 18 of those from FBS (Trey Lance played in FCS).
- **Scouting consensus,** cited where used: ESPN (Pete Thamel, Oct. 31, 2026), The Athletic's Dane Brugler via Bleacher Report (Nov. 12, 2026), PFF (Oct. 6, 2026).

## Results

### 1. Through nine games his raw line is near the first-round median: ahead on volume, behind on interceptions.

First-round quarterbacks are compared here through their first {sg['games']} games of their final college season, so the comparison is nine games against nine.

| Measure, first {sg['games']} games | Mestemaker 2026 | First-round median | First-rounders he is ahead of |
|---|---|---|---|
{sg_rows}

Situational measures are only available for full seasons, so these compare his nine games with their whole season, bowl and playoff games included:

| Measure | Mestemaker, 9 games | First-round median, full season | First-rounders he is ahead of |
|---|---|---|---|
{full_rows}

These measures overlap heavily (rating is built from yards, touchdowns and interceptions per attempt), so they are one or two independent looks, not eleven. At his nine-game pace a 12-game regular season ends near {f['pace_12']['yards']:,} yards and {f['pace_12']['td']} touchdowns.

{img('national_ranks.png', 'National rank in each measure among the top 100 FBS passers by yards per game, 2026, all games.')}

### 2. Against the defenses he has faced, he is fourth of seven in the class and below most first-rounders.

For each FBS game I take what that opponent allowed to every other passing offense this season, weight it by his attempts, and compare. The FCS game (Murray State: {f['fcs_game']['att']} attempts, {f['fcs_game']['rating']:.1f} rating) is out.

| Quarterback | Team | G | Yards | TD | INT | Cmp % | Y/A | Rating, all games | Rating vs FBS | What those defenses allow | Over expected | 25+ per 100 | INT % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
{cls_rows}

- His opponents allow a {me_o['opp_allowed']:.1f} rating to everyone else, the most generous schedule of the seven (#{o['sched_rank_easiest']} easiest).
- He is {me_o['over']:+.1f} over expected. Mensah ({opp['Darian Mensah']['over']:+.1f}) and Sayin ({opp['Julian Sayin']['over']:+.1f}) are about twice that. He is level with Carr ({opp['CJ Carr']['over']:+.1f}).
- The same measure for the {N} first-round quarterbacks' final seasons has a median of {o['fr_median']:+.1f}. He is ahead of {o['fr_beats']} of them. His own 2025 at North Texas was {o['me_2025']['over']:+.1f}.
- On unadjusted rating he is #{raw_rank} of the seven. He leads the group in yards, touchdowns, yards per game and 25+ yard completions.

These seven are the quarterbacks named in ESPN's poll plus Sayin, not every eligible passer; nationally {f['x25_leader']['name']} ({f['x25_leader']['team']}) has the top 25+ rate ({f['x25_leader']['x25']:.1f} on {f['x25_leader']['att']} attempts). Dante Moore, the August favorite, played {f['moore']['games']} games ({f['moore']['yards']} yards, {f['moore']['td']} TD) before a concussion that is expected to end his season; Oklahoma State beat his Oregon team {f['oregon']['result'].split()[1]} with Mestemaker throwing for {f['oregon']['yards']} and running for {f['oregon']['rush']}.

Over the last two seasons Mestemaker has the most yards ({two_me['Yards']:,}) and touchdowns ({two_me['TD']}) of the group on {two_me['Att']:,} attempts, with a {two_me['Rating']:.1f} rating. {two_best['name']} has the best two-year rating ({two_best['Rating']:.1f}).

| Quarterback | Seasons in data | Att | Yards | TD | INT | Y/A | Rating | Yards per game |
|---|---|---|---|---|---|---|---|---|
{two_rows}

{img('class_map.png', 'Yards per attempt against 25+ yard completion rate for the top FBS passers; the draft-eligible class is labeled.')}

### 3. College seasons like his have produced first-round picks, day-three picks and undrafted players.

The nearest {pc['n']} seasons to his 2026 among all {pc['prior_seasons']} qualifying seasons from 2020 to 2025 (distance on yards per attempt, completion %, touchdown %, interception % and yards per game):

| Quarterback | Team | Season | Rating | Y/A | TD % | INT % | What happened |
|---|---|---|---|---|---|---|---|
{comp_rows}

Of the {pc['decided']} whose draft outcome is known, {pc['round1']} went in round 1, {pc['drafted'] - pc['round1']} were drafted later and {pc['not_drafted']} were not drafted. Several of these are not a quarterback's final season, so the outcome is what eventually happened to the player.

Every prior season at or above both his rating ({L['Rating']:.1f}) and his yards per attempt ({L['YPA']:.1f}): {ao['seasons']} seasons by {ao['qbs']} quarterbacks. Of those quarterbacks, {ao['round1']} went in round 1, {ao['drafted_later']} were drafted later and {ao['not_drafted']} were not drafted.

| Quarterback | Team | Season | Rating | Y/A | What happened |
|---|---|---|---|---|---|
{ao_rows}

The base rate by rating, for the {f['base_rate_n']} quarterbacks whose last top-100 season came in 2020-2025:

| Rating in last qualifying season | Quarterbacks | Drafted | Round 1 | Round 1 rate |
|---|---|---|---|---|
{br_rows}

Production gets a quarterback into the conversation. It has not been enough to make one a first-round pick, and the players who were not drafted from the top of this list were mostly from Group of Five schools, which is the question he had to answer by moving up.

{img('base_rate.png', 'Share of quarterbacks drafted, and drafted in round 1, by passer rating in their last qualifying college season, 2020-2025.')}

### 4. He held his level moving from the American to the Big 12, which is better than the typical mover and inside the normal spread.

{mf['n']} quarterbacks since 2021 transferred from a Group of Five school to a Power Four school and made the top-100 list in both seasons. Against FBS opponents only:

- His rating went from {mf['me_before']:.1f} to {mf['me_after']:.1f} ({mf['me_d']:+.1f}).
- The other {mf['others']} changed by {mf['mean']:+.1f} on average (median {mf['median']:+.1f}); {mf['declined']} of {mf['others']} declined. The standard deviation is {mf['sd']:.1f} points, so his change is {mf['z']:+.1f} SD from the average: not distinguishable from a typical move.
- His change ranks #{mf['me_rank']} of {mf['n']}. His level after the move ranks #{mf['me_rank_after']} of {mf['n']}; {mf['top_after']} is first.
- Counting all games, his rating rose {mv['me_d_rating']:+.1f} ({mv['me_before']:.1f} to {mv['me_after']:.1f}). That gain comes from the Murray State game.
- He moved with his head coach and offense. This is a test of better opponents, not of a new system.

Against Power conference opponents this year: {sp['vs. FBS Power 5']['att']} attempts, {sp['vs. FBS Power 5']['ypa']:.1f} yards per attempt, {sp['vs. FBS Power 5']['td']} touchdowns, {sp['vs. FBS Power 5']['int']} interceptions, {sp['vs. FBS Power 5']['rating']:.1f} rating.

{img('g5_to_p4.png', 'Passer rating against FBS opponents in the last Group of Five season and the first Power Four season, for every transfer who qualified in both.')}

### 5. The setting he came from is friendly to quarterbacks, and the coach is only part of it.

North Texas starters in this data:

| Season | Quarterback | Head coach | Att | Y/A | Rating |
|---|---|---|---|---|---|
{unt_rows}

- Under Morris, the two North Texas starters before him averaged a {sy['morris_other_mean']:.1f} rating. He was {f['line_2025']['Rating'] - sy['morris_other_mean']:.0f} points better in the same offense ({f['line_2025']['Rating']:.1f}), which is evidence for the player.
- After he and Morris left, {unt26['name']} has a {unt26['rating']:.1f} rating there under a new staff{succ_txt}. That is evidence that the schedule and setting at North Texas lift a passer's numbers, whoever coaches.
- Both readings are true at once, and this data cannot split them. No adjustment for receivers or line is made here.

### 6. His weakest numbers are noisy ones, and so is his best one.

He ranks {rk('INTp')} in interception rate and {rk('r3')} in third-down rating ({L['att3']:.0f} attempts), and his fourth-quarter rating ({L['q4']:.0f}) is {rk('q4')}. For the same quarterback in back-to-back seasons:

| Measure | Year-to-year r | 95% interval | Pairs |
|---|---|---|---|
{st_rows}

- **Interceptions.** {L['Int']} in {L['Att']} attempts is {L['INTp']:.1f}%, with a 95% interval of {iv['int_lo']:.1f} to {iv['int_hi']:.1f} that {int_contains} the first-round median ({v['INTp']['median']:.1f}). Interception rate barely carries over year to year (r = {s['INTp']['r']:.2f}); in 2025 he was at {f['line_2025']['INTp']:.1f}%.
- **Third down.** r = {s['r3']['r']:.2f}, on a small sample ({L['att3']:.0f} attempts for him this year). In 2025 his third-down rating was {f['line_2025']['r3']:.0f}.
- **Fourth quarter.** On a smaller sample it repeats about as well as overall rating (r = {s['q4']['r']:.2f}), so his drop from {f['line_2025']['q4']:.0f} in 2025 to {L['q4']:.0f} is the split I would watch.
- **Big plays.** {iv['x25_n']} completions of 25+ yards in {iv['x25_att']} attempts is {L['x25']:.1f}%, {rk('x25')} nationally and above {v['x25']['beats']} of {N} first-rounders' full seasons. The 95% interval is {iv['x25_lo']:.1f} to {iv['x25_hi']:.1f}, which {contains} the first-round median ({v['x25']['median']:.1f}), and the rate repeats at only r = {s['x25']['r']:.2f} across quarterbacks. He was #{f['ranks_2025']['x25'][0]} of {f['ranks_2025']['x25'][1]} in 2025. Yards per attempt (r = {s['YPA']['r']:.2f}) is the safer number, and he led FBS in it in 2025.

{img('stability.png', 'Year-to-year correlation of each passing measure, with 95% bootstrap intervals.')}

{img('explosive_vs_first_round.png', 'Completions of 25+ yards per 100 attempts, with the 95% interval on his nine-game rate.')}

### 7. Recent form is strong, and the hardest games have been his worst.

- Weeks 1 and 2 (Tulsa, Oregon): a {f['first2']['rating']:.1f} rating with {f['first2']['int']} interceptions on {f['first2']['att']} attempts. The {f['last7']['games']} games since: {f['last7']['comp']}-of-{f['last7']['att']}, {f['last7']['yards']:,} yards, {f['last7']['td']} touchdowns, {f['last7']['int']} interceptions, a {f['last7']['rating']:.1f} rating (one of the seven is the FCS game).
- 300 yards in {f['games_300']} of {L['G']} games. On the ground: {f['rush']['att']} carries, {f['rush']['yards']} yards, {f['rush']['td']} touchdowns.
- Against AP-ranked teams: {sp['vs. Ranked (AP)']['att']} attempts, {sp['vs. Ranked (AP)']['rating']:.1f} rating, {sp['vs. Ranked (AP)']['td']} touchdowns, {sp['vs. Ranked (AP)']['int']} interceptions. Against FBS teams with winning records: {sp['vs. FBS Winning']['rating']:.1f}. In losses: {sp['in Losses']['rating']:.1f}.
- On third and 10 or more he is {f['downs']['3rd Down, 10+ To Go']['comp']}-of-{f['downs']['3rd Down, 10+ To Go']['att']} for {f['downs']['3rd Down, 10+ To Go']['yards']} yards.

{img('game_log.png', 'Game-by-game passer rating, North Texas 2025 and Oklahoma State 2026.')}

### 8. What the scouts add, which this data cannot measure.

- **Consensus.** 17 of 25 in ESPN's poll; top quarterback and No. 2 overall on Brugler's board.
- **Tools, as cited.** ESPN's scouts point to size and arm ("arm talent, power and accuracy," one said). Brugler cites tools, passing instincts and toughness.
- **Pressure.** PFF had him at a 48.8 passing grade under pressure against 90.3 from a clean pocket through Week 5 (Oct. 6, 2026), when its board had him behind Manning, Moore and Carr among quarterbacks. That is PFF's charting over his first four games.
- **Experience.** ESPN projects 27 career starts by the end of 2026.
- **He may not come out.** He is a redshirt sophomore; Brugler reports scouts believe there is a good chance he declares.
- **Age.** Born {f['age']['born']}, he will be {f['age']['at_draft']} at the draft.

## Verdict

**What the evidence on this page supports**

| For QB1 | Against QB1 |
|---|---|
| 17 of 25 scouts and executives, and Brugler's board | Mensah ({opp['Darian Mensah']['over']:+.1f}) and Sayin ({opp['Julian Sayin']['over']:+.1f}) are far ahead of his {me_o['over']:+.1f} against schedule |
| #1 in touchdown passes and #2 in yards in FBS | The easiest set of pass defenses of the seven quarterbacks compared |
| Raw line near the first-round median through nine games, ahead of {sg['ypg']['beats']} of {N} in yards per game | Ahead of only {o['fr_beats']} of {N} first-rounders once opponents are counted |
| Held his level moving up a conference | {his_band['round1']} of {his_band['n']} quarterbacks with a last-season rating like his went in round 1 |
| 21 on draft day; two seasons as a starter | {rk('INTp')} in interception rate; {sp['vs. Ranked (AP)']['rating']:.1f} rating against ranked teams |

**Grade:** first-round candidate. On production he is in the top four of this class, behind Mensah and Sayin and level with Carr.

**My call, and it is an opinion:** I would still have him first, because the people who grade arms for a living do, because of his age, and because he was {f['line_2025']['Rating'] - sy['morris_other_mean']:.0f} points better than the two quarterbacks who ran the same offense before him. The numbers on this page do not prove that. If the draft were decided on college production against schedule, Mensah would be first.

**What would move it:** up, if he plays to his season line against Texas Tech and the better defenses left; down, if the interception rate stays above 2.5% or Mensah and Sayin hold their margins through the postseason.

## Method

- **Rates.** Touchdown % and interception % are per attempt. Passer rating is the NCAA formula: (8.4 x yards + 330 x TD + 100 x completions - 200 x INT) / attempts.
- **Opponent adjustment.** FBS games only. For each game, the opponent's season passing line allowed, minus this quarterback's own game, gives what that defense allows per attempt to everyone else. Those rates times his attempts, summed over games, give an expected line and an expected rating. "Over expected" is his FBS rating minus that. It adjusts for pass defense only, and an opponent's other games are against different offenses.
- **Same-games comparison.** Each first-round quarterback's first {sg['games']} games of his final college season from the game logs (Justin Fields played eight in 2020).
- **Full-pool comps.** Euclidean distance on five z-scored measures across all prior qualifying seasons. Draft outcomes are matched by name to nflverse picks, 2021-2026; "not drafted" means not drafted through 2026 and not in the 2026 college data.
- **Base rate.** One row per quarterback: his last top-100 season, 2020-2025, excluding anyone still playing college football in 2026.
- **Intervals.** Wilson 95% intervals on the per-attempt rates. Year-to-year r from quarterbacks on the top-100 list in back-to-back seasons, with 2,000 bootstrap samples that resample quarterbacks.
- **Moving up.** Transfers only. Power conferences are the ACC, Big Ten, Big 12, SEC, Notre Dame and the Pac-12 through 2023. Ratings are from the "vs. FBS" split. The list is in `data/g5_to_p4_moves.csv`.
- **National ranks** are among the top {f['pool']} FBS passers by yards per game, all games.

## Validation

- Season totals reproduce from the game logs, and my computed passer rating matches the cfbstats rating.
- The cfbstats line ({L['Comp']}-of-{L['Att']}, {L['Yards']:,} yards, {L['TD']} TD, {L['Int']} INT) matches the line reported by USA Today on Nov. 14, 2026 and by Bleacher Report on Nov. 12.
- All 18 FBS first-round quarterbacks, all 20 movers and all seven class quarterbacks have complete game logs or splits; tests fail if one is missing.
- The cfbstats situational table counts {f['sit_att_all_plays']} attempts against {L['Att']} in the season table; the per-attempt situational rates use the situational count.
- Results that cut against the scouting consensus are reported at the same weight as the ones that support it.

## Limitations

- **Nine games.** Every 2026 number is a partial season, and the opponent ratings behind the adjustment are nine-game samples too.
- **Box-score data.** No air yards, pressure, drops or time to throw. The explosive measures count completions by total gain, so they credit receivers and scheme as well as the passer.
- **The opponent adjustment is simple.** One number per defense, no adjustment for the offenses that defense faced, none for receivers or line.
- **Survivor samples.** The stability, transfer and base-rate samples only include quarterbacks who made a top-100 list. "Not drafted" includes players who lost jobs or were hurt.
- **Name matching** to draft picks can miss a player whose name is listed differently; the 68 drafted quarterbacks were checked by hand, and the five from FCS schools are not in the college data.
- **Small groups.** Eighteen first-round quarterbacks and {his_band['n']} quarterbacks in his rating band are enough for a base rate, not for a model.
- **No tape grades of my own** are in this report. Tools and traits are cited from published evaluations.

## Next steps

- Refresh after Texas Tech (Nov. 14) and each game left.
- Play-by-play: expected points per dropback, air yards, pressure and blitz splits.
- A fuller opponent model (offense and defense together) and the same page for Mensah, Sayin and Carr.
- NFL outcomes for the comparison seasons, once the 2024-2026 classes have played enough.

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
| `opponent_adjusted.png`, `national_ranks.png`, `class_map.png`, `base_rate.png`, `g5_to_p4.png`, `stability.png`, `explosive_vs_first_round.png`, `game_log.png` | The eight figures |
| `class_table.csv`, `first_round_final_seasons.csv`, `g5_to_p4_table.csv`, `stability_table.csv`, `opponent_adjusted.csv`, `pool_comps.csv` | The tables behind the figures |
| `data/qb_seasons_2020_2026.csv` | Top-100 passer tables, 2020-2026 |
| `data/situational_2024_2026_and_first_rounders.csv` | Situational passing tables |
| `data/gamelogs.csv`, `data/splits.csv` | Game logs and splits |
| `data/team_pass_defense_2020_2026.csv` | Passing allowed by every FBS defense |
| `data/first_round_qbs_2021_2026.csv`, `data/qb_draft_picks_2021_2026.csv`, `data/g5_to_p4_moves.csv` | Draft picks and the list of moves |

**Sources:** [cfbstats.com](https://cfbstats.com/2026/player/521/50259623/index.html); [nflverse draft picks](https://github.com/nflverse/nflverse-data); [ESPN, "NFL scouts favor Drew Mestemaker as first QB taken in draft"](https://www.espn.com/college-football/story/_/id/50335830/nfl-scouts-favor-drew-mestemaker-first-qb-taken-draft); [Bleacher Report on Brugler's board](https://bleacherreport.com/articles/25532576-drew-mestemakers-nfl-draft-2027-status-addressed-nfl-scouts-brugler-ranks-qb-new-big-board); [PFF, top 10 quarterback prospects after Week 5](https://www.pff.com/news/draft-top-10-quarterback-prospects-after-week-5); [Oklahoma State roster bio](https://okstate.com/sports/football/roster/drew-mestemaker/14374) and [Eric Morris staff bio](https://www.okstate.com/staff-directory/eric-morris/3991); [Fox Sports on Neal Brown replacing Morris at North Texas](https://www.foxsports.com/articles/cfb/no-20-north-texas-names-neal-brown-to-replace-oklahoma-stbound-eric-morris-after-season); [USA Today via Yahoo Sports, Nov. 14, 2026](https://sports.yahoo.com/articles/drew-mestemaker-one-win-away-100703900.html); birth month from [Wikipedia](https://en.wikipedia.org/wiki/Drew_Mestemaker).

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
    td = pd.read_csv(DATA / "team_pass_defense_2020_2026.csv")
    for y in seasons:
        t = pd.read_html(io.StringIO(get(f"https://cfbstats.com/{y}/leader/national/team/defense/split01/category02/sort01.html")))[0]
        t = t.drop(columns=["Unnamed: 0", "Att/G", "Yards/G"]).rename(columns={"Pct.": "Pct", "Yards/Att": "YPA"})
        t["season"] = y
        td = pd.concat([td[td.season != y], t])
    td.to_csv(DATA / "team_pass_defense_2020_2026.csv", index=False)
    seas.to_csv(DATA / "qb_seasons_2020_2026.csv", index=False)
    sit.to_csv(DATA / "situational_2024_2026_and_first_rounders.csv", index=False)
    logs.to_csv(DATA / "gamelogs.csv", index=False)
    splits.to_csv(DATA / "splits.csv", index=False)


def main():
    if "--refresh" in sys.argv:
        pull()
    f, D, G, fr, mv, cls = analyze()
    _, _, SP, FR, MV = load()
    unt = D[(D.season == SEASON) & (D.Team == "N Texas")]
    f["context"] = dict(unt_2026_qb=unt.Name.iloc[0], unt_2026_rating=float(unt.Rating.iloc[0]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "findings.json").write_text(json.dumps(f, indent=1))
    cols = ["Name", "Team", "G", "Att", "Comp", "Yards", "TD", "Int", "Pct", "YPA", "AYA", "Rating", "YPG", "TDp", "INTp", "x25", "x15", "fd", "r3", "q4", "rz_td", "trail"]
    cls.reset_index()[cols].round(2).to_csv(OUT / "class_table.csv", index=False)
    fr[["Name", "season", "pick", "team", "age"] + cols[2:]].round(2).to_csv(OUT / "first_round_final_seasons.csv", index=False)
    mv[["name", "from_team", "to_team", "season_before", "season_after", "Rating_b", "Rating_a", "d_rating", "YPA_b", "YPA_a", "d_ypa"]].round(2).to_csv(OUT / "g5_to_p4_table.csv", index=False)
    pd.DataFrame(f["stability"]).T.round(3).to_csv(OUT / "stability_table.csv")
    mvf = evaluate(f, D, G, SP, FR, MV)
    (OUT / "findings.json").write_text(json.dumps(f, indent=1))
    o = f["opp"]
    pd.DataFrame([dict(group="2027 class", **x) for x in o["cls"]] + [dict(group="first round, final season", **x) for x in o["first_round"]]).round(2).to_csv(OUT / "opponent_adjusted.csv", index=False)
    pd.DataFrame(f["pool_comps"]).round(2).to_csv(OUT / "pool_comps.csv", index=False)
    figures(f, D, G, fr, mv, cls, mvf)
    (OUT / "README.md").write_text(readme(f))
    print(json.dumps({k: f[k] for k in ["line", "ranks", "move", "last7", "first2", "team", "age", "comps", "class_leads"]}, indent=1)[:3000])


if __name__ == "__main__":
    main()
