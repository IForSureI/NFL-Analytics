"""Held-out tests for the fourth-down bot's component models: the scoring tools and the fitting frames, on made-up
data with a known answer. None of these reads a published number."""
import numpy as np
import pandas as pd
import pytest

from nflan.fourth import FourthDownBot, convert_frame, fg_frame, grade_calls, punt_frame
from nflan.holdout import (beats, bin_rate, brier_rows, calibration_by, flip_share, headline_moves, log_loss_rows,
                           paired_scores, split_seasons)


def test_split_puts_every_season_on_one_side():
    df = pd.DataFrame({"season": [2021, 2022, 2023, 2024, 2025], "v": range(5)})
    tr, te = split_seasons(df, 2023)
    assert list(tr.season) == [2021, 2022, 2023] and list(te.season) == [2024, 2025]
    assert not set(tr.season) & set(te.season)


def test_log_loss_and_brier_by_hand():
    assert log_loss_rows([0.5, 0.5], [1, 0]) == pytest.approx([np.log(2)] * 2)
    assert log_loss_rows([0.8], [1])[0] == pytest.approx(-np.log(0.8))
    assert np.isfinite(log_loss_rows([0.0, 1.0], [1, 0])).all()          # a certain miss is large, not infinite
    assert log_loss_rows([0.0], [1])[0] > log_loss_rows([0.01], [1])[0]
    assert brier_rows([0.8, 0.3], [1, 0]) == pytest.approx([0.04, 0.09])


def test_bin_rate_is_the_training_mean_of_each_bin():
    x = [1, 1, 1, 1, 5, 5, 5, 5]; y = [1, 1, 1, 0, 0, 0, 0, 1]
    f = bin_rate(x, y, [0, 2, 6, 10])
    assert f([1, 5]) == pytest.approx([0.75, 0.25])
    assert f([8, 50]) == pytest.approx([0.5, 0.5])                         # no training rows there: the overall mean


def test_paired_scores_point_values_and_a_model_against_itself():
    loss = np.array([0.1, 0.2, 0.3, 0.4]); g = ["a", "a", "b", "c"]
    s = paired_scores({"model": loss, "same": loss, "flat": np.full(4, 0.5)}, g, n=500)
    assert s["model"][0] == pytest.approx(0.25) and s["flat"] == pytest.approx([0.5, 0.5, 0.5])
    assert s["model_minus_same"] == pytest.approx([0, 0, 0])               # paired: the same games score both
    assert s["model"][1] <= s["model"][0] <= s["model"][2]
    r = paired_scores({"model": np.array([9.0, 16.0])}, ["a", "b"], n=200, root=True)
    assert r["model"][0] == pytest.approx(np.sqrt(12.5))                   # RMSE, not mean of roots


def test_a_model_that_knows_the_truth_beats_the_league_average():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 6000); y = (rng.random(6000) < p).astype(int); games = rng.integers(0, 300, 6000)
    for rows in (brier_rows, log_loss_rows):
        s = paired_scores({"model": rows(p, y), "league_avg": rows(np.full(6000, y.mean()), y)}, games, n=500)
        assert beats(s["model_minus_league_avg"]) == "better"
        coin = paired_scores({"model": rows(np.full(6000, y.mean()), y), "league_avg": rows(np.full(6000, y.mean()), y)}, games, n=500)
        assert beats(coin["model_minus_league_avg"]) == "tie"              # no information, no win


def test_resampling_games_is_wider_than_resampling_plays_when_games_differ():
    rng = np.random.default_rng(1)
    game = np.repeat(np.arange(40), 50)
    loss = rng.normal(0, 1, 40)[game] + rng.normal(0, 0.1, 2000)            # almost all of the spread is between games
    by_game = paired_scores({"model": loss}, game, n=1000)["model"]
    by_play = paired_scores({"model": loss}, np.arange(2000), n=1000)["model"]
    assert (by_game[2] - by_game[1]) > 3 * (by_play[2] - by_play[1])


def test_calibration_table_keeps_counts_and_means():
    t = calibration_by([0.1, 0.1, 0.9, 0.9, 0.9], [0.1, 0.1, 0.9, 0.9, 0.9], [0, 1, 1, 1, 0], [0, 0.5, 1.0])
    assert list(t.n) == [2, 3] and t.n.sum() == 5
    assert t.actual.tolist() == pytest.approx([0.5, 2 / 3]) and t.pred.tolist() == pytest.approx([0.1, 0.9])


