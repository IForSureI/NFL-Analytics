"""Fast tests on synthetic data plus model sanity checks on real data when it is cached."""
import numpy as np
import pandas as pd
import pytest

from nflan.stats import wilson, shrink_rate, pythag_wins, split_half_r
from nflan.penalties import classify, accepted_flags
from nflan.wp import add_features, derive, labels, FEATURES, MODEL_FEATURES


def test_wilson_contains_rate_and_is_bounded():
    lo, hi = wilson(10, 100)
    assert 0 <= lo < 0.10 < hi <= 1


def test_shrink_pulls_small_samples_toward_mean():
    k = pd.Series([2, 10, 30]); n = pd.Series([2, 1000, 2000])
    s = shrink_rate(k, n)
    pooled = k.sum() / n.sum()
    assert pooled < s[0] < 1.0          # 2-for-2 is pulled hard toward the pooled rate
    assert abs(s[1] - 0.01) < 0.005     # a big sample barely moves


def test_pythag_even_points_is_half():
    assert pythag_wins([300], [300], 17)[0] == pytest.approx(8.5)


def test_split_half_perfect_signal():
    df = pd.DataFrame({"season": 1, "team": list("AABB"), "odd": [0, 1, 0, 1], "x": [1, 1, 5, 5]})
    df = pd.concat([df, df.assign(team=["C", "C", "D", "D"], x=[2, 2, 9, 9])])
    assert split_half_r(df, "x") == pytest.approx(1.0)


def test_flag_classification():
    s = classify(pd.Series(["False Start", "Defensive Pass Interference", "Leverage"]))
    assert list(s) == ["objective", "subjective", "other"]


def test_accepted_flags_drops_declined():
    df = pd.DataFrame({"penalty": [1, 1, 0], "penalty_type": ["False Start", "Offensive Holding", None],
                       "penalty_team": ["A", "A", None], "posteam": ["A", "A", "A"],
                       "desc": ["False Start on A", "Holding on A, declined", "run"]})
    out = accepted_flags(df)
    assert len(out) == 1 and out.iloc[0].penalty_type == "False Start"


def test_wp_features_kickoff_logic():
    df = pd.DataFrame({"posteam": ["H", "A"], "home_team": ["H", "H"], "spread_line": [3.0, 3.0],
                       "home_opening_kickoff": [1, 1], "qtr": [1, 1]})
    f = add_features(df)
    # home received the opening kickoff, so the away team receives the second-half kickoff
    assert list(f.receive_2h_ko) == [0, 1]
    assert list(f.posteam_spread) == [3.0, -3.0]


def test_spread_fades_with_time():
    s = pd.DataFrame({c: [0.0, 0.0] for c in FEATURES})
    s["posteam_spread"] = [7.0, 7.0]; s["game_seconds_remaining"] = [3600, 60]
    X = derive(s)
    assert X.spread_time.iloc[0] > X.spread_time.iloc[1] > 0
    assert list(X.columns) == MODEL_FEATURES


def test_labels_from_result():
    df = pd.DataFrame({"posteam": ["H", "A"], "home_team": ["H", "H"], "result": [7, 7]})
    assert list(labels(df)) == [1, 0]
