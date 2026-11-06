"""Checks on the saved findings: the published numbers stay inside football-sane ranges."""
import json
from pathlib import Path

import pytest

R = Path(__file__).resolve().parents[1] / "reports"


def load(slug):
    p = R / slug / "findings.json"
    if not p.exists():
        pytest.skip(f"{slug} not built")
    return json.loads(p.read_text())


def test_wp_model_close_to_nflfastR():
    f = load("02-fourth-down-bot")
    assert f["brier_ours"] < 0.16
    assert abs(f["brier_ours"] - f["brier_nflfastR_vegas_wp"]) < 0.005
    assert f["corr_with_nflfastR"] > 0.98


def test_fourth_down_sanity():
    f = load("02-fourth-down-bot")
    assert f["sanity_4th1_midfield_go_boost"] > 0      # 4th-and-1 at midfield, early, tied: go
    assert f["sanity_4th10_own20_go_boost"] < -5       # 4th-and-10 at your own 20: kick


def test_third_down_conversion_monotone():
    f = load("03-sack-leverage")
    c = f["third_down_conversion_by_distance"]
    assert c["1-2"] > c["3-6"] > c["7-10"] > c["11+"]


def test_luck_does_not_repeat():
    f = load("04-luck-index")
    for k in ["yoy_r_fumble_luck", "yoy_r_one_score_luck", "yoy_r_wins_over_pythag"]:
        assert abs(f[k]) < 0.2


def test_pass_beats_run_every_season():
    f = load("06-pass-run")
    assert f["seasons_pass_better"] == f["seasons_total"]


def test_box_score_tax_direction():
    f = load("07-box-score-tax")
    assert f["yoy_r_pressure_rate"] > f["yoy_r_sack_rate"]           # pressures are the stabler skill
    assert abs(f["yoy_r_sack_luck"]) < 0.2                           # sack luck does not repeat
    assert f["musd_per_lucky_sack_ci"][0] > 0                        # ...but the market pays for it
    assert 0.2 < f["league_sacks_per_pressure"] < 0.35