def test_flip_share_counts_changed_recommendations():
    a = ["go"] * 6 + ["punt"] * 4; b = ["go"] * 5 + ["fg"] + ["punt"] * 3 + ["go"]
    f = flip_share(a, b, np.arange(10), n=500)
    assert f[0] == pytest.approx(0.2) and 0 <= f[1] <= f[0] <= f[2] <= 1
    assert flip_share(a, a, np.arange(10), n=100) == pytest.approx([0, 0, 0])


def test_headline_rule_fires_only_outside_the_published_intervals():
    card = pd.DataFrame({"posteam": ["A", "B", "C", "D"], "wp_lost_per_game": [1.0, 2.0, 3.0, 4.0],
                         "ci_low": [0.5, 1.5, 2.5, 3.5], "ci_high": [1.5, 2.5, 3.5, 4.5], "held_out": [1.1, 2.2, 2.9, 4.0]})
    assert headline_moves({2024: (0.55, 0.50, 0.60, 0.57)}, card) == []
    assert headline_moves({2024: (0.55, 0.50, 0.60, 0.62)}, card) == ["go rate 2024"]
    moved = card.assign(held_out=[1.1, 2.9, 2.9, 4.0])
    assert headline_moves({2024: (0.55, 0.50, 0.60, 0.57)}, moved) == ["team card B"]
    shuffled = card.assign(held_out=[1.4, 1.6, 3.4, 3.6], ci_low=0.0, ci_high=9.0)   # inside every interval, but reordered
    assert any(w.startswith("team card r") for w in headline_moves({}, shuffled.assign(held_out=[4.0, 3.0, 2.0, 1.0])))
    assert headline_moves({}, shuffled) == []


# ---------- the frames the models are fit and scored on ----------
def _plays():
    return pd.DataFrame({
        "down": [3, 4, 4, 1, 4, 3], "play_type": ["pass", "run", "pass", "run", "punt", "run"],
        "ydstogo": [5.0, 1.0, 8.0, 10.0, 6.0, 2.0], "yardline_100": [40.0, 30.0, 6.0, 75.0, 60.0, 50.0],
        "yards_gained": [7.0, 0.0, 6.0, 12.0, 0.0, 1.0], "touchdown": [0, 0, 1, 0, 0, 0],
        "td_team": [None, None, "A", None, None, None], "posteam": ["A"] * 6, "posteam_spread": [3.0] * 6})


def test_convert_frame_definition():
    X, y, d = convert_frame(_plays())
    assert list(d.down) == [3, 4, 4, 3]                 # first downs and punts are out
    assert list(y) == [1, 0, 1, 0]                      # gained the distance; stuffed; scored short of the sticks; short
    assert list(X.is4) == [0, 1, 1, 0] and list(X.columns) == ["ydstogo", "yardline_100", "is4", "posteam_spread"]
    lost = _plays().assign(td_team=[None, None, "B", None, None, None])
    assert list(convert_frame(lost)[1]) == [1, 0, 0, 0]  # a defensive touchdown is not a conversion


def _kicks(rng, n=600):
    dist = rng.integers(20, 60, n).astype(float)
    made = rng.random(n) < 1 / (1 + np.exp((dist - 50) / 6))
    return pd.DataFrame({"field_goal_attempt": 1, "kick_distance": dist, "field_goal_result": np.where(made, "made", "missed"),
                         "roof": rng.choice(["dome", "outdoors"], n), "season": rng.integers(2016, 2026, n)})


def test_fg_frame_and_a_training_fit_that_never_sees_the_test_seasons():
    k = _kicks(np.random.default_rng(3))
    X, made, rows = fg_frame(pd.concat([k, k.head(3).assign(kick_distance=np.nan)]))
    assert len(rows) == len(k) and made.sum() == (k.field_goal_result == "made").sum()
    assert X[:, 1] == pytest.approx(X[:, 0] ** 2) and set(X[:, 2]) == {0.0, 1.0}
    scrambled = k.copy()                                 # change every outcome after 2023: the training fit must not move
    late = scrambled.season > 2023
    scrambled.loc[late, "field_goal_result"] = np.where(scrambled.loc[late, "field_goal_result"] == "made", "missed", "made")
    a = FourthDownBot.fit_fg(split_seasons(k, 2023)[0]); b = FourthDownBot.fit_fg(split_seasons(scrambled, 2023)[0])
    assert a.coef_ == pytest.approx(b.coef_) and a.intercept_ == pytest.approx(b.intercept_)
    assert FourthDownBot.fit_fg(scrambled).coef_ != pytest.approx(a.coef_)   # and the full fit does


