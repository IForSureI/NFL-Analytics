"""Logic tests on small made-up tables. Each test builds data with a known answer and checks that the code
recovers it. None of them reads a published number, so none of them can pass by agreeing with a conclusion."""
import numpy as np
import pandas as pd
import pytest

from nflan.fourth import FourthDownBot, fg_range, _flip
from nflan.stats import boot_r, boot_ratio
from nflan.wp import FEATURES, WPModel
from projects.box_score_tax import _beta, boot_players, one_deal_per_player_year, rush_group, sack_luck, shrunk_luck, add_prior
from projects.kickoff_value import eb_normal, is_onside_or_squib, split_half, tb_spot
from projects.luck_index import _luck_stats, matched_gap, team_games
from projects.pass_run import neutral


# ---------- win probability and the fourth-down bot ----------
def _states(n, rng):
    s = pd.DataFrame({
        "score_differential": rng.integers(-21, 22, n).astype(float),
        "game_seconds_remaining": rng.integers(60, 3600, n).astype(float),
        "yardline_100": rng.integers(1, 100, n).astype(float),
        "down": rng.integers(1, 5, n).astype(float),
        "ydstogo": rng.integers(1, 15, n).astype(float),
        "posteam_timeouts_remaining": 3.0, "defteam_timeouts_remaining": 3.0,
        "receive_2h_ko": rng.integers(0, 2, n).astype(float),
        "posteam_spread": rng.normal(0, 5, n),
    })
    s["half_seconds_remaining"] = s.game_seconds_remaining % 1800
    s["is_second_half"] = (s.game_seconds_remaining <= 1800).astype(float)
    return s[FEATURES]


def test_wp_model_learns_a_known_rule_and_stays_monotone():
    rng = np.random.default_rng(0)
    s = _states(3000, rng)
    s["y"] = (rng.random(len(s)) < 1 / (1 + np.exp(-s.score_differential / 5))).astype(int)  # only the score matters
    m = WPModel.fit(s)
    probe = _states(1, np.random.default_rng(1))
    grid = pd.concat([probe.assign(score_differential=float(d)) for d in range(-21, 22, 3)], ignore_index=True)
    p = m.predict(grid)
    assert np.all(np.diff(p) >= -1e-9)          # more points ahead never lowers win probability
    assert p[0] < 0.2 and p[-1] > 0.8           # and the fitted rule is the one that made the data
    far = m.predict(probe.assign(yardline_100=95.0)); near = m.predict(probe.assign(yardline_100=5.0))
    assert near[0] >= far[0] - 1e-9             # closer to the end zone never lowers it


class _WP:
    """Stand-in model with a closed form, so the bot's arithmetic can be checked by hand."""
    def predict(self, s):
        return np.clip(0.5 + 0.02 * s["score_differential"].to_numpy(float) - 0.002 * (s["yardline_100"].to_numpy(float) - 50), 0.01, 0.99)


class _Const:
    def __init__(self, p): self.p = p
    def predict_proba(self, X): return np.column_stack([np.full(len(X), 1 - self.p), np.full(len(X), self.p)])
    def predict(self, X): return np.full(len(X), 80.0)


def _bot(p_conv=0.5, p_make=0.8, fg_max=55):
    gain = pd.DataFrame({"bucket": pd.cut(pd.Series([1, 2, 3, 5, 8, 12]), [0, 1, 2, 4, 7, 10, 99]), "extra": 0.0})
    return FourthDownBot(wp=_WP(), convert=_Const(p_conv), fg=_Const(p_make), punt_net=_Const(0), gain_given_convert=gain,
                         kickoff_start=70.0, fg_max_dist=fg_max)


def _fourth(yardline, ydstogo=2.0):
    s = _states(1, np.random.default_rng(2)).assign(score_differential=0.0, yardline_100=float(yardline), ydstogo=float(ydstogo), down=4.0)
    return s.assign(roof_indoor=0, season=2024)


def test_bot_go_value_is_the_weighted_average_of_both_outcomes():
    s = _fourth(50, 2)
    out = _bot(p_conv=0.5).evaluate(s)
    wp = _WP()
    conv = wp.predict(s.assign(yardline_100=48.0))            # first down two yards on
    fail = 1 - wp.predict(_flip(s, 50, 0, 6))                 # opponent takes over at the spot
    assert out.wp_go.iloc[0] == pytest.approx(0.5 * conv[0] + 0.5 * fail[0])
    assert _bot(p_conv=0.9).evaluate(s).wp_go.iloc[0] > out.wp_go.iloc[0]   # a better offense makes going worth more


def test_bot_never_offers_a_kick_out_of_range_or_a_punt_in_close():
    b = _bot(fg_max=55)
    long_kick = b.evaluate(_fourth(45))      # 63-yard try, beyond the 55-yard range
    assert np.isnan(long_kick.wp_fg.iloc[0]) and long_kick.p_make.iloc[0] == 0 and long_kick.best_kick.iloc[0] == "punt"
    in_range = b.evaluate(_fourth(30))       # 48-yard try, inside the 35 so no punt
    assert not np.isnan(in_range.wp_fg.iloc[0]) and np.isnan(in_range.wp_punt.iloc[0]) and in_range.best_kick.iloc[0] == "fg"


