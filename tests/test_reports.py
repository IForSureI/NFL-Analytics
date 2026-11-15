"""Consistency checks on the saved findings: shapes, counts and intervals that must hold whatever the result is.

These do not assert a conclusion. A study is free to find the opposite of what it found last week and still pass.
The logic itself is tested on made-up data in test_logic.py."""
import json
from pathlib import Path

import pytest

R = Path(__file__).resolve().parents[1] / "reports"


def load(slug):
    p = R / slug / "findings.json"
    if not p.exists():
        pytest.skip(f"{slug} not built")
    return json.loads(p.read_text())


def _interval_ok(v):
    """[point, low, high] with low <= point <= high."""
    return len(v) == 3 and v[1] <= v[0] <= v[2]


def test_fourth_down_findings_are_consistent():
    f = load("02-fourth-down-bot")
    assert 0 < f["brier_ours"] < 0.25 and 0 < f["brier_nflfastR_vegas_wp"] < 0.25      # a Brier score for a coin flip is 0.25
    assert f["wp_test_plays"] > 0 and f["n_boot"] >= 20
    assert 30 <= f["fg_max_dist"] <= 70
    assert 0 <= f["fg_attempts_beyond_range"] <= f["fg_attempts_total"]
    for row in f["most_costly"] + f["least_costly"]:
        team, val, lo, hi = row
        assert lo <= val <= hi, team
    assert -1 <= f["scorecard_split_half_r"] <= 1
    for season, (lo, hi) in f["go_rate_ci"].items():
        assert 0 <= lo <= f["go_rate_clear_spots"][season] <= hi <= 1, season


def test_fourth_down_holdout_findings_are_consistent():
    f = load("02-fourth-down-bot")
    h = f["holdout"]
    assert int(h["train"][-4:]) < int(h["test"][:4])                       # the test seasons come after the training seasons
    for key in ("convert", "convert_4th", "fg", "fg_in_range"):
        c = h[key]
        assert c["n"] > 0 and 0 <= c["actual"] <= 1 and 0 <= c["predicted"] <= 1
        for metric in ("brier", "log_loss"):
            assert all(v[1] <= v[0] <= v[2] for v in c[metric].values()), (key, metric)
        assert 0 < c["brier"]["model"][0] < 1 and c["brier"]["league_avg"][0] <= 0.26   # a constant rate cannot score worse than about 0.25
    assert h["convert_4th"]["n"] < h["convert"]["n"] and h["fg_in_range"]["n"] <= h["fg"]["n"]
    assert all(v[1] <= v[0] <= v[2] for v in h["punt"]["rmse"].values()) and h["punt"]["bias"][1] <= h["punt"]["bias"][0] <= h["punt"]["bias"][2]
    fl = h["flips"]
    for k in ("components", "components_and_wp"):
        assert 0 <= fl[k][1] <= fl[k][0] <= fl[k][2] <= 1
    assert fl["n_flips"] == fl["flips_go_vs_kick"] + fl["flips_fg_vs_punt"]
    assert fl["components"][0] == pytest.approx(fl["n_flips"] / fl["n"], abs=1e-4)
    assert sum(n for _, n in fl["by_season"].values()) == fl["n"]
    assert fl["counted_calls_flipped"] <= min(fl["counted_calls"], fl["n_flips"]) and fl["flips_margin_2plus"] <= fl["flips_margin_1plus"] <= fl["n_flips"]
    hl = h["headline"]
    assert hl["moves"] == bool(hl["reasons"]) and -1 <= hl["card_r"] <= 1
    assert set(hl["go_rate"]) == set(fl["by_season"])                       # every test season is compared
    pf = f["punt_fix"]
    assert (pf["go_to_punt"] + pf["punt_to_go"] + pf["other"]) / pf["n"] == pytest.approx(pf["share_recs_changed"], abs=5e-5)   # the share is stored to 4 places
    assert set(pf["go_rate_before"]) == set(f["go_rate_clear_spots"])       # every season has its before-the-fix rate
    assert all(0 <= r <= 1 and n > 0 for r, n in pf["go_rate_before"].values())
    assert -1 <= pf["split_half_r_before"] <= 1 and -1 <= pf["yoy_r_before"] <= 1 and len(pf["most_costly_before"]) == 3


