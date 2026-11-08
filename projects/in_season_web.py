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
         "interception", "fumble_lost", "rushing_yards", "first_down"]


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
            rows.append((pid, nm, r.defteam, sk, r.week, r.down, r.epa))
    return pd.DataFrame(rows, columns=["pid", "name", "team", "sacks", "week", "down", "epa"])


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
    g8 = g8[g8.tgt >= 40].sort_values("tgt", ascending=False).head(45)
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

    return {"meta": {"season": f["season"], "weeks": f["weeks"], "plays": f["plays"], "built": f["built"]},
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