def test_bot_recommendation_follows_the_sign_of_go_boost():
    out = pd.concat([_bot(p_conv=p).evaluate(_fourth(40, 1)) for p in (0.05, 0.95)])
    assert list(out.rec == "go") == list(out.go_boost > 0)
    assert out.go_boost.iloc[1] > out.go_boost.iloc[0]


def test_fg_range_is_the_longest_distance_coaches_still_kick_from():
    rows = []
    for yl, share in [(20, 0.9), (30, 0.6), (35, 0.3), (40, 0.05), (45, 0.5)]:   # 45: half kick, but only 10 plays
        n = 10 if yl == 45 else 100
        k = int(round(share * n))
        rows += [{"yardline_100": yl, "play_type": "field_goal"}] * k + [{"yardline_100": yl, "play_type": "punt"}] * (n - k)
    assert fg_range(pd.DataFrame(rows), min_share=0.25, min_n=40) == 35 + 18


# ---------- contracts and sack luck ----------
def test_one_deal_per_player_year_keeps_the_longer_deal():
    c = pd.DataFrame({"gsis_id": ["a", "a", "a", "b"], "year_signed": [2024, 2024, 2025, 2024],
                      "years": [1, 4, 1, 2], "apy": [20.0, 18.0, 5.0, 3.0]})
    out = one_deal_per_player_year(c)
    assert len(out) == 3
    assert out[(out.gsis_id == "a") & (out.year_signed == 2024)].years.iloc[0] == 4   # the tag is dropped, the extension kept


def test_sack_luck_is_measured_within_position_group():
    df = pd.DataFrame({"sk": [10.0, 10.0], "prss": [40.0, 40.0], "grp": rush_group(pd.Series(["DE", "DT"]))})
    luck = sack_luck(df, {"edge": 0.25, "interior": 0.20})
    assert list(df.grp) == ["edge", "interior"]
    assert luck.tolist() == pytest.approx([0.0, 2.0])


def test_shrunk_luck_moves_toward_zero_and_small_samples_move_most():
    raw_small, raw_big = 4 - 0.25 * 8, 20 - 0.25 * 40
    s_small = shrunk_luck(4.0, 8.0, 0.25, 100); s_big = shrunk_luck(20.0, 40.0, 0.25, 100)
    assert 0 < s_small < raw_small and 0 < s_big < raw_big
    assert s_small / raw_small < s_big / raw_big
    assert shrunk_luck(10.0, 40.0, 0.25, 100) == pytest.approx(0.0)


def test_add_prior_attaches_the_season_before_and_flags_missing_ones():
    ps = pd.DataFrame({"pid": ["a", "a", "b"], "season": [2022, 2023, 2023], "prss": [30.0, 50.0, 20.0], "sk": [5.0, 9.0, 2.0]})
    out = add_prior(ps.copy(), ps, "pid", "season").sort_values(["pid", "season"]).reset_index(drop=True)
    assert out.prev_prss.tolist() == [0.0, 30.0, 0.0] and out.has_prev.tolist() == [0.0, 1.0, 0.0]


def test_beta_recovers_known_slopes_and_player_bootstrap_keeps_players_whole():
    rng = np.random.default_rng(3)
    d = pd.DataFrame({"pid": np.repeat(np.arange(60), 3), "x1": rng.normal(size=180), "x2": rng.normal(size=180)})
    d["y"] = 2.0 * d.x1 - 1.0 * d.x2 + 5
    assert _beta(d.y, d[["x1", "x2"]]) == pytest.approx([2.0, -1.0])
    seen = boot_players({"d": (d, "pid")}, lambda s: s["d"].groupby("pid").size().mod(3).eq(0).all() and len(s["d"]) == 180, n=20)
    assert all(seen)        # every draw holds whole players (rows come in threes) and the same number of rows


# ---------- kickoffs ----------
def test_touchback_spot_follows_the_rule_and_fails_loudly_for_an_unknown_season():
    # yards from the receiving team's goal line to score: own 25, own 30, own 35
    assert tb_spot(2023) == 75 and tb_spot(2024) == 70 and tb_spot(2025) == 65
    with pytest.raises(KeyError):
        tb_spot(2031)


def test_onside_and_squib_kicks_are_found_in_the_description():
    d = pd.Series(["J.Tucker kicks onside 12 yards", "kicks 65 yards from BAL 35 to end zone, Touchback", "B.Aubrey Squib kick", None])
    assert is_onside_or_squib(d).tolist() == [True, False, True, False]


def test_empirical_bayes_shrinks_noise_to_zero_and_keeps_real_spread():
    rng = np.random.default_rng(4)
    n = pd.Series(np.full(200, 50.0))
    noise_only = pd.Series(rng.normal(0, 1, (200, 50)).sum(1))
    shrunk, half, var_true = eb_normal(noise_only, n, 1.0)
    assert var_true < 0.01 and shrunk.abs().max() < 0.2
    skill = np.repeat([-1.0, 1.0], 100)
    real = pd.Series((rng.normal(0, 1, (200, 50)) + skill[:, None]).sum(1))
    shrunk, half, var_true = eb_normal(real, n, 1.0)
    assert 0.8 < var_true < 1.2 and np.corrcoef(shrunk, skill)[0, 1] > 0.95


