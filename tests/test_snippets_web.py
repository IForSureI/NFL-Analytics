"""Interactive in-season snippets (docs/snippets.html): the page's numbers match the published charts'
findings.json, every charted point has a breakdown, and the page is one self-contained file."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "snippets.html"
F = ROOT / "reports" / "2026-in-season-snippets" / "findings.json"


@pytest.fixture(scope="module")
def page():
    if not PAGE.exists() or not F.exists():
        pytest.skip("interactive snippets page not built")
    html = PAGE.read_text()
    blob = re.search(r"const DATA = (\{.*?\});\n", html, re.S).group(1)
    return html, json.loads(blob), json.loads(F.read_text())


def test_same_weeks_and_plays(page):
    _, d, f = page
    assert d["meta"]["weeks"] == f["weeks"] and d["meta"]["plays"] == f["plays"]


def test_leaders_match_findings(page):
    _, d, f = page
    c = d["charts"]
    qbs = sorted(c["qb"], key=lambda r: -r["x"])
    assert [r["x"] for r in qbs[:3]] == [r["epa"] for r in f["qb_epa_cpoe"]["top3_epa"]]  # names can tie at 3 decimals
    names = {d["qb"][r["id"]]["name"] for r in c["qb"]}
    assert {r["name"] for r in f["qb_epa_cpoe"]["top3_epa"]} <= names
    assert len(c["qb"]) == f["qb_epa_cpoe"]["n_qbs"] and len(c["qb7"]) == f["qb_adot_yac"]["n_qbs"]
    assert [d["rb"][r["id"]]["name"] for r in c["rb"][:5]] == [r["rusher_player_name"] for r in f["rb_success"]["top5"]]
    assert [d["rec"][r["id"]]["name"] for r in c["yac"][:5]] == [r["receiver_player_name"] for r in f["yac_over_expected"]["top5"]]
    assert [r["v"] for r in c["yac"][:5]] == [r["yacoe"] for r in f["yac_over_expected"]["top5"]]
    assert [d["def"][r["id"]]["name"] for r in c["rush"][:5]] == [r["name"] for r in f["pass_rush_leaders"]["top5"]]
    assert [d["k"][r["id"]]["name"] for r in c["k"][:3]] == [r["kicker_player_name"] for r in f["kicker_fgoe"]["top3"]]
    assert len(c["rec8"]) == f["receiver_epa_adot"]["n"] and len(c["k"]) == f["kicker_fgoe"]["n"]
    assert [r["team"] for r in c["proe"][:3]] == list(f["early_down_proe"]["most_pass_happy"])


def test_teams_match_findings(page):
    _, d, f = page
    for t in f["team_tiers"]["top5_net"]:
        assert abs(d["teams"][t["team"]]["net"] - t["net"]) < 0.002
    assert len(d["teams"]) == 32 and all(v["w"] + v["l"] + v["t"] > 0 for v in d["teams"].values())


def test_every_point_has_a_breakdown(page):
    _, d, _ = page
    c = d["charts"]
    for key, who in (("qb", "qb"), ("qb7", "qb"), ("rb", "rb"), ("wopr", "rec"), ("rec8", "rec"), ("yac", "rec"),
                     ("rush", "def"), ("k", "k")):
        assert c[key] and all(r["id"] in d[who] for r in c[key]), key
    for key in ("tiers", "proe", "press", "drp"):
        assert all(r["team"] in d["teams"] for r in c[key]), key
    for k in d["k"].values():
        assert sum(b["att"] for b in k["bands"]) == k["att"] and sum(b["made"] for b in k["bands"]) == k["made"]


def test_page_is_self_contained(page):
    html, _, _ = page
    assert not re.search(r"<script[^>]+src=|@import|url\(http", html)  # no outside code or styles
    links = re.findall(r'<link[^>]+href="([^"]+)"', html)
    assert all(h.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com")) for h in links)  # fonts only


def _sum_cube(c):
    out = {}
    for r in c["rows"]:
        a = out.setdefault(c["ents"][r[0]], [0.0] * len(c["cols"]))
        for i, v in enumerate(r[4:]):
            a[i] += v
    return {e: dict(zip(c["cols"], v)) for e, v in out.items()}


def test_filters_add_back_to_the_charts(page):
    """Every chart can be cut by week, down and quarter; with no filter the cube cells add back to the chart."""
    _, d, _ = page
    cu, c = d["cubes"], d["charts"]
    for row in d["cubes"]["qb"]["rows"] + d["cubes"]["team"]["rows"]:
        assert row[1] in range(d["meta"]["weeks"][0], d["meta"]["weeks"][1] + 1) and 0 <= row[2] <= 4 and 1 <= row[3] <= 5
    qb, tm, rc, rb, k = (_sum_cube(cu[x]) for x in ("qb", "team", "rec", "rb", "k"))
    for r in c["qb"]:
        assert abs(qb[r["id"]]["epa"] / qb[r["id"]]["db"] - r["x"]) < 6e-4
    for r in c["rb"]:
        assert abs(rb[r["id"]]["succ"] / rb[r["id"]]["car"] - r["v"]) < 6e-4
    for r in c["tiers"]:
        assert abs(tm[r["team"]]["off_e"] / tm[r["team"]]["off_n"] - r["x"]) < 6e-4
    for r in c["proe"]:
        assert abs(tm[r["team"]]["proe_s"] / tm[r["team"]]["proe_n"] - r["v"]) < 6e-4
    for r in c["wopr"]:
        assert abs(rc[r["id"]]["w_t"] / rc[r["id"]]["w_tt"] - r["x"]) < 6e-4
    for r in c["k"]:
        assert abs(3 * (k[r["id"]]["made"] - k[r["id"]]["exp"]) - r["v"]) < 0.06
    assert all(i in d["names"]["qb"] for i in cu["qb"]["ents"]) and all(i in d["names"]["rec"] for i in cu["rec"]["ents"])
