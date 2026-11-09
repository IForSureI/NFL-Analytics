"""2026 In-Season Snippets, interactive: the twelve charts as one web page where every player and team opens
its breakdown on hover (tap on a phone, focus with the keyboard).

The page reads the same play-by-play file through the same filters as projects/in_season_snippets.py, and the
build stops if any headline number differs from reports/2026-in-season-snippets/findings.json, so the
interactive charts can't drift from the published ones. Rebuilt by scripts/update.py after the snippets.

    python -m projects.in_season_web      # -> docs/snippets.html

Data: nflverse play-by-play (CC-BY 4.0) and nflverse team colors.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from nflan import data
from projects import in_season_snippets as sn

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "snippets.html"
TEMPLATE = Path(__file__).with_name("in_season_web.html")
FINDINGS = sn.OUT / "findings.json"

EXTRA = ["pass_length", "pass_location", "home_team", "away_team", "home_score", "away_score", "touchdown",
         "interception", "fumble_lost", "rushing_yards", "first_down", "qtr"]


def r3(x):
    return None if x is None or pd.isna(x) else round(float(x), 3)


def r1(x):
    return None if x is None or pd.isna(x) else round(float(x), 1)


def load():
    """The snippets' own rows (regular season, completed weeks), with a few extra columns for the breakdowns."""
    p, weeks = sn.load(False)
    x = pd.read_parquet(data.pbp_path(sn.SEASON), columns=["game_id", "play_id"] + EXTRA)
    full = pd.read_parquet(data.pbp_path(sn.SEASON), columns=["game_id", "play_id", "season_type", "week"])
    full = full[(full.season_type == "REG") & full.week.isin(weeks)]
    if len(full) != len(p):
        raise SystemExit("row mismatch with the snippets' load()")
    p = p.reset_index(drop=True).assign(play_id=full.play_id.to_numpy(), _gid=full.game_id.to_numpy())
    if not (p._gid == p.game_id).all():
        raise SystemExit("row order mismatch with the snippets' load()")
    return p.drop(columns="_gid").merge(x, on=["game_id", "play_id"], how="left"), weeks


def weekly(s: pd.Series, weeks) -> list:
    return [r3(s.get(w)) for w in weeks]


def records(p) -> dict:
    g = p.groupby("game_id").agg(home=("home_team", "first"), away=("away_team", "first"),
                                 hs=("home_score", "max"), as_=("away_score", "max"))
    out = {}
    for t in set(g.home) | set(g.away):
        h, a = g[g.home == t], g[g.away == t]
        w = int((h.hs > h.as_).sum() + (a.as_ > a.hs).sum())
        l = int((h.hs < h.as_).sum() + (a.as_ < a.hs).sum())
        out[t] = {"w": w, "l": l, "t": int(len(h) + len(a) - w - l),
                  "pf": int(h.hs.sum() + a.as_.sum()), "pa": int(h.as_.sum() + a.hs.sum())}
    return out


def depth_band(ay):
    return np.select([ay < 0, ay < 10, ay < 20], ["Behind LOS", "0-9 yds", "10-19 yds"], "20+ yds")


def qb_profile(pid, p, weeks):
    db = p[(p.id == pid) & (p.qb_dropback == 1) & p.epa.notna() & (p.two_point_attempt != 1)]
    att = p[(p.passer_player_id == pid) & (p.pass_attempt == 1) & (p.sack != 1) & (p.two_point_attempt != 1)].copy()
    att["band"] = depth_band(att.air_yards.fillna(0))
    bands = []
    for b in ["Behind LOS", "0-9 yds", "10-19 yds", "20+ yds"]:
        q = att[att.band == b]
        if len(q):
            bands.append({"band": b, "att": int(len(q)), "comp": r3(q.complete_pass.mean()), "epa": r3(q.epa.mean())})
    downs = [{"down": int(d), "n": int(len(q)), "epa": r3(q.epa.mean()), "succ": r3(q.success.mean())}
             for d, q in db.groupby("down") if d in (1, 2, 3)]
    comp = att[att.complete_pass == 1]
    return {"kind": "qb", "name": db.name.mode().iat[0], "team": db.posteam.mode().iat[0], "games": int(db.game_id.nunique()),
            "dropbacks": int(len(db)), "epa": r3(db.epa.mean()), "succ": r3(db.success.mean()),
            "att": int(len(att)), "comp": r3(att.complete_pass.mean()), "cpoe": r3(att.cpoe.mean()), "adot": r1(att.air_yards.mean()),
            "yds": int(comp.passing_yards.sum()), "td": int((att.touchdown == 1).sum()), "int": int((att.interception == 1).sum()),
            "sacks": int((db.sack == 1).sum()), "scrambles": int((db.qb_scramble == 1).sum()),
            "yac_share": r3(comp.yards_after_catch.sum() / comp.passing_yards.sum()) if comp.passing_yards.sum() else None,
            "bands": bands, "downs": downs, "weeks": weekly(db.groupby("week").epa.mean(), weeks)}