def test_split_half_separates_skill_from_noise():
    rng = np.random.default_rng(5)
    rows = [{"pid": p, "game_id": "g", "play_id": i, "skill": float(p), "noise": rng.normal()} for p in range(30) for i in range(40)]
    df = pd.DataFrame(rows)
    df["skilled"] = df.skill + df.noise
    r_skill, n = split_half(df, "pid", "skilled", 10)
    r_noise, _ = split_half(df, "pid", "noise", 10)
    assert n == 30 and r_skill > 0.95 and abs(r_noise) < 0.5


# ---------- luck ----------
def test_team_games_counts_wins_ties_and_one_score_games():
    g = pd.DataFrame({"game_id": ["1", "2"], "season": 2024, "week": [1, 2], "home_team": ["A", "A"], "away_team": ["B", "B"],
                      "home_score": [20, 17], "away_score": [10, 17]})
    t = team_games(g).set_index(["game_id", "team"])
    assert t.loc[("1", "A"), "win"] == 1 and t.loc[("1", "B"), "win"] == 0 and t.loc[("2", "A"), "win"] == 0.5
    assert not t.loc[("1", "A"), "one_score"] and t.loc[("2", "B"), "one_score"]


def _luck_frame(carry, rng, n=4000):
    p17 = rng.normal(8.5, 2, n); luck = rng.normal(0, 1.5, n)
    d = pd.DataFrame({"p17": p17, "luck17": luck, "w17": p17 + luck})
    d["w17_next"] = 8.5 + 0.5 * (p17 - 8.5) + carry * luck + rng.normal(0, 0.5, n)
    d["fumble_luck"] = rng.normal(size=n); d["fg_luck"] = rng.normal(size=n); d["one_score_luck"] = rng.normal(size=n)
    d["pyth_pct"] = d.p17 / 17; d["winpct"] = d.w17 / 17; d["winpct_next"] = d.w17_next / 17
    return d


def test_luck_regression_recovers_how_much_luck_carries_over():
    for carry in (0.0, 0.5):
        s = _luck_stats(_luck_frame(carry, np.random.default_rng(6)))
        assert s["next_wins_per_pythag_win"] == pytest.approx(0.5, abs=0.03)
        assert s["next_wins_per_luck_win"] == pytest.approx(carry, abs=0.03)


def test_matched_comparison_removes_plain_regression_to_the_mean():
    # luck carries over exactly like points here, so lucky teams fall back only as much as any team with their record
    d = _luck_frame(0.5, np.random.default_rng(7), n=20000)
    raw_fall = (d[d.luck17 >= 2].w17_next - d[d.luck17 >= 2].w17).mean()
    assert raw_fall < -1.0                                  # the raw fall looks like "luck running out"...
    assert abs(matched_gap(d, 1)) < 0.25                    # ...and vanishes against same-record teams
    lost = _luck_frame(0.0, np.random.default_rng(7), n=20000)
    assert matched_gap(lost, 1) < -0.5 and matched_gap(lost, -1) > 0.5   # when luck is lost, the matched gap shows it


# ---------- pass vs run, shared stats ----------
def test_neutral_filter_keeps_only_early_downs_in_close_games():
    base = dict(down=1, wp=0.5, half_seconds_remaining=900, qtr=2, play_type="pass", epa=0.1, qb_kneel=0, qb_spike=0, two_point_attempt=0)
    rows = [base, {**base, "down": 3}, {**base, "wp": 0.95}, {**base, "half_seconds_remaining": 60}, {**base, "qb_kneel": 1},
            {**base, "play_type": "punt"}, {**base, "qtr": 5}, {**base, "down": 2, "play_type": "run"}]
    assert list(neutral(pd.DataFrame(rows)).index) == [0, 7]


def test_boot_r_interval_covers_the_truth_and_widens_when_groups_are_resampled():
    rng = np.random.default_rng(8)
    g = np.repeat(np.arange(30), 10)
    team = rng.normal(size=30)[g]
    x = team + rng.normal(0, 0.3, 300); y = team + rng.normal(0, 0.3, 300)
    r, lo, hi = boot_r(x, y, n=400)
    rg, glo, ghi = boot_r(x, y, groups=g, n=400)
    assert lo < r < hi and r == pytest.approx(rg)
    assert (ghi - glo) > (hi - lo)          # rows from one team are not independent, and the interval says so
    z, zlo, zhi = boot_r(rng.normal(size=300), rng.normal(size=300), n=400)
    assert zlo < 0 < zhi


def test_boot_ratio_point_estimate_and_interval():
    num = np.array([1.0, 0.0, 2.0, 1.0] * 50); den = np.full(200, 100.0)
    p, lo, hi = boot_ratio(num, den, n=500, scale=100)
    assert p == pytest.approx(1.0) and lo < 1.0 < hi and hi - lo < 0.5
