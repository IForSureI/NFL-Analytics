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


def test_draft_value_findings_are_consistent():
    f = load("10-draft-value")
    assert f["picks"] + f["specialists_dropped"] + f["unresolved_dropped"] == f["picks_all"]
    assert sum(f["picks_by_pos"].values()) == f["picks"]
    for k in ("curve_av_at", "curve_apy_at", "curve_start_at", "curve_second_at"):   # the curve never rises with the pick
        v = [f[k][p] for p in sorted(f[k], key=int)]
        assert all(a >= b for a, b in zip(v, v[1:])), k
    for p, r in f["r37"].items():
        for val, ci in (("av_surplus", "av_ci"), ("apy_surplus", "apy_ci"), ("start_over", "start_over_ci"), ("second_over", "second_over_ci")):
            assert r[ci][0] <= r[ci][1], (p, val)
        assert r["av_p"] <= r["av_p_holm"] <= 1                                 # a correction never lowers a p-value
        assert r["picks"] == sum(f["grid_n"][p][x] for x in ("R3", "R4", "R5", "R6", "R7"))
    assert set(f["r37_av_holm_clear"]) <= set(f["r37_av_clear"]) and set(f["r37_apy_holm_clear"]) <= set(f["r37_apy_clear"])
    for x in f["inefficiencies"]:                                               # the rule stated before the results
        r = f["r37"][x["pos"]]
        assert r["av_ci"][0] > 0 or r["av_ci"][1] < 0
        assert (r["av_surplus"] > 0) == (r["apy_surplus"] > 0) == (x["direction"] == "drafted too late")
    assert len(f["inefficiencies"]) <= 3 and all(c["bandwidth"] > 0 for c in f["curve_cv"].values())