def rb_profile(pid, r, weeks):
    q = r[r.rusher_player_id == pid]
    downs = [{"down": int(d), "n": int(len(g)), "succ": r3(g.success.mean()), "epa": r3(g.epa.mean())}
             for d, g in q.groupby("down") if d in (1, 2, 3)]
    return {"kind": "rb", "name": q.rusher_player_name.mode().iat[0], "team": q.posteam.mode().iat[0],
            "games": int(q.game_id.nunique()), "carries": int(len(q)), "yds": int(q.yards_gained.sum()),
            "ypc": r1(q.yards_gained.mean()), "succ": r3(q.success.mean()), "epa": r3(q.epa.mean()),
            "explosive": r3((q.yards_gained >= 10).mean()), "stuffed": r3((q.yards_gained <= 0).mean()),
            "td": int((q.touchdown == 1).sum()), "fumbles": int((q.fumble_lost == 1).sum()), "downs": downs,
            "weeks": weekly(q.groupby("week").success.mean(), weeks)}


def rec_profile(pid, p, weeks, share_row=None):
    tg = p[(p.receiver_player_id == pid) & (p.pass_attempt == 1) & (p.sack != 1) & (p.two_point_attempt != 1)].copy()
    tg["band"] = depth_band(tg.air_yards.fillna(0))
    c = tg[(tg.complete_pass == 1) & tg.yards_after_catch.notna() & tg.xyac_mean_yardage.notna()]
    bands = []
    for b in ["Behind LOS", "0-9 yds", "10-19 yds", "20+ yds"]:
        q = tg[tg.band == b]
        if len(q):
            bands.append({"band": b, "tgt": int(len(q)), "catch": r3(q.complete_pass.mean()), "epa": r3(q.epa.mean())})
    out = {"kind": "rec", "name": tg.receiver_player_name.mode().iat[0], "team": tg.posteam.mode().iat[0],
           "games": int(tg.game_id.nunique()), "tgt": int(len(tg)), "rec": int(tg.complete_pass.sum()),
           "catch": r3(tg.complete_pass.mean()), "yds": int(tg.receiving_yards.fillna(0).sum()),
           "td": int((tg.touchdown == 1).sum()), "adot": r1(tg.air_yards.mean()), "epa": r3(tg.epa.mean()),
           "yac": r1(c.yards_after_catch.mean()), "yacoe": float(np.round((c.yards_after_catch - c.xyac_mean_yardage).mean(), 2)) if len(c) else None,
           "bands": bands, "weeks": weekly(tg.groupby("week").size(), weeks)}
    if share_row is not None:
        out |= {"tgt_share": r3(share_row.tgt_share), "air_share": r3(share_row.air_share), "wopr": r3(share_row.wopr)}
    return out


def team_profiles(p, weeks, rec):
    sc = data.scrimmage(p)
    sc = sc[sc.two_point_attempt != 1]
    sc = sc.assign(_run=(sc.play_type == "run") & (sc.qb_scramble != 1), _drop=sc.qb_dropback == 1)
    db = p[(p.qb_dropback == 1) & p.epa.notna() & (p.two_point_attempt != 1)]
    press = ((db.sack == 1) | (db.qb_hit == 1))
    n = data.scrimmage(p)
    n = n[n.down.isin([1, 2]) & n.wp.between(0.2, 0.8) & (n.half_seconds_remaining > 120) & n.pass_oe.notna()]
    out = {}
    for t in sorted(sc.posteam.dropna().unique()):
        o, d = sc[sc.posteam == t], sc[sc.defteam == t]
        wk = (o.groupby("week").epa.mean() - d.groupby("week").epa.mean())
        nn = n[n.posteam == t]
        out[t] = {"kind": "team", "team": t, **rec.get(t, {}),
                  "off": r3(o.epa.mean()), "def": r3(d.epa.mean()), "net": r3(o.epa.mean() - d.epa.mean()),
                  "off_pass": r3(o[o._drop].epa.mean()), "off_run": r3(o[o._run].epa.mean()),
                  "def_pass": r3(d[d._drop].epa.mean()), "def_run": r3(d[d._run].epa.mean()),
                  "off_succ": r3(o.success.mean()), "def_succ": r3(d.success.mean()),
                  "proe": r3(nn.pass_oe.mean() / 100), "proe_plays": int(len(nn)),
                  "press": r3(press[db.defteam == t].mean()), "db_faced": int((db.defteam == t).sum()),
                  "sacks": int(((db.defteam == t) & (db.sack == 1)).sum()),
                  "weeks": weekly(wk, weeks)}
    return out