def test_punt_frame_takes_the_other_teams_next_snap():
    pbp = pd.DataFrame({
        "game_id": ["g"] * 5 + ["h"] * 2, "play_id": [1, 2, 3, 4, 5, 1, 2], "season": 2024,
        "posteam": ["A", "B", "B", "B", "B", "A", "A"], "play_type": ["punt", "run", "pass", "punt", "kickoff", "punt", "run"],
        "punt_attempt": [1, 0, 0, 1, 0, 1, 0], "yardline_100": [70.0, 78.0, 70.0, 60.0, 35.0, 55.0, 30.0]})
    m = punt_frame(pbp, pbp)
    assert len(m) == 1                                   # B's punt has no next snap; A kept the ball after the muff in game h
    assert m.yardline_100.iloc[0] == 70.0 and m.next_yl.iloc[0] == 78.0 and m.next_team.iloc[0] == "B"


def test_punt_model_moves_the_opponent_back_as_the_punter_moves_up():
    rng = np.random.default_rng(4)
    rows, pid = [], 0
    for i in range(1500):
        spot = float(rng.integers(36, 99)); net = float(np.clip(rng.normal(42, 8), 5, spot - 1))
        land = 100 - spot + net                          # the other team's distance to its end zone
        land = 80.0 if land > 99 else land
        rows += [dict(game_id=f"g{i}", play_id=1, season=2020, posteam="A", play_type="punt", punt_attempt=1, yardline_100=spot),
                 dict(game_id=f"g{i}", play_id=2, season=2020, posteam="B", play_type="run", punt_attempt=0, yardline_100=land)]
    pbp = pd.DataFrame(rows)
    reg = FourthDownBot.fit_punt(pbp, pbp)
    p = reg.predict(pd.DataFrame({"yardline_100": [40.0, 55.0, 70.0, 85.0, 95.0]}))
    assert np.all(np.diff(p) <= 1e-9)                    # a punt from deeper never pins the opponent deeper
    assert p[0] - p[-1] > 25                             # and the model is not one number for every spot


# ---------- the grading rule shared by the published bot and the before-the-fix comparison ----------
def _opts(go, fg, punt):
    o = pd.DataFrame({"wp_go": go, "wp_fg": fg, "wp_punt": punt}, dtype=float)
    o["go_boost"] = 100 * (o.wp_go - o[["wp_fg", "wp_punt"]].max(axis=1, skipna=True))
    return o


def test_grade_calls_charges_only_misses_that_survive_the_refits():
    #            kicked, gap 3   kicked, gap 3   kicked, gap 0.5   went, best
    point = _opts([0.50, 0.50, 0.505, 0.50], [0.47, 0.47, 0.50, 0.47], [np.nan, 0.40, 0.45, 0.40])
    chosen = np.array([1, 1, 1, 0])
    steady = [point.copy() for _ in range(20)]
    lost, clear_go = grade_calls(point, steady, chosen)
    assert lost == pytest.approx([3.0, 3.0, 0.0, 0.0])                      # under 1 point is never charged; the best call costs nothing
    assert list(clear_go) == [True, True, False, True]                     # a go spot needs 2+ points
    # in a few refits the kick is the better call for row 1: the miss and the go spot no longer hold up
    flipped = _opts([0.50, 0.45, 0.505, 0.50], [0.47, 0.47, 0.50, 0.47], [np.nan, 0.40, 0.45, 0.40])
    lost, clear_go = grade_calls(point, steady[:17] + [flipped] * 3, chosen)
    assert lost == pytest.approx([3.0, 0.0, 0.0, 0.0]) and list(clear_go) == [True, False, False, True]
    # a punt that was not offered (NaN) is never the best option
    assert grade_calls(_opts([0.5], [0.6], [np.nan]), [_opts([0.5], [0.6], [np.nan])] * 5, np.array([1]))[0] == pytest.approx([0.0])