def test_draft_value_logic_on_made_up_picks():
    import numpy as np
    import pandas as pd
    from projects.draft_value import fit_curve, surplus_table, equivalent_shift, position_group, second_contract, POS_ORDER
    rng = np.random.default_rng(3)
    n = 6000
    pick = rng.integers(1, 257, n)
    pos = rng.choice(POS_ORDER, n)
    base = 60 * np.exp(-pick / 60) + 5                                          # a known falling curve
    y = base + np.where((pos == "IDL") & (pick > 64), 4.0, 0.0) + rng.normal(0, 3, n)   # late IDL planted at +4
    df = pd.DataFrame({"pick": pick, "pos": pos, "y": y, "round": np.minimum((pick - 1) // 32 + 1, 7)})
    cv = fit_curve(df.pick, df.y, 0.18)
    assert np.all(np.diff(cv) <= 1e-9)                                          # never rises
    assert abs(cv[99] - (60 * np.exp(-100 / 60) + 5)) < 1.5                     # and finds the curve that made the data
    t, ex, _ = surplus_table(df, "y", 0.18, n_boot=60)
    r = t[t["round"] == "R3-7"].set_index("pos")
    assert r.loc["IDL", "lo"] > 2.5 and r.loc["IDL", "hi"] < 5.5                # the planted effect, less the curve's share of it
    others = r.drop("IDL")
    assert (others.surplus.abs() < 1.0).all()
    assert equivalent_shift(cv, np.array([100, 150]), float(cv[[99, 149]].mean())) == 0   # no surplus, no shift
    assert equivalent_shift(cv, np.array([150]), float(cv[129])) == 20.0
    assert position_group("DB", "S", None) == "S" and position_group("CB", "S", None) == "CB"   # specific labels win
    assert position_group("OLB", "ED", None) == "EDGE" and position_group("P") == "ST"
    c = pd.DataFrame({"draft_year": [2015, 2015, 2015, 2016], "draft_overall": [100, 100, 100, 5], "year_signed": [2015, 2019, 2022, 2017],
                      "apy_cap_pct": [0.005, 0.02, 0.05, 0.01]})
    sc = second_contract(c)
    assert sc.loc[sc.draft_overall == 100, "apy_cap"].item() == 0.02            # rookie deal and the year-7 deal fall outside 2-5
    assert 5 not in set(sc.draft_overall)                                       # signed one year after the draft: not a second contract


def test_turnovers_forced_findings_are_consistent():
    f = load("11-turnovers-forced")
    for k, v in f["yoy_r"].items():
        assert -1 <= v[1] <= v[0] <= v[2] <= 1, k
    for k, v in f["r_next_pa"].items():
        assert _interval_ok(v), k
    assert f["pairs"] < f["team_seasons"] and f["top5_n"] == 5 * len(range(int(f["seasons"][:4]), int(f["seasons"][-4:])))
    assert _interval_ok(f["top5_excess_retained"]) and _interval_ok(f["top5_pa_change_vs_matched"])
    assert f["top5_takeaways_pg"][0] > f["league_takeaways_pg"] > f["bottom5_takeaways_pg"][0]   # the top five sit above the league by construction
    assert 0.4 < f["league_fum_rec_share_pooled"] < 0.6                                             # a loose ball is close to a coin flip
    assert all(_interval_ok(r["pa_change_vs_matched"]) for r in f["top5_robustness"])
    assert f["oos_n"][0] + f["oos_n"][1] == f["pairs"]
    assert f["flag_rule"]["sell_n"] == len(f["sell"]) and f["flag_rule"]["buy_n"] == len(f["buy"])
    assert all(x["to_pts"] <= -f["flag_rule"]["to_pts_ppg"] for x in f["sell"]) and all(x["to_pts"] >= f["flag_rule"]["to_pts_ppg"] for x in f["buy"])
    assert 1 <= f["through_week"] <= 18 and f["current_games_range"][1] <= f["through_week"]


def test_turnovers_forced_logic_on_made_up_plays():
    import pandas as pd
    from projects.turnovers_forced import aggregate, latest_complete_week, tag_plays, team_points
    base = dict(season=2030, season_type="REG", game_date="2030-09-10", home_team="AAA", away_team="BBB", home_score=20, away_score=10,
                posteam="BBB", defteam="AAA", play_type="pass", epa=0.5, down=1, qb_dropback=1, interception=0, fumble=0, fumble_forced=0,
                fumble_lost=0, fumbled_1_team=None, fumble_recovery_1_team=None, sack=0, qb_hit=0, success=1)
    rows = [dict(base, game_id="g1", week=1),
            dict(base, game_id="g1", week=1, interception=1, epa=-4.0, success=0),                                      # takeaway
            dict(base, game_id="g1", week=1, play_type="run", qb_dropback=0, fumble=1, fumble_forced=1, fumble_lost=1,   # forced, recovered by D
                 fumbled_1_team="BBB", fumble_recovery_1_team="AAA", epa=-3.0, success=0),
            dict(base, game_id="g1", week=1, fumble=1, fumbled_1_team="BBB", fumble_recovery_1_team="BBB", sack=1, qb_hit=1, epa=-1.0, success=0),
            dict(base, game_id="g1", week=1, interception=1, fumble=1, fumble_lost=1, fumbled_1_team="AAA", fumble_recovery_1_team="BBB", epa=-2.0, success=0),  # INT then fumbled back
            dict(base, game_id="g0", week=1, home_team="III", away_team="JJJ", posteam="JJJ", defteam="III"),
            dict(base, game_id="g2", week=2, home_team="CCC", away_team="DDD", posteam="DDD", defteam="CCC"),
            dict(base, game_id="g3", week=2, home_team="EEE", away_team="FFF", posteam="FFF", defteam="EEE"),
            dict(base, game_id="g4", week=3, home_team="GGG", away_team="HHH", posteam="HHH", defteam="GGG")]
    pbp = pd.DataFrame(rows)
    assert latest_complete_week(pbp, 2030) == 2          # week 3 has fewer games than any earlier week: still being played
    s = tag_plays(pbp)
    t = aggregate(s, team_points(pbp)).set_index("team").loc["AAA"]
    assert t.plays == 5 and t.takeaways == 3 and t.ints == 2 and t.fum_lost == 1   # the fumble after an interception is not a second takeaway
    assert t.opp_fum_known == 2 and t.def_rec == 1 and t.ff == 1 and t.fum_rec_share == 0.5
    assert t.press == 1 and t.dropbacks == 4
    assert t.epa_noto == (0.5 - 1.0) / 2 and t.pa_pg == 10


def test_backup_qb_findings_are_consistent():
    f = load("12-backup-qb-value")
    for k in ("epa_db", "pf", "margin", "win"):
        assert _interval_ok(f["effect"][k]), k
    s = f["backup_starts_per_17"]
    assert s[1] <= s[0] <= s[2] and 0 < s[0] < 17
    assert 0 <= f["share_seasons_4plus"] <= f["share_seasons_with_backup_start"] <= 1
    assert sum(f["dist_backup_starts"].values()) == f["team_seasons"]
    assert f["fe_backup_games"] == f["backup_games"] and f["fe_games"] <= f["team_games"]
    assert 0 < f["wins_per_point_margin"][0] < 0.1                                     # a point of margin per game is worth a few hundredths of a win
    lo, hi = f["wins_per_start_via_margin_ci"]
    assert lo <= f["wins_per_start_via_margin"] <= hi
    assert f["wins_per_start_via_margin"] == pytest.approx(f["effect"]["margin"][0] * f["wins_per_point_margin"][0], abs=1e-3)
    u = f["upgrade"]
    assert _interval_ok(u["wins_per_season"]) and _interval_ok(u["value_musd"]) and u["cost_gap_musd"] == f["pricey_musd"] - f["cheap_musd"]
    assert u["value_musd"][0] == pytest.approx(u["wins_per_season"][0] * f["usd_per_win_qb_market"][0], abs=0.02)
    assert _interval_ok(f["usd_per_win_qb_market"])
    for r in f["robustness"]:
        assert r["margin_lo"] <= r["margin"] <= r["margin_hi"]
    for g in ("history", "no_history"):
        assert _interval_ok(f["rest_of_season"][g]["rate"]) and 0 <= f["rest_of_season"][g]["rate"][0] <= 1
    rows = f["exposure_rows"]
    assert len({r["team"] for r in rows}) == len(rows) == 32
    for r in rows:
        assert r["starter_id"] != r["backup_id"]
        assert r["exp_wins_lost_rest_lo"] <= r["exp_wins_lost_rest"] <= r["exp_wins_lost_rest_hi"] or abs(r["exp_wins_lost_rest"]) < 1e-9
    assert all(x["team"] in {r["team"] for r in rows if not r["already_on_backup"]} for x in f["spotlight"])


def test_backup_qb_logic_on_made_up_games():
    import pandas as pd
    from projects.backup_qb_value import contract_in_force, game_qbs, season_starters, shrink, value_of_upgrade
    drop = pd.DataFrame({"game_id": ["g1"] * 5 + ["g2"] * 4 + ["g3"] * 3, "team": ["A"] * 12,
                         "passer_id": ["s", "s", "s", "b", "b", "b", "b", "b", "s", "s", "s", "s"],
                         "passer": ["S"] * 12, "epa": [0.1] * 12})
    tg = game_qbs(drop)
    assert dict(zip(tg.game_id, tg.qb)) == {"g1": "s", "g2": "b", "g3": "s"}          # most dropbacks in the game
    tg["season"] = 2020
    st = season_starters(tg)
    assert st.starter.iloc[0] == "s" and st.starter_starts.iloc[0] == 2                  # most games as the game's QB
    assert shrink([0.0], [0], -0.1, 200)[0] == pytest.approx(-0.1)                      # no record: the prior
    assert shrink([30.0], [200], 0.0, 200)[0] == pytest.approx(0.075)                   # half signal at k dropbacks
    hist = [{"contract_type": "Drafted", "year_signed": 2018.0, "yrs": 4.0, "apy": 1.0},
            {"contract_type": "Extension", "year_signed": 2021.0, "yrs": 2.0, "apy": 10.0},
            {"contract_type": "UFA", "year_signed": 2025.0, "yrs": 1.0, "apy": 3.0}]
    assert contract_in_force(hist, 2019)[0] == 1.0
    assert contract_in_force(hist, 2021)[0] == 1.0                                       # the extension signed in 2021 starts in 2022
    assert contract_in_force(hist, 2023)[0] == 10.0                                      # the extension covers 2022-2023
    assert contract_in_force(hist, 2024)[0] != contract_in_force(hist, 2024)[0]          # no deal covers 2024: nan
    assert contract_in_force(hist, 2025)[0] == 3.0
    w, usd = value_of_upgrade(3.0, 0.12, 0.10, 10.0)                                     # wins lost per start: $2M backup 0.12, $10M backup 0.10
    assert w == pytest.approx(0.06) and usd == pytest.approx(0.6)                        # 3 starts x 0.02 wins x $10M a win