def rush_events(p):
    d = p[(p.qb_dropback == 1) & (p.two_point_attempt != 1)]
    rows = []
    for r in d.itertuples():
        seen = {}
        if pd.notna(r.sack_player_id):
            seen[r.sack_player_id] = (r.sack_player_name, 1.0)
        for i in (1, 2):
            pid = getattr(r, f"half_sack_{i}_player_id")
            if pd.notna(pid):
                seen[pid] = (getattr(r, f"half_sack_{i}_player_name"), 0.5)
        for i in (1, 2):
            pid = getattr(r, f"qb_hit_{i}_player_id")
            if pd.notna(pid) and pid not in seen:
                seen[pid] = (getattr(r, f"qb_hit_{i}_player_name"), 0.0)
        for pid, (nm, sk) in seen.items():
            rows.append((pid, nm, r.defteam, sk, r.week, r.down, r.epa, r.qtr))
    return pd.DataFrame(rows, columns=["pid", "name", "team", "sacks", "week", "down", "epa", "qtr"])


# ---------------------------------------------------------------- filter cubes
# Every chart can be cut by week range, down and quarter on the page. Each cube holds additive sums per
# (entity, week, down, quarter): counts and sums, never means, so the page re-adds the cells that pass the filter
# and recomputes the same statistic. Down 0 = no down (kicks); quarter 5 = overtime. With every filter at "All"
# the cells add back to the published charts exactly (checked in build()).
KEYS = ["week", "down", "qtr"]


def _keys(df):
    return df.assign(down=df.down.fillna(0).astype(int), qtr=df.qtr.fillna(1).clip(upper=5).astype(int),
                     week=df.week.astype(int))


def _cells(parts: list[tuple[pd.DataFrame, str, dict]]) -> pd.DataFrame:
    """parts: (rows, entity column, {out column: (source column or None for a count, how)}) -> one summed frame."""
    out = None
    for df, ent, cols in parts:
        df = _keys(df).rename(columns={ent: "ent"})
        agg = {}
        for name, src in cols.items():
            agg[name] = ("week", "size") if src is None else (src, "sum")
        g = df.groupby(["ent"] + KEYS).agg(**agg).reset_index()
        out = g if out is None else out.merge(g, on=["ent"] + KEYS, how="outer")
    return out.fillna(0)


def _pack(g: pd.DataFrame, keep=None, digits=6) -> dict:
    if keep is not None:
        g = g[g.ent.isin(keep)]
    cols = [c for c in g.columns if c not in ["ent"] + KEYS]
    ents = sorted(g.ent.unique())
    ix = {e: i for i, e in enumerate(ents)}
    rows = []
    for r in g.itertuples(index=False):
        d = r._asdict()
        vals = [d[c] for c in cols]
        rows.append([ix[d["ent"]], d["week"], d["down"], d["qtr"]] +
                    [int(v) if float(v).is_integer() else round(float(v), digits) for v in vals])
    return {"ents": ents, "cols": cols, "rows": rows}


