"""Study 13 (Metric Stability Atlas): logic tests on made-up data with a known answer, plus consistency checks on the
saved findings. None of the logic tests reads a published number."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from projects.metric_stability_atlas import (center_by_season, k_from_r, make_rows, oos_r2, random_halves, regress_share,
                                             reliability, season_values, shrink, shrink_test, split_half, spearman_brown, yoy)

R = Path(__file__).resolve().parents[1] / "reports" / "13-metric-stability-atlas"


def _sim(k_true=100.0, units=60, seasons=(2010, 2011, 2012, 2013), games=16, n_per_game=40, seed=0, persist=1.0):
    """Units with a true mean drawn once (persist=1 carries it across seasons) and per-trial noise.
    True-talent variance tau2 and trial variance sigma2 are set so that k = sigma2 / tau2 = k_true."""
    rng = np.random.default_rng(seed)
    tau = 1.0
    sigma = np.sqrt(k_true) * tau
    base = rng.normal(0, tau, units)
    rows = []
    for s in seasons:
        talent = persist * base + np.sqrt(1 - persist ** 2) * rng.normal(0, tau, units)
        base = talent
        for u in range(units):
            for w in range(1, games + 1):
                y = rng.normal(talent[u], sigma, n_per_game)
                rows.append((s, w, f"g{s}{w}{u}", f"u{u}", y.sum(), float(n_per_game)))
    return pd.DataFrame(rows, columns=["season", "week", "game_id", "unit", "num", "den"])


def test_regression_constant_round_trips_with_reliability():
    for r, n in [(0.2, 100), (0.5, 300), (0.8, 40)]:
        k = k_from_r(r, n)
        assert reliability(n, k) == pytest.approx(r)
        assert regress_share(n, k) == pytest.approx(1 - r)
        assert reliability(k, k) == pytest.approx(0.5)           # half signal at n = k
    assert k_from_r(0.0, 100) == float("inf") and k_from_r(-0.1, 100) == float("inf")
    assert reliability(500, float("inf")) == 0.0
    assert spearman_brown(0.5) == pytest.approx(2 / 3)
    assert spearman_brown(0.5) == pytest.approx(reliability(2 * 100, k_from_r(0.5, 100)))   # same answer two ways


def test_split_half_recovers_a_known_regression_constant():
    df = _sim(k_true=200.0, units=400, seasons=(2010, 2011), seed=1)
    rows = make_rows(df, "num", "den")
    out = split_half(rows, min_half=1, rng=np.random.default_rng(2), n_splits=20, n_boot_splits=5, b=100)
    n_h = 8 * 40
    assert out["n_half"] == pytest.approx(n_h)
    assert out["r"] == pytest.approx(n_h / (n_h + 200), abs=0.05)
    assert k_from_r(out["r"], out["n_half"]) == pytest.approx(200, rel=0.25)
    assert out["r_ci"][0] < out["r"] < out["r_ci"][1]


def test_split_half_of_pure_noise_is_near_zero():
    df = _sim(k_true=1e9, seed=3)                              # no real differences between units
    out = split_half(make_rows(df, "num", "den"), 1, np.random.default_rng(4), n_splits=30, n_boot_splits=5, b=100)
    assert abs(out["r"]) < 0.1
    assert out["r_ci"][0] < 0 < out["r_ci"][1]


def test_random_halves_keep_games_whole_and_balanced():
    df = pd.DataFrame({"season": 2020, "week": [1, 2, 3, 4, 5, 1, 2, 3], "game_id": list("abcdefgh"),
                       "unit": ["A"] * 5 + ["B"] * 3, "num": 1.0, "den": 1.0})
    rows = make_rows(df, "num", "den")
    for seed in range(20):
        m = random_halves(rows, np.random.default_rng(seed))
        assert len(m) == len(df)                               # one flag per game: a game is never split
        a_counts = np.bincount(rows.key[m], minlength=2)
        assert list(a_counts) == [2, 1]                        # floor(n/2) games go to half A for each unit


def test_season_centring_removes_a_pure_league_trend():
    rng = np.random.default_rng(5)
    season = np.repeat(np.arange(2006, 2026), 32)
    trend = (season - 2006) * 0.05                             # the league drifts, the teams do not differ
    a, b = trend + rng.normal(0, 0.01, len(season)), trend + rng.normal(0, 0.01, len(season))
    ok = np.ones(len(season), bool)
    assert np.corrcoef(a, b)[0, 1] > 0.9                        # uncentred: the trend looks like signal
    ac, bc = center_by_season(a, season, ok), center_by_season(b, season, ok)
    assert abs(np.corrcoef(ac, bc)[0, 1]) < 0.15


def test_two_part_metric_is_the_difference_of_two_ratios():
    df = pd.DataFrame({"season": 2020, "week": [1, 2], "game_id": ["a", "b"], "unit": "A",
                       "num": [3.0, 1.0], "den": [10.0, 10.0], "num2": [2.0, 2.0], "den2": [5.0, 15.0]})
    v, d, d2 = season_values(make_rows(df, "num", "den", "num2", "den2"))
    assert v[0] == pytest.approx(4 / 20 - 4 / 20)
    assert d[0] == 20 and d2[0] == 20


def test_year_to_year_follows_how_much_talent_persists():
    hi = yoy(make_rows(_sim(k_true=20, persist=0.9, seed=6), "num", "den"), min_season=1, b=100)
    lo = yoy(make_rows(_sim(k_true=20, persist=0.1, seed=6), "num", "den"), min_season=1, b=100)
    assert hi["r"] > 0.7 and abs(lo["r"]) < 0.25
    assert hi["pairs"] == 60 * 3


def test_regressed_forecast_beats_the_raw_number_when_samples_are_noisy():
    df = _sim(k_true=400.0, seed=7)
    rows = make_rows(df, "num", "den")
    st = shrink_test(rows, k=400.0, min_half=1, seasons=[2012, 2013])
    assert st["mse_shrunk"] < st["mse_raw"]
    assert st["mse_shrunk"] <= st["mse_mean"] * 1.02
    assert st["obs_slope"] == pytest.approx(st["pred_reliability"], abs=0.2)
    assert shrink(1.0, 0.0, 100, 100) == pytest.approx(0.5)


def test_out_of_sample_r2_scores_a_real_signal_and_rejects_noise():
    rng = np.random.default_rng(8)
    x = rng.normal(size=400); y = 2 * x + rng.normal(0, 0.1, 400)
    assert oos_r2(x[:200], y[:200], x[200:], y[200:]) > 0.95
    z = rng.normal(size=400)
    assert oos_r2(z[:200], y[:200], z[200:], y[200:]) < 0.03


# ---------- consistency of the saved findings (shapes, not conclusions) ----------
def _load():
    p = R / "findings.json"
    if not p.exists():
        pytest.skip("13-metric-stability-atlas not built")
    return json.loads(p.read_text())


def test_atlas_findings_are_internally_consistent():
    f = _load()
    assert len(f["atlas"]) >= 40
    for name, r in f["atlas"].items():
        lo, hi = r["split_half_ci"]
        assert -1 <= lo <= hi <= 1, name
        assert r["yoy_ci"][0] <= r["yoy_r"] <= r["yoy_ci"][1], name
        assert 0 <= r["regress_17"] <= r["regress_8"] <= r["regress_4"] <= 1, name      # more games, less regression
        assert r["rel_full_season"] == pytest.approx(1 - r["regress_17"], abs=0.002), name
        if r["k"] is not None:
            assert r["k"] > 0 and r["k_games"] == pytest.approx(r["k"] / r["per_game"], rel=0.005, abs=0.06), name
            assert r["split_half_r"] == pytest.approx(r["half_sample"] / (r["half_sample"] + r["k"]), abs=0.002), name
    assert f["oos_shrunk_beats_raw"] <= f["oos_metrics"] and f["oos_shrunk_beats_mean"] <= f["oos_metrics"]


def test_prediction_findings_are_internally_consistent():
    f = _load()
    p = f["predict_rest"]
    for k, v in p.items():
        if k.startswith("_"):
            continue
        assert v["r_rest_pd_ci"][0] <= v["r_rest_pd"] <= v["r_rest_pd_ci"][1], k
        assert v["minus_point_diff"][1] <= v["minus_point_diff"][0] <= v["minus_point_diff"][2], k
    assert p["res_point_diff"]["minus_point_diff"] == [0.0, 0.0, 0.0]          # the baseline minus itself
    assert set(f["predict_beats_pd"]) <= {k for k in p if not k.startswith("_")}
    q = f["qb_predict"]
    assert q["cpoe_minus_epa"][0] == pytest.approx(q["qb_cpoe"]["r"] - q["qb_epa"]["r"], abs=0.002)