def test_fourth_down_page_says_what_the_holdout_rule_found():
    f = load("02-fourth-down-bot")
    page = (R / "02-fourth-down-bot" / "README.md").read_text()
    moves = f["holdout"]["headline"]["moves"]                               # the wording follows the rule, whichever way it falls
    assert ("and the headline numbers hold" in page) == (not moves) and ("the headline numbers move:" in page) == moves
    assert f["holdout"]["train"] in page and f["holdout"]["test"] in page  # training and test seasons are named
    assert "They are not tested out of sample" not in page
    ys = sorted(f["go_rate_clear_spots"])
    if any(round(f["punt_fix"]["go_rate_before"][y][0], 2) != round(f["go_rate_clear_spots"][y], 2) for y in (ys[0], ys[-2])):
        assert "before the fix" in page.split("## Key numbers")[0]          # a headline number that moved is flagged in the TL;DR


def test_sack_leverage_findings_are_consistent():
    f = load("03-sack-leverage")
    assert all(0 <= v <= 100 for v in f["third_down_conversion_by_distance"].values())   # percentages
    assert _interval_ok(f["third_minus_second_avg"])
    assert all(_interval_ok(v) for v in f["third_minus_second_same_distance"].values())
    assert isinstance(f["epa_per_sack_repeats"], bool)


def test_luck_findings_are_consistent():
    f = load("04-luck-index")
    for k in ["lucky_minus_matched_wins", "unlucky_minus_matched_wins", "next_wins_per_pythag_win", "next_wins_per_luck_win", "r_pythag_minus_r_wins"]:
        assert _interval_ok(f[k]), k
    assert f["lucky_teams_n"] + f["unlucky_teams_n"] < f["team_season_pairs"]
    assert f["r_pythag_minus_r_wins"][0] == pytest.approx(f["r_next_winpct_from_pythag"] - f["r_next_winpct_from_winpct"], abs=0.002)


def test_kickoff_findings_are_consistent():
    import csv
    f = load("05-kickoff-value")
    d = R / "05-kickoff-value"
    ret = list(csv.DictReader(open(d / "returners_2025_on.csv")))
    kick = list(csv.DictReader(open(d / "kickers_2025_on.csv")))
    assert ret and kick
    assert len({r[next(iter(r))] for r in ret}) == len(ret)          # one row per returner
    assert (d / "return_value_by_landing_spot.csv").exists()
    text = json.dumps(f)
    assert "NaN" not in text


def test_pass_run_findings_are_consistent():
    f = load("06-pass-run")
    assert f["seasons_total"] == len(f["epa_gap_by_season"]) == len(f["epa_gap_ci_by_season"])
    assert 0 <= f["seasons_pass_better"] <= f["seasons_total"]
    assert all(_interval_ok(v) for v in f["epa_gap_ci_by_season"].values())
    assert _interval_ok(f["team_corr_pooled"]) and _interval_ok(f["within_team_change_corr"])
    assert f["team_corr_seasons_positive"] <= f["team_corr_seasons"]


def test_box_score_tax_findings_are_consistent():
    f = load("07-box-score-tax")
    assert 0.1 < f["league_sacks_per_pressure"] < 0.5                 # a rate, checked as a rate
    lo, hi = f["musd_per_lucky_sack_ci"]
    assert lo <= f["musd_per_lucky_sack_2026"] <= hi
    for k in ["tax_ratio_ci90", "tax_ratio_ci95"]:
        assert f[k][0] <= f["tax_ratio"] <= f[k][1]
    assert f["tax_ratio_ci95"][0] <= f["tax_ratio_ci90"][0] and f["tax_ratio_ci90"][1] <= f["tax_ratio_ci95"][1]
    assert 0 <= f["tax_ratio_share_above_1"] <= 1


def test_contract_tables_hold_one_deal_per_player_year():
    import csv
    for slug, name in [("07-box-score-tax", "rusher_contracts_with_platform.csv"), ("09-run-game-value", "rb_contracts_with_platform.csv")]:
        p = R / slug / name
        if not p.exists():
            pytest.skip(f"{slug} not built")
        rows = list(csv.DictReader(open(p)))
        keys = [(r["player"], r["year_signed"]) for r in rows]
        assert len(keys) == len(set(keys)), slug