def cubes(p, r, e, k):
    """The filter cubes for all twelve charts, plus names and teams for every entity in them."""
    names = {}

    def name_of(df, ent, nm, team="posteam"):
        g = df.groupby(ent).agg(n=(nm, lambda s: s.mode().iat[0]), t=(team, lambda s: s.mode().iat[0]))
        return {i: [x.n, x.t] for i, x in g.iterrows()}

    # quarterbacks: dropbacks (chart 1) and attempts (chart 7)
    db = p[(p.qb_dropback == 1) & p.epa.notna() & (p.two_point_attempt != 1)]
    att = p[(p.pass_attempt == 1) & (p.sack != 1) & (p.two_point_attempt != 1)].copy()
    att["cpoe_n"], att["cpoe_s"] = att.cpoe.notna().astype(int), att.cpoe.fillna(0)
    att["air_n"], att["air_s"] = att.air_yards.notna().astype(int), att.air_yards.fillna(0)
    cp = att.complete_pass == 1
    att["cyds"], att["cyac"] = np.where(cp, att.passing_yards.fillna(0), 0), np.where(cp, att.yards_after_catch.fillna(0), 0)
    qb = _cells([(db, "id", {"db": None, "epa": "epa"}),
                 (att, "passer_player_id", {"att": None, "cpoe_n": "cpoe_n", "cpoe_s": "cpoe_s", "air_n": "air_n",
                                            "air_s": "air_s", "cyds": "cyds", "cyac": "cyac"})])
    tot = qb.groupby("ent")[["db", "att"]].sum()
    keep_qb = set(tot[(tot.db >= 30) | (tot.att >= 30)].index)
    names["qb"] = {i: v for i, v in name_of(db, "id", "name").items() if i in keep_qb}

    # running backs (chart 2) and the RB average over every back
    rr = r.assign(succ=r.success.fillna(0))
    rb = _cells([(rr, "rusher_player_id", {"car": None, "succ": "succ", "epa": "epa"})])
    tot = rb.groupby("ent").car.sum()
    keep_rb = set(tot[tot >= 15].index)
    names["rb"] = {i: v for i, v in name_of(r, "rusher_player_id", "rusher_player_name").items() if i in keep_rb}
    rb_all = _cells([(rr.assign(all="ALL"), "all", {"car": None, "succ": "succ"})])

    # teams (charts 3, 4, 6 and 10)
    sc = data.scrimmage(p)
    sc2 = sc[sc.two_point_attempt != 1]
    neu = sc[sc.down.isin([1, 2]) & sc.wp.between(0.2, 0.8) & (sc.half_seconds_remaining > 120) & sc.pass_oe.notna()]
    dbt = db.assign(press=((db.sack == 1) | (db.qb_hit == 1)).astype(int))
    runs, drops = sc2[(sc2.play_type == "run") & (sc2.qb_scramble != 1)], sc2[sc2.qb_dropback == 1]
    tm = _cells([(sc2, "posteam", {"off_n": None, "off_e": "epa"}), (sc2, "defteam", {"def_n": None, "def_e": "epa"}),
                 (neu.assign(oe=neu.pass_oe / 100), "posteam", {"proe_n": None, "proe_s": "oe"}),
                 (dbt, "defteam", {"db_n": None, "press": "press", "db_e": "epa"}),
                 (runs, "defteam", {"run_n": None, "run_e": "epa"}), (drops, "defteam", {"pas_n": None, "pas_e": "epa"})])

    # receivers: shares (chart 5, over the games each player was targeted in), value (8), YAC over expected (9)
    tg = p[(p.pass_attempt == 1) & p.receiver_player_id.notna() & (p.two_point_attempt != 1)].copy()
    tg["air"] = tg.air_yards.fillna(0)
    tg = _keys(tg)
    team_cell = tg.groupby(["posteam", "game_id"] + KEYS).agg(t_tgt=("air", "size"), t_air=("air", "sum")).reset_index()
    games = tg[["receiver_player_id", "posteam", "game_id"]].drop_duplicates()
    sh = games.merge(team_cell, on=["posteam", "game_id"])
    own = tg.groupby(["receiver_player_id", "posteam", "game_id"] + KEYS).agg(w_t=("air", "size"), w_a=("air", "sum")).reset_index()
    sh = sh.merge(own, on=["receiver_player_id", "posteam", "game_id"] + KEYS, how="left").fillna({"w_t": 0, "w_a": 0})
    sh = sh.groupby(["receiver_player_id"] + KEYS).agg(w_t=("w_t", "sum"), w_a=("w_a", "sum"), w_tt=("t_tgt", "sum"),
                                                         w_ta=("t_air", "sum")).reset_index().rename(columns={"receiver_player_id": "ent"})
    t8 = p[(p.pass_attempt == 1) & (p.sack != 1) & p.receiver_player_id.notna() & p.epa.notna() & (p.two_point_attempt != 1)].copy()
    t8["an"], t8["as_"] = t8.air_yards.notna().astype(int), t8.air_yards.fillna(0)
    c9 = p[(p.complete_pass == 1) & p.receiver_player_id.notna() & p.yards_after_catch.notna() & p.xyac_mean_yardage.notna()
           & (p.two_point_attempt != 1)].copy()
    c9["oe"] = c9.yards_after_catch - c9.xyac_mean_yardage
    rc = _cells([(t8, "receiver_player_id", {"v_n": None, "v_e": "epa", "v_an": "an", "v_as": "as_"}),
                 (c9, "receiver_player_id", {"y_n": None, "y_oe": "oe", "y_yac": "yards_after_catch"})])
    rc = sh.merge(rc, on=["ent"] + KEYS, how="outer").fillna(0)
    tot = rc.groupby("ent")[["w_t", "y_n"]].sum()
    keep_rc = set(tot[(tot.w_t >= 15) | (tot.y_n >= 10)].index)
    names["rec"] = {i: v for i, v in name_of(tg, "receiver_player_id", "receiver_player_name").items() if i in keep_rc}

    # pass rushers (chart 11)
    ev = _cells([(e, "pid", {"ev": None, "sk": "sacks"})])
    tot = ev.groupby("ent").ev.sum()
    keep_ev = set(tot[tot >= 3].index)
    names["def"] = {i: v for i, v in name_of(e, "pid", "name", "team").items() if i in keep_ev}

    # kickers (chart 12)
    kk = _cells([(k, "kicker_player_id", {"att": None, "made": "made", "exp": "p"})])
    names["k"] = name_of(k, "kicker_player_id", "kicker_player_name")

    out = {"qb": _pack(qb, keep_qb), "rb": _pack(rb, keep_rb), "rb_all": _pack(rb_all), "team": _pack(tm),
           "rec": _pack(rc, keep_rc), "def": _pack(ev, keep_ev), "k": _pack(kk)}
    return out, names, {"qb": qb, "rb": rb, "rb_all": rb_all, "team": tm, "rec": rc, "def": ev, "k": kk}


