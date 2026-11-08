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