def test_yac_tax_findings_are_consistent():
    f = load("08-yac-tax")
    for k in ["tax_ratio_ci90", "tax_ratio_ci95"]:
        assert f[k][0] <= f["tax_ratio"] <= f[k][1]
    assert all(-1 <= v <= 1 for v in f["yoy_r"].values())


def test_run_game_value_findings_are_consistent():
    f = load("09-run-game-value")
    assert all(-1 <= v <= 1 for v in f["yoy_r"].values())
    assert abs(f["share_of_repeatable_ypc_expected"] + f["share_of_repeatable_ypc_ryoe"] - 1) < 0.01  # the two parts add to YPC
    assert 3.0 < f["league_ypc"] < 5.5
    lo, hi = f["price_per_carry_diff_ci"]
    assert lo <= f["price_per_carry_diff_musd"] <= hi
    assert f["price_per_carry_min_detectable_musd"] > 0 and f["predict_next_ypc_min_detectable"] > 0


def test_run_game_value_free_agents_checked():
    import csv
    f = load("09-run-game-value")
    rows = list(csv.DictReader(open(R / "09-run-game-value" / f"free_agents_{f['fa_class']}_rbs.csv")))
    names = {r["player"] for r in rows}
    assert "Christian McCaffrey" not in names                            # under contract through 2027 (news check)
    rows2 = list(csv.DictReader(open(R / "09-run-game-value" / f"free_agents_{f['fa_class']}_rbs_no_ngs.csv")))
    assert all(r["news_note"] for r in rows + rows2)                      # every listed name carries a news note
    assert len(rows) == f["fa_n"]


def test_contract_end_year():
    from nflan.data import contract_end_year
    h = [{"contract_type": "Drafted", "year_signed": 2021, "yrs": 4},
         {"contract_type": "Extension", "year_signed": 2024, "yrs": 3},
         {"contract_type": "Extension", "year_signed": 2024, "yrs": 3}]  # duplicate listing
    assert contract_end_year(h) == 2027
    assert contract_end_year([{"contract_type": "UFA", "year_signed": 2026, "yrs": 1}]) == 2026


def test_flag_audit_findings_are_consistent():
    f = load("01-flag-audit")
    assert -1 <= f["crew_yoy_r"] <= 1 and f["crew_yoy_r_ci"][0] <= f["crew_yoy_r"] <= f["crew_yoy_r_ci"][1]
    assert 0 <= f["false_start_road_share"] <= 1
    assert _interval_ok(f["road_subj_drop_per_100_snaps_ci"]) and _interval_ok(f["road_subj_drop_per_100_close_snaps_ci"])
    assert set(f["rtp_above_league_after_correction"]) <= set(f["rtp_above_league"])   # a stricter test never adds names
    assert f["flags"] > 0 and f["games"] > 0


def test_in_season_snippets_sane():
    f = load("2026-in-season-snippets")
    assert f["weeks"][0] == 1 and f["weeks"][1] >= 1
    for name in ["qb_epa_cpoe", "rb_success", "team_tiers", "early_down_proe", "receiver_share", "defense_pressure", "qb_adot_yac", "receiver_epa_adot",
                 "yac_over_expected", "defense_run_pass", "pass_rush_leaders", "kicker_fgoe"]:
        assert (R / "2026-in-season-snippets" / f"{name}.png").exists(), name
    assert -1.0 < f["qb_epa_cpoe"]["top3_epa"][0]["epa"] < 1.0        # EPA per dropback is a per-play number
    for k in ["qb_epa_cpoe", "early_down_proe", "defense_pressure", "qb_adot_yac", "receiver_epa_adot", "defense_run_pass"]:
        lo, hi = f[k]["corr_ci"]
        assert -1 <= lo <= hi <= 1, k
    assert all(0 < r["tgt_share"] < 0.5 for r in f["receiver_share"]["top5_wopr"])


def test_snippets_kicker_model_sane():
    f = load("2026-in-season-snippets")
    k = f["kicker_fgoe"]
    assert k["model_kicks"] > 2000
    assert all(abs(r["fgoe_pts"]) <= 3 * r["att"] for r in k["top3"] + k["bottom3"])   # cannot gain or lose more than 3 points a kick
    assert 0 <= k["outside_chance_band"] <= k["n"]