def headshots(ids) -> dict:
    """Player headshots for the scatter markers: nflverse's players file points at the NFL's image server, asked for a
    96px face crop. The page links to them (nothing is copied here) and falls back to the team-colour dot."""
    pl = data.load_players()[["gsis_id", "headshot"]].dropna()
    pl = pl[pl.gsis_id.isin(ids) & pl.headshot.str.contains("/f_auto,q_auto/")]
    return {r.gsis_id: r.headshot.replace("/f_auto,q_auto/", "/f_auto,q_auto,w_96,h_96,c_fill,g_face/") for r in pl.itertuples()}


def build() -> dict:
    p, weeks = load()
    f = json.loads(FINDINGS.read_text())
    tc = sn.team_colors()
    colors = {t: [r.team_color, r.team_color2] for t, r in tc.iterrows()}

    def check(label, got, want, tol=0.0015):
        if isinstance(want, str) or isinstance(got, str):
            ok = got == want
        else:
            ok = abs(float(got) - float(want)) <= tol
        if not ok:
            raise SystemExit(f"{label}: page {got} vs findings.json {want}; rebuild the snippets first")

    check("plays", len(p), f["plays"], 0)
    check("first week", min(weeks), f["weeks"][0], 0)
    check("last week", max(weeks), f["weeks"][1], 0)
    QB, RB, REC, DEF, K = {}, {}, {}, {}, {}

    # 1 and 7: quarterbacks
    q = sn.qb_table(p)
    q1 = q[q.dropbacks >= 150]
    check("QBs charted", len(q1), f["qb_epa_cpoe"]["n_qbs"], 0)
    check("corr EPA-CPOE", round(float(q1.epa.corr(q1.cpoe)), 2), f["qb_epa_cpoe"]["corr_epa_cpoe"], 0.001)
    for got, want in zip(q1.sort_values("epa", ascending=False).head(3).itertuples(), f["qb_epa_cpoe"]["top3_epa"]):
        check(f"QB {want['name']}", got.name, want["name"])
        check(f"QB {want['name']} EPA", got.epa, want["epa"])
    q7 = q[q.attempts >= 150]
    check("QBs charted (YAC)", len(q7), f["qb_adot_yac"]["n_qbs"], 0)
    for i in set(q1.id) | set(q7.id):
        QB[i] = qb_profile(i, p, weeks)
    c_qb = [{"id": r.id, "x": r3(r.epa), "y": r3(r.cpoe)} for r in q1.itertuples()]
    c_qb7 = [{"id": r.id, "x": r1(r.adot), "y": r3(r.yac_share)} for r in q7.itertuples()]

    # 2: running backs
    qbs = set(p[(p.qb_dropback == 1)].groupby("id").size().loc[lambda x: x >= 50].index)
    r = p[(p.play_type == "run") & p.rusher_player_id.notna() & p.epa.notna() & (p.two_point_attempt != 1)
          & (p.qb_scramble != 1) & ~p.rusher_player_id.isin(qbs)]
    g = r.groupby("rusher_player_id").agg(carries=("epa", "size"), success=("success", "mean"), epa=("epa", "mean")).reset_index()
    check("RB average", r.success.mean(), f["rb_success"]["rb_average_success"])
    check("RBs qualified", int((g.carries >= 60).sum()), f["rb_success"]["n_qualified"], 0)
    rb = g[g.carries >= 60].sort_values("success", ascending=False).head(30)
    for got, want in zip(rb.itertuples(), f["rb_success"]["top5"]):
        check(f"RB {want['rusher_player_name']} success", got.success, want["success"])
    for i in rb.rusher_player_id:
        RB[i] = rb_profile(i, r, weeks)
    c_rb = [{"id": x.rusher_player_id, "v": r3(x.success), "right": r3(x.epa), "n": int(x.carries)} for x in rb.itertuples()]

    # 3, 4, 6, 10: teams
    T = team_profiles(p, weeks, records(p))
    for want in f["team_tiers"]["top5_net"]:
        check(f"{want['team']} net EPA", T[want["team"]]["net"], want["net"], 0.0016)
    for t, v in f["early_down_proe"]["most_pass_happy"].items():
        check(f"{t} PROE", T[t]["proe"], v)
    c_tiers = [{"team": t, "x": v["off"], "y": v["def"]} for t, v in T.items()]
    proe = sorted(T.values(), key=lambda v: -v["proe"])
    off_rank = {t: i + 1 for i, t in enumerate(sorted(T, key=lambda t: -T[t]["off"]))}
    c_proe = [{"team": v["team"], "v": v["proe"], "right": off_rank[v["team"]]} for v in proe]
    c_press = [{"team": t, "x": v["press"], "y": None} for t, v in T.items()]
    dbx = p[(p.qb_dropback == 1) & p.epa.notna() & (p.two_point_attempt != 1)]
    epa_db = dbx.groupby("defteam").epa.mean()
    for row in c_press:
        row["y"] = r3(epa_db[row["team"]])
        T[row["team"]]["epa_db_allowed"] = row["y"]
    xs, ys = np.array([c["x"] for c in c_press], float), np.array([c["y"] for c in c_press], float)
    check("corr pressure-EPA", round(float(np.corrcoef(xs, ys)[0, 1]), 2), f["defense_pressure"]["corr_press_epa"], 0.011)
    fit = np.polyfit(xs, ys, 1)
    for row in c_press:
        T[row["team"]]["vs_fit"] = r3(row["y"] - np.polyval(fit, row["x"]))
    c_drp = [{"team": t, "x": v["def_run"], "y": v["def_pass"]} for t, v in T.items()]
    best_run = sorted(T, key=lambda t: T[t]["def_run"])[:3]
    check("best run defense", ",".join(best_run), ",".join(f["defense_run_pass"]["best_run_d"]))

    # 5: receiver roles (WOPR, top 40 with 40+ targets)
    tg = p[(p.pass_attempt == 1) & p.receiver_player_id.notna() & (p.two_point_attempt != 1)].copy()
    tg["air"] = tg.air_yards.fillna(0)
    tgame = tg.groupby(["posteam", "game_id"]).agg(t_tgt=("pass_attempt", "size"), t_air=("air", "sum")).reset_index()
    pgame = tg.groupby(["receiver_player_id", "posteam", "game_id"]).agg(tgt=("pass_attempt", "size"), air=("air", "sum")).reset_index()
    pgame = pgame.merge(tgame, on=["posteam", "game_id"])
    w = pgame.groupby("receiver_player_id").agg(tgt=("tgt", "sum"), air=("air", "sum"), t_tgt=("t_tgt", "sum"), t_air=("t_air", "sum")).reset_index()
    w["tgt_share"], w["air_share"] = w.tgt / w.t_tgt, w.air / w.t_air
    w["wopr"] = 1.5 * w.tgt_share + 0.7 * w.air_share
    w5 = w[w.tgt >= 40].sort_values("wopr", ascending=False).head(40)
    for got, want in zip(w5.itertuples(), f["receiver_share"]["top5_wopr"]):
        check(f"WOPR {want['receiver_player_name']}", got.wopr, want["wopr"])
    shares = w.set_index("receiver_player_id")
    c_wopr = [{"id": x.receiver_player_id, "x": r3(x.tgt_share), "y": r3(x.air_share)} for x in w5.itertuples()]

    # 8: receivers, role vs value (45 most targeted, 40+ targets)
    t8 = p[(p.pass_attempt == 1) & (p.sack != 1) & p.receiver_player_id.notna() & p.epa.notna() & (p.two_point_attempt != 1)]
    g8 = t8.groupby("receiver_player_id").agg(tgt=("epa", "size"), epa=("epa", "mean"), adot=("air_yards", "mean")).reset_index()
    g8 = g8[g8.tgt >= 40].sort_values("tgt", ascending=False)
    tie8 = list(g8.receiver_player_id)  # the page breaks ties in target count in this same order
    g8 = g8.head(45)
    check("receivers charted", len(g8), f["receiver_epa_adot"]["n"], 0)
    check("top EPA/target", g8.epa.max(), f["receiver_epa_adot"]["top5_epa_per_target"][0]["epa"])
    c_rec8 = [{"id": x.receiver_player_id, "x": r1(x.adot), "y": r3(x.epa)} for x in g8.itertuples()]

    # 9: YAC over expected (top 30, 25+ catches)
    c9 = p[(p.complete_pass == 1) & p.receiver_player_id.notna() & p.yards_after_catch.notna() & p.xyac_mean_yardage.notna()
           & (p.two_point_attempt != 1)].copy()
    c9["yacoe"] = c9.yards_after_catch - c9.xyac_mean_yardage
    g9 = c9.groupby("receiver_player_id").agg(rec=("yacoe", "size"), yacoe=("yacoe", "mean"), yac=("yards_after_catch", "mean")).reset_index()
    check("YACOE qualified", int((g9.rec >= 25).sum()), f["yac_over_expected"]["n_qualified"], 0)
    g9 = g9[g9.rec >= 25].sort_values("yacoe", ascending=False).head(30)
    for got, want in zip(g9.itertuples(), f["yac_over_expected"]["top5"]):
        check(f"YACOE {want['receiver_player_name']}", got.yacoe, want["yacoe"], 0.006)
    c_yac = [{"id": x.receiver_player_id, "v": float(np.round(x.yacoe, 2)), "right": r1(x.yac), "n": int(x.rec)} for x in g9.itertuples()]
    for i in set(w5.receiver_player_id) | set(g8.receiver_player_id) | set(g9.receiver_player_id):
        REC[i] = rec_profile(i, p, weeks, shares.loc[i] if i in shares.index else None)

    # 11: pass rush (top 30 by plays with a sack or QB hit)
    e = rush_events(p)
    g11 = e.groupby("pid").agg(name=("name", "first"), team=("team", lambda s: s.mode().iat[0]), events=("sacks", "size"),
                               sacks=("sacks", "sum")).reset_index().sort_values(["events", "sacks"], ascending=False).head(30)
    for got, want in zip(g11.itertuples(), f["pass_rush_leaders"]["top5"]):
        check(f"rusher {want['name']}", got.events, want["events"], 0)
    for x in g11.itertuples():
        q11 = e[e.pid == x.pid]
        DEF[x.pid] = {"kind": "def", "name": x.name, "team": x.team, "events": int(x.events), "sacks": float(x.sacks),
                      "hits_only": int((q11.sacks == 0).sum()), "games_with": int(q11.week.nunique()),
                      "third_down": int((q11.down == 3).sum()), "epa_on": r3(q11.epa.mean()),
                      "weeks": [int((q11.week == wk).sum()) for wk in weeks]}
    c_rush = [{"id": x.pid, "v": int(x.events), "right": float(x.sacks)} for x in g11.itertuples()]

    # 12: kickers (FG points over expected, model on 2022-25)
    m, n_hist = sn.fg_model()
    check("FG model kicks", n_hist, f["kicker_fgoe"]["model_kicks"], 0)
    k = p[(p.field_goal_attempt == 1) & p.kick_distance.notna()].copy()
    k["p"] = m.predict_proba(np.c_[k.kick_distance, k.kick_distance ** 2, k.roof.isin(["dome", "closed"])])[:, 1]
    k["made"] = (k.field_goal_result == "made").astype(int)
    g12 = k.groupby("kicker_player_id").agg(att=("made", "size"), made=("made", "sum"), exp=("p", "sum")).reset_index()
    g12["fgoe"] = 3 * (g12.made - g12.exp)
    g12 = g12[g12.att >= 8].sort_values("fgoe", ascending=False)
    check("kickers charted", len(g12), f["kicker_fgoe"]["n"], 0)
    for got, want in zip(g12.itertuples(), f["kicker_fgoe"]["top3"]):
        check(f"kicker {want['kicker_player_name']}", got.fgoe, want["fgoe_pts"], 0.006)
    for x in g12.itertuples():
        q12 = k[k.kicker_player_id == x.kicker_player_id]
        bands = []
        for lo, hi, lab in ((0, 40, "Under 40"), (40, 50, "40-49"), (50, 99, "50+")):
            b = q12[(q12.kick_distance >= lo) & (q12.kick_distance < hi)]
            if len(b):
                bands.append({"band": lab, "made": int(b.made.sum()), "att": int(len(b)), "exp": r1(b.p.sum())})
        K[x.kicker_player_id] = {"kind": "k", "name": q12.kicker_player_name.mode().iat[0], "team": q12.posteam.mode().iat[0],
                                 "made": int(x.made), "att": int(x.att), "exp": r1(x.exp), "fgoe": r1(x.fgoe),
                                 "long": int(q12[q12.made == 1].kick_distance.max()) if q12.made.any() else None,
                                 "miss": [int(d) for d in q12[q12.made == 0].kick_distance], "bands": bands}
    c_k = [{"id": x.kicker_player_id, "v": round(float(x.fgoe), 1), "right": f"{int(x.made)}-{int(x.att)}"} for x in g12.itertuples()]

    # filter cubes: with every filter at "All" they must add back to the charts above
    k["made"] = k["made"].astype(int)
    CU, NAMES, raw = cubes(p, r, e, k)
    S = {kk: v.groupby("ent").sum(numeric_only=True) for kk, v in raw.items()}
    for row in c_qb:
        q_ = S["qb"].loc[row["id"]]
        check("cube QB EPA", q_.epa / q_.db, row["x"], 6e-4); check("cube QB CPOE", q_.cpoe_s / q_.cpoe_n, row["y"], 6e-4)
    for row in c_qb7:
        q_ = S["qb"].loc[row["id"]]
        check("cube aDOT", q_.air_s / q_.air_n, row["x"], 0.06); check("cube YAC share", q_.cyac / q_.cyds, row["y"], 6e-4)
    for row in c_rb:
        q_ = S["rb"].loc[row["id"]]
        check("cube RB success", q_.succ / q_.car, row["v"], 6e-4); check("cube RB carries", q_.car, row["n"], 0)
    check("cube RB avg", S["rb_all"].succ.sum() / S["rb_all"].car.sum(), r.success.mean(), 1e-9)
    st = S["team"]
    for row in c_tiers:
        check("cube off", st.loc[row["team"]].off_e / st.loc[row["team"]].off_n, row["x"], 6e-4)
        check("cube def", st.loc[row["team"]].def_e / st.loc[row["team"]].def_n, row["y"], 6e-4)
    off_full = (st.off_e / st.off_n).sort_values(ascending=False)  # rank on unrounded EPA, as the static chart does
    for row in c_proe:
        row["right"] = int((off_full > off_full[row["team"]]).sum() + 1)
    for row in c_proe:
        check("cube PROE", st.loc[row["team"]].proe_s / st.loc[row["team"]].proe_n, row["v"], 6e-4)
    for row in c_press:
        check("cube press", st.loc[row["team"]].press / st.loc[row["team"]].db_n, row["x"], 6e-4)
        check("cube EPA/db", st.loc[row["team"]].db_e / st.loc[row["team"]].db_n, row["y"], 6e-4)
    for row in c_drp:
        check("cube run D", st.loc[row["team"]].run_e / st.loc[row["team"]].run_n, row["x"], 6e-4)
        check("cube pass D", st.loc[row["team"]].pas_e / st.loc[row["team"]].pas_n, row["y"], 6e-4)
    sr = S["rec"]
    for row in c_wopr:
        check("cube tgt share", sr.loc[row["id"]].w_t / sr.loc[row["id"]].w_tt, row["x"], 6e-4)
        check("cube air share", sr.loc[row["id"]].w_a / sr.loc[row["id"]].w_ta, row["y"], 6e-4)
    for row in c_rec8:
        check("cube EPA/tgt", sr.loc[row["id"]].v_e / sr.loc[row["id"]].v_n, row["y"], 6e-4)
        check("cube rec aDOT", sr.loc[row["id"]].v_as / sr.loc[row["id"]].v_an, row["x"], 0.06)
    for row in c_yac:
        check("cube YACOE", sr.loc[row["id"]].y_oe / sr.loc[row["id"]].y_n, row["v"], 0.006)
    for row in c_rush:
        check("cube events", S["def"].loc[row["id"]].ev, row["v"], 0); check("cube sacks", S["def"].loc[row["id"]].sk, row["right"], 1e-9)
    for row in c_k:
        q_ = S["k"].loc[row["id"]]
        check("cube FGOE", 3 * (q_.made - q_.exp), row["v"], 0.06)

    return {"meta": {"season": f["season"], "weeks": f["weeks"], "plays": f["plays"], "built": f["built"]},
            "cubes": CU, "names": NAMES, "tie8": tie8, "heads": headshots(set(NAMES["qb"]) | set(NAMES["rec"])),
            "findings": f,  # the page header (TL;DR, key numbers) quotes findings.json directly
            "colors": colors, "qb": QB, "rb": RB, "rec": REC, "def": DEF, "k": K, "teams": T,
            "league": {"rb_succ": r3(r.success.mean()), "yacoe": f["yac_over_expected"]["league_mean"]},
            "charts": {"qb": c_qb, "rb": c_rb, "tiers": c_tiers, "proe": c_proe, "wopr": c_wopr, "press": c_press,
                       "qb7": c_qb7, "rec8": c_rec8, "yac": c_yac, "drp": c_drp, "rush": c_rush, "k": c_k}}


def write(d: dict, out: Path = PAGE) -> Path:
    blob = json.dumps(d, separators=(",", ":"), ensure_ascii=False, default=float).replace("</", "<\\/")
    out.write_text(TEMPLATE.read_text().replace("/*DATA*/null", blob))
    return out


def main():
    d = build()
    print(write(d), f"{len(d['qb'])} QBs, {len(d['rb'])} RBs, {len(d['rec'])} receivers, {len(d['def'])} rushers, {len(d['k'])} kickers")


if __name__ == "__main__":
    main()
