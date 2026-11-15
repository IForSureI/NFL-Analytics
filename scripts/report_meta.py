"""Per-study presentation content for the report READMEs (see docs/report-standard.md).

build_readmes.py writes each study's findings (numbers from findings.json). This file adds what a
professional write-up needs around them: the one-line question, key-number table, what a club does
with it, equations, validation, next steps, figure placement and file descriptions.

Every study in build_readmes.REPORTS must have an entry here (tests/test_readme_standard.py checks).
Numbers in "key" and "validation" are lambdas over findings.json so a refresh keeps them current.
"""
from __future__ import annotations


def _pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def _era(f):
    return {k.strip("()").replace("'", "").replace(" ", ""): v for k, v in f["home_edge_by_era"].items()}


def _eras(f):
    return sorted({k.split(",")[0] for k in _era(f)})


def _kg(r, d=1):
    """Games to half signal, as text."""
    k = r["k_games"]
    if k is None:
        return "no measurable signal"
    return f"{k:.0f}" if k >= 100 else f"{k:.{d}f}"


def _kgci(r):
    lo, hi = r["k_games_ci"]
    lo_t = "0" if lo is None else (f"{lo:.0f}" if lo >= 100 else f"{lo:.1f}")
    hi_t = "no upper bound" if hi is None else (f"{hi:.0f}" if hi >= 100 else f"{hi:.1f}")
    return f"{lo_t} to {hi_t}"


def atlas_table(f, team=True):
    """The ranked atlas: most to least reliable over a full season, with the regression guide."""
    tg = {"Offense", "Defense", "Special teams", "Team"}
    rows = sorted([r for r in f["atlas"].values() if (r["group"] in tg) == team], key=lambda r: -r["rel_full_season"])
    head = ("| # | Metric | Trial | Split-half r (95%) | Half signal after k trials (games) | Signal in a full season | "
            "Regress after 4 / 8 / 17 games | Year-to-year r (95%) |\n|---|---|---|---|---|---|---|---|")
    out = [head]
    for i, r in enumerate(rows, 1):
        k = "no measurable signal" if r["k"] is None else f"{r['k']:,.0f} ({_kg(r)})"
        out.append(f"| {i} | {r['label']} | {r['unit']} | {r['split_half_r']:.2f} ({r['split_half_ci'][0]:.2f} to {r['split_half_ci'][1]:.2f}) | {k} | "
                   f"{100 * r['rel_full_season']:.0f}% | {100 * r['regress_4']:.0f}% / {100 * r['regress_8']:.0f}% / {100 * r['regress_17']:.0f}% | "
                   f"{r['yoy_r']:.2f} ({r['yoy_ci'][0]:.2f} to {r['yoy_ci'][1]:.2f}) |")
    return "\n".join(out)


META = {
    "01-flag-audit": dict(
        short="Flag Audit",
        tldr=lambda f: [
            f"Road teams drew {_era(f)[_eras(f)[0] + ',subjective']:.2f} more judgment-call flags a game than home teams in {_eras(f)[0]}; since 2023 the gap has averaged {round(_era(f)[_eras(f)[-1] + ',subjective'], 2) + 0:.2f}. The drop is real per snap (95% interval {f['road_subj_drop_per_100_snaps_ci'][1]:.2f} to {f['road_subj_drop_per_100_snaps_ci'][2]:.2f} per 100 snaps) but not yet in close games only, and I picked 2023 from the chart.",
            f"Referee crews have a modest style (year-to-year r = {f['crew_yoy_r']:.2f}, 95% interval {f['crew_yoy_r_ci'][0]:.2f} to {f['crew_yoy_r_ci'][1]:.2f}); a team's flag luck does not carry over (r = {f['split_r_net']:.2f}).",
            f"Mahomes ranks #{f['rtp_mahomes'][1]} of {f['rtp_mahomes'][2]} QBs in roughing flags drawn, right at the league rate.",
        ],
        question="Do NFL flags really even out, or do some teams, quarterbacks and crews get a different game?",
        seasons=lambda f: f["seasons"],
        tags=["empirical Bayes", "Wilson intervals", "split-half reliability"],
        hero=("home_edge.png", "Road team's extra flags per game, by flag type and season."),
        figs={3: [("crew_stability.png", "A crew's flags per game in one season vs the next.")],
              5: [("qb_roughing.png", "Roughing-the-passer flags drawn per 100 dropbacks, shrunk toward the league rate, with 95% intervals.")]},
        key=lambda f: [
            ("Road team's extra judgment-call flags per game, " + _eras(f)[0], f"{_era(f)[_eras(f)[0] + ',subjective']:.2f}"),
            ("Same, " + _eras(f)[-1], f"{round(_era(f)[_eras(f)[-1] + ',subjective'], 2) + 0:.2f}"),
            ("Drop in the road gap per 100 snaps, all snaps (95% interval)", f"{f['road_subj_drop_per_100_snaps_ci'][0]:.2f} ({f['road_subj_drop_per_100_snaps_ci'][1]:.2f} to {f['road_subj_drop_per_100_snaps_ci'][2]:.2f})"),
            ("Same, close game states only", f"{f['road_subj_drop_per_100_close_snaps_ci'][0]:.2f} ({f['road_subj_drop_per_100_close_snaps_ci'][1]:.2f} to {f['road_subj_drop_per_100_close_snaps_ci'][2]:.2f})"),
            ("Crew flags per game, year-to-year r", f"{f['crew_yoy_r']:.2f} ({f['crew_yoy_r_ci'][0]:.2f} to {f['crew_yoy_r_ci'][1]:.2f})"),
            ("Team net flags, odd vs even weeks r", f"{f['split_r_net']:.2f}"),
            ("Mahomes' rank in roughing flags drawn", f"#{f['rtp_mahomes'][1]} of {f['rtp_mahomes'][2]}"),
            ("Flags that swung win probability 10+ points, per season", f"{f['big_calls_per_full_season_reg']:.0f}"),
        ],
        why=[
            "**Coaching and game prep:** the road gap that is clearly left is in neutral zone infractions and delay of game. False starts split evenly, so this data does not show that a silent count is the fix. It shows where to look on road film.",
            "**Weekly opponent and crew prep:** crews have a modest style with a wide interval (see key numbers), worth one line in the game-plan packet, not a strategy.",
            "**Expectations:** a team's flag luck does not carry over, so a bad flag differential is not a reason to change personnel by itself.",
        ],
        method_eq=[
            r"Shrunk roughing rate for quarterback $i$ (beta-binomial empirical Bayes): $\hat p_i = \dfrac{x_i + \alpha}{n_i + \alpha + \beta}$, with $\alpha, \beta$ fit to all quarterbacks.",
            r"Split-half reliability: $r\big(\bar y_{\text{odd weeks}},\ \bar y_{\text{even weeks}}\big)$ across team-seasons.",
        ],
        validation=lambda f: [
            f"Stability is tested before anything is called a skill: crews {f['crew_yoy_r']:.2f}, team flags committed {f['split_r_committed']:.2f}, drawn {f['split_r_drawn']:.2f}, net {f['split_r_net']:.2f}.",
            f"Quarterback rates are shrunk and shown with Wilson 95% intervals. {f['rtp_qbs']} quarterbacks are tested at once, so about {f['rtp_expected_above_by_chance']:g} would clear the league rate by chance; {len(f['rtp_above_league_after_correction'])} clear it after a Bonferroni correction.",
            "The home-edge drop is reported per snap, in close game states, without 2020, and for every break year, with game-bootstrap intervals.",
            "Unit tests check the flag categories on a small made-up play-by-play table (`tests/`).",
        ],
        next=["Penalty-type profiles per crew (who calls holding vs pass interference).",
              "Add tracking-era context once public player tracking covers full seasons."],
        files={"home_edge_by_season.csv": "Road minus home flags per game by season and flag type",
               "home_edge_by_era.csv": "The same by era (2016-22 vs 2023 on; the break year was chosen from the chart)",
               "objective_road_skew_by_type.csv": "Share of each rule-book flag that goes against the road team",
               "crew_flags_per_game.csv": "Flags per game by referee crew and season",
               "qb_roughing_drawn.csv": "Roughing flags drawn per QB with shrunk rates and intervals",
               "big_calls_team_season.csv": "Flags that moved win probability 10+ points, by team-season"},
    ),
    "02-fourth-down-bot": dict(
        short="Fourth-Down Bot",
        tldr=lambda f: [
            f"I built a win-probability model that comes close to nflfastR out of sample (Brier {f['brier_ours']:.4f} vs {f['brier_nflfastR_vegas_wp']:.4f} on {f['wp_test_plays']:,} plays) and a fourth-down bot on top of it.",
            f"Coaches now go for it in {_pct(f['go_rate_clear_spots'][sorted(f['go_rate_clear_spots'])[-2]])} of clear go spots, up from {_pct(f['go_rate_clear_spots'][sorted(f['go_rate_clear_spots'])[0]])} in {sorted(f['go_rate_clear_spots'])[0]}. Only spots that stay go spots when the models are refit are counted.",
            f"The team card is a description, not a ranking: a team's lost win probability in odd weeks predicts its even weeks at r = {f['scorecard_split_half_r']:.2f}, and {f['scorecard_teams_clear_of_median']} of 32 teams clear the league median this season.",
        ],
        question="When the math says go for it on fourth down, how often do coaches go, and can the cost be pinned on a team?",
        seasons=lambda f: "2006-" + sorted(f["go_rate_clear_spots"])[-1],
        tags=["gradient boosting", "win probability", "decision analysis", "game bootstrap"],
        hero=("go_rate_trend.png", "Go rate when going adds 2+ win-probability points."),
        figs={1: [("wp_calibration.png", "Out-of-sample calibration of my win-probability model, 2024-25.")],
              4: [("team_scorecard.png", "Win-probability points lost per game on charged fourth-down calls, this season, with 90% intervals.")]},
        key=lambda f: [
            ("Brier score, my WP model (out of sample)", f"{f['brier_ours']:.4f}"),
            ("Brier score, nflfastR (same plays)", f"{f['brier_nflfastR_vegas_wp']:.4f}"),
            ("Agreement with nflfastR (r)", f"{f['corr_with_nflfastR']:.3f}"),
            ("Test plays", f"{f['wp_test_plays']:,}"),
            ("Go rate in clear go spots, " + sorted(f["go_rate_clear_spots"])[0], _pct(f["go_rate_clear_spots"][sorted(f["go_rate_clear_spots"])[0]])),
            ("Go rate in clear go spots, " + sorted(f["go_rate_clear_spots"])[-2], _pct(f["go_rate_clear_spots"][sorted(f["go_rate_clear_spots"])[-2]])),
            ("Median standard error of the go-vs-kick margin (WP points)", f"{f['median_go_boost_se']:.2f}"),
            ("Team card, odd vs even weeks r", f"{f['scorecard_split_half_r']:.2f}"),
            ("Team card, year-to-year r", f"{f['scorecard_yoy_r']:.2f}"),
            ("Longest field goal the bot offers", f"{f['fg_max_dist']:.0f} yards"),
        ],
        why=[
            "**Game day:** the same engine could produce a pregame go/kick chart by field position and distance for the head coach's call sheet.",
            "**Post-game review:** every fourth down graded against the best option, so the staff argues about inputs (our kicker, our short-yardage offense) rather than outcomes.",
            "**Front office:** the league-wide go rate is the solid number here. The team card is too noisy to judge a coach on one season.",
        ],
        method_eq=[
            r"$\text{WP}_{\text{go}} = P(\text{convert})\cdot \text{WP}(\text{first down}) + \big(1 - P(\text{convert})\big)\cdot \text{WP}(\text{opponent ball at the spot})$",
            r"$\text{WP}_{\text{FG}} = P(\text{make})\cdot \text{WP}(+3,\ \text{kickoff}) + \big(1 - P(\text{make})\big)\cdot \text{WP}(\text{opponent ball after a miss})$",
            r"A call is charged $\max_k \text{WP}_k - \text{WP}_{\text{call}}$ only when that gap is at least 1 point and its 5th percentile across game-bootstrap refits is above zero. Brier score $= \frac{1}{N}\sum_i (p_i - y_i)^2$.",
        ],
        validation=lambda f: [
            f"Trained on 2006-2023, tested on {f['wp_test_plays']:,} plays from 2024-25: Brier {f['brier_ours']:.4f} vs nflfastR {f['brier_nflfastR_vegas_wp']:.4f} on the same rows; r = {f['corr_with_nflfastR']:.3f}.",
            "Calibration plot under result 1: predicted vs actual win rate by bin, close to the 45-degree line.",
            f"The conversion, field-goal and punt models are refit on {f['n_boot']} resamples of games, so every recommendation carries a standard error. They are not tested out of sample.",
            f"The team card is tested for repeatability before it is read: split-half r = {f['scorecard_split_half_r']:.2f}, year-to-year r = {f['scorecard_yoy_r']:.2f}.",
            f"Football sanity checks: 4th-and-1 at midfield favors going ({f['sanity_4th1_midfield_go_boost']:+.1f} WP), 4th-and-10 at your own 20 favors kicking ({f['sanity_4th10_own20_go_boost']:+.1f}). The bot's arithmetic is unit-tested on a made-up model (`tests/test_logic.py`).",
            "Monotone constraints keep the model football-logical (a bigger lead never lowers WP).",
        ],
        next=["Team-specific inputs: the offense's short-yardage success and the kicker's range.",
              "Two-point decisions and end-of-half clock management.",
              "A one-page in-game chart per opponent."],
        files={"fourth_downs_scored.parquet": "Every fourth down with WP for go, field goal and punt, and the refit standard errors",
               "team_scorecard.csv": "WP points lost per game by team and season, with 90% intervals",
               "go_rate_when_math_says_go.csv": "Go rate in clear go spots by season, with spots and Wilson intervals",
               "costliest_calls_current_season.csv": "The current season's most expensive calls",
               "wp_calibration_2024_2025.csv": "Calibration bins for the out-of-sample test",
               "kickoff_start_by_season.csv": "Average drive start after a kickoff, used by the bot",
               "model_summary.txt": "Out-of-sample Brier scores, test plays and the field-goal range"},
    ),
    "03-sack-leverage": dict(
        short="Sack Leverage",
        tldr=lambda f: [
            f"Distance decides a sack's worth: 3rd-and-1-2 takes {f['epa_lost_per_sack']['3&1-2']:.2f} expected points, 3rd-and-11+ only {f['epa_lost_per_sack']['3&11+']:.2f}. At the same distance a third-down sack costs more than a second-down sack except at 11+ yards ({f['third_minus_second_same_distance']['11+'][0]:+.2f}, interval {f['third_minus_second_same_distance']['11+'][1]:+.2f} to {f['third_minus_second_same_distance']['11+'][2]:+.2f}).",
            f"{_pct(f['share_2nd_down_sacks_to_3rd_and_11plus'])} of 2nd-down sacks leave 3rd-and-11 or longer, and the series survives only {_pct(f['series_success_after_2nd_down_sack'])} of the time.",
            f"EPA per sack does not repeat for a rusher (year-to-year r = {f['epa_per_sack_yoy_r']:.2f}, 95% interval {f['epa_per_sack_yoy_ci'][0]:.2f} to {f['epa_per_sack_yoy_ci'][1]:.2f}), so the player board is a record of the season, not a skill rating." if not f["epa_per_sack_repeats"] else
            f"EPA per sack repeats modestly for a rusher (year-to-year r = {f['epa_per_sack_yoy_r']:.2f}).",
        ],
        question="Are all sacks equal, or does the down and distance decide how much a sack is worth?",
        seasons=lambda f: "2016-now",
        tags=["expected points", "replication", "game bootstrap", "stability test"],
        hero=("epa_per_sack.png", "Expected points taken away per sack, by down and distance, with 95% intervals."),
        figs={5: [("pass_rusher_board.png", "Expected points taken by each rusher's sacks, last full season.")]},
        key=lambda f: [
            ("Average 3rd-down sack / 2nd-down sack, EPA taken", f"{f['epa_lost_3rd_down_sack_avg']:.2f} / {f['epa_lost_2nd_down_sack_avg']:.2f}"),
            ("3rd minus 2nd down at 7-10 yards", f"{f['third_minus_second_same_distance']['7-10'][0]:+.2f} ({f['third_minus_second_same_distance']['7-10'][1]:+.2f} to {f['third_minus_second_same_distance']['7-10'][2]:+.2f})"),
            ("3rd minus 2nd down at 11+ yards", f"{f['third_minus_second_same_distance']['11+'][0]:+.2f} ({f['third_minus_second_same_distance']['11+'][1]:+.2f} to {f['third_minus_second_same_distance']['11+'][2]:+.2f})"),
            ("2nd-down sacks that leave 3rd-and-11+", _pct(f["share_2nd_down_sacks_to_3rd_and_11plus"])),
            ("Series still converted after a 2nd-down sack", _pct(f["series_success_after_2nd_down_sack"])),
            ("EPA per sack, year-to-year r (rushers)", f"{f['epa_per_sack_yoy_r']:.2f} ({f['epa_per_sack_yoy_ci'][0]:.2f} to {f['epa_per_sack_yoy_ci'][1]:.2f})"),
            ("3rd-and-1-2 conversion rate (" + f["third_down_window"] + ")", f"{f['third_down_conversion_by_distance']['1-2']}%"),
        ],
        why=[
            "**Defensive game planning:** a second-down sack ends most series because it leaves third-and-long. That is the value of the sack, not of calling pressure; whether a pressure call pays depends on what it gives up when it does not get home.",
            "**Pass-rush evaluation:** when a rusher's sacks came is not a skill that repeats, so judge him on pressures and sack counts (study 07), not on the leverage of last year's sacks.",
            "**Reviewing a season:** the board shows which sacks swung the most expected points, which is useful for telling the story of a season.",
        ],
        method_eq=[r"Value of a sack $= -\text{EPA}_{\text{play}}$ (nflfastR expected points), credited half and half on shared sacks."],
        validation=lambda f: [
            "Checked against Brett Kollmann's third-down conversion table (PFF data): "
            f"{f['third_down_conversion_by_distance']['1-2']}/{f['third_down_conversion_by_distance']['3-6']}/{f['third_down_conversion_by_distance']['7-10']}/{f['third_down_conversion_by_distance']['11+']}% here vs his 62.8/46.8/34.4/16.3.",
            f"Stability before value: EPA per sack year to year r = {f['epa_per_sack_yoy_r']:.2f} ({f['epa_per_sack_yoy_pairs']} pairs), odd vs even weeks r = {f['epa_per_sack_split_half_r']:.2f} ({f['epa_per_sack_split_half_n']} rusher-seasons).",
            "Down-and-distance intervals resample games, so sacks in the same game are not treated as independent.",
        ],
        next=["Credit pressures, not only sacks, from nflverse participation data (2023 on).",
              "Split credit between the rusher who finished and the one who forced it."],
        files={"third_down_by_distance.csv": "Third-down conversion and sack rate by distance",
               "epa_lost_per_sack.csv": "EPA taken per sack by down and distance, with 95% intervals",
               "pass_rusher_board_2025.csv": "EPA taken by each rusher's sacks, last full season (descriptive)",
               "pass_rusher_board_2026.csv": "The same for the season in progress"},
    ),
    "04-luck-index": dict(
        short="Luck Index",
        tldr=lambda f: [
            f"Fumble, field-goal and close-game luck do not repeat (year-to-year r = {f['yoy_r_fumble_luck']:.2f}, {f['yoy_r_fg_luck']:.2f}, {f['yoy_r_one_score_luck']:.2f}).",
            f"Points predict next season a little better than record (r = {f['r_next_winpct_from_pythag']:.2f} vs {f['r_next_winpct_from_winpct']:.2f}; gap {f['r_pythag_minus_r_wins'][0]:.2f}, 95% interval {f['r_pythag_minus_r_wins'][1]:.2f} to {f['r_pythag_minus_r_wins'][2]:.2f}).",
            f"A win above what points predict is worth {f['next_wins_per_luck_win'][0]:.2f} wins next year (95% interval {f['next_wins_per_luck_win'][1]:.2f} to {f['next_wins_per_luck_win'][2]:.2f}); a Pythagorean win is worth {f['next_wins_per_pythag_win'][0]:.2f}.",
        ],
        question="How many wins does chance hand out, and do lucky wins carry over to the next year?",
        seasons=lambda f: "2006-now",
        tags=["Pythagorean expectation", "regression to the mean", "year-to-year stability"],
        hero=("luck_regression.png", "Wins above points this year vs change in wins next year."),
        figs={6: [("luck_2026.png", "This season: actual wins vs what points scored and allowed predict.")]},
        key=lambda f: [
            ("Fumble-recovery luck, year-to-year r", f"{f['yoy_r_fumble_luck']:.2f}"),
            ("One-score record luck, year-to-year r", f"{f['yoy_r_one_score_luck']:.2f}"),
            ("Next-year win %: r with Pythagorean win %", f"{f['r_next_winpct_from_pythag']:.2f}"),
            ("Next-year win %: r with actual win %", f"{f['r_next_winpct_from_winpct']:.2f}"),
            ("Next-year wins per Pythagorean win", f"{f['next_wins_per_pythag_win'][0]:.2f} ({f['next_wins_per_pythag_win'][1]:.2f} to {f['next_wins_per_pythag_win'][2]:.2f})"),
            ("Next-year wins per win above Pythagorean", f"{f['next_wins_per_luck_win'][0]:.2f} ({f['next_wins_per_luck_win'][1]:.2f} to {f['next_wins_per_luck_win'][2]:.2f})"),
            ("Lucky teams vs same-record teams, next-year change", f"{f['lucky_minus_matched_wins'][0]:+.1f} wins ({f['lucky_minus_matched_wins'][1]:+.1f} to {f['lucky_minus_matched_wins'][2]:+.1f})"),
            ("Unlucky teams vs same-record teams, next-year change", f"{f['unlucky_minus_matched_wins'][0]:+.1f} wins ({f['unlucky_minus_matched_wins'][1]:+.1f} to {f['unlucky_minus_matched_wins'][2]:+.1f})"),
        ],
        why=[
            "**Front office planning:** judge a season by points, not record, before extending a coach or buying at the deadline.",
            "**Projections:** start next year's win projection from Pythagorean wins.",
            "**Communication:** a simple, honest way to tell ownership how much of a record was the bounces.",
        ],
        method_eq=[r"Pythagorean win % $= \dfrac{PF^{2.37}}{PF^{2.37} + PA^{2.37}}$",
                   r"Fumble luck $=$ fumbles recovered $- \tfrac12 \times$ all fumbles in the team's games; one-score luck $=$ one-score wins $- \tfrac12 \times$ one-score games.",
                   r"Carry-over test: $W_{t+1} = a + b\,\text{Pyth}_t + c\,(W_t - \text{Pyth}_t)$, wins per 17 games. Luck carries over only if $c > 0$."],
        validation=lambda f: [
            f"Each luck type is tested for repeatability first: fumbles r = {f['yoy_r_fumble_luck']:.2f}, field goals r = {f['yoy_r_fg_luck']:.2f}, one-score games r = {f['yoy_r_one_score_luck']:.2f}.",
            f"The fall-back is tested against teams with the same record, so regression to the mean is not counted as luck. 95% intervals resample teams {f['boot_n']:,} times.",
        ],
        next=["Add drops and dropped interceptions (FTN charting, 2022 on).",
              "A weekly luck-adjusted standings table in season."],
        files={"team_season_luck.csv": "Every team-season with each luck component",
               "luck_2026.csv": "The season in progress"},
    ),
    "05-kickoff-value": dict(
        short="Kickoff Value",
        tldr=lambda f: [
            f"The new kickoff brought returns back: {_pct(f['by_season']['2023']['return_rate'])} of kickoffs returned in 2023, {_pct(f['by_season']['2025']['return_rate'])} in 2025, and drives start {f['by_season']['2025']['avg_start_own'] - f['by_season']['2023']['avg_start_own']:.1f} yards further up.",
            f"The average return lands {abs(f['returned_vs_tb_league']):.1f} yards behind a touchback, but a returner cannot choose the touchback. Against a typical return from the same landing spot, returners cannot yet be told apart (split-half r = {f['returner_split_half_r']:.2f}).",
            f"Kickers show a small repeatable spread (split-half r = {f['kicker_split_half_r']:.2f}, about {f['kicker_signal_sd']:.3f} expected points per kick), and {f['kickers_clear']} of {f['kickers_rated']} is clear of average after shrinkage.",
        ],
        question="What did the new kickoff rule do to field position, and can kickers and returners be told apart under it?",
        seasons=lambda f: "2016-" + sorted(f["by_season"])[-1],
        tags=["rule-change analysis", "special teams", "empirical Bayes", "split-half reliability"],
        hero=("kickoff_era.png", "Return rate and drive start by season, across the 2024 and 2025 rule changes."),
        figs={4: [("returners.png", "Returners since 2025: expected points per return above a typical return from the same landing spot, with 90% intervals.")]},
        key=lambda f: [
            ("Kickoffs returned, 2023 / 2025", f"{_pct(f['by_season']['2023']['return_rate'])} / {_pct(f['by_season']['2025']['return_rate'])}"),
            ("Average drive start, 2023 to 2025", f"own {f['by_season']['2023']['avg_start_own']:.1f} to {f['by_season']['2025']['avg_start_own']:.1f}"),
            ("Average return vs a touchback (2025 on)", f"{f['returned_vs_tb_league']:+.1f} yards"),
            ("Returner value over expected, split-half r", f"{f['returner_split_half_r']:.2f} ({f['returner_split_half_n']} returners)"),
            ("Kicker EPA allowed, split-half r", f"{f['kicker_split_half_r']:.2f} ({f['kicker_split_half_n']} kickers)"),
            ("Kickers / returners clear of average", f"{f['kickers_clear']} of {f['kickers_rated']} / {f['returners_clear']} of {f['returners_rated']} (about {f['returners_clear_expected_by_chance']:.0f} expected by chance)"),
        ],
        why=[
            "**Roster spots:** two seasons of the new rule do not yet separate one returner from another, so do not pay or cut on a return average alone.",
            "**Kicker evaluation:** kickoff placement shows a small repeatable effect; track it next to field goals, with its interval.",
            "**Special-teams scheme:** the value of a return by landing spot says where a kick is cheapest to give up.",
        ],
        method_eq=[r"Return value over expected $= 	ext{EPA}_{	ext{kickoff}} - \widehat{E}[	ext{EPA} \mid 	ext{landing spot}]$, receiving team's side, touchdowns and fumbles included.",
                   r"Shrunk estimate $= \dfrac{\sigma^2_{	ext{true}}}{\sigma^2_{	ext{true}} + \sigma^2_{	ext{play}}/n}\,ar{x}$."],
        validation=lambda f: [
            f"Stability before value: split-half r = {f['returner_split_half_r']:.2f} for returners and {f['kicker_split_half_r']:.2f} for kickers, so neither board is published as a ranking.",
            f"Return touchdowns ({f['return_tds_kept']}) and lost fumbles ({f['return_fumbles_lost_kept']}) are in the player sample; {f['onside_squib_dropped']} onside kicks, squibs and kicking-team recoveries are out.",
            "The rule-year touchback spot is set for every season, and the code stops if a season has none.",
        ],
        next=["Separate the kick from the coverage unit with tracking data or coverage-unit fixed effects.",
              "Re-run when the current rule has three full seasons."],
        files={"kickoffs_by_season.csv": "Kickoffs, touchback and return rates, drive start and EP by season",
               "return_value_by_landing_spot.csv": "What a return is worth by where the ball came down",
               "kickers_2025_on.csv": "Kickers since 2025: EPA allowed per kickoff vs average, raw and shrunk, with intervals",
               "returners_2025_on.csv": "Returners since 2025: EPA per return over expected, with intervals"},
    ),
    "06-pass-run": dict(
        short="Pass vs Run",
        tldr=lambda f: [
            f"Passing beat running on neutral early downs in {f['seasons_pass_better']} of {f['seasons_total']} seasons.",
            f"Teams moved slowly: early-down pass rate {_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[0]])} to {_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[-2]])}.",
            f"At team level, passing more than expected goes with better efficiency at r = {f['team_corr_pooled'][0]:.2f} (95% interval {f['team_corr_pooled'][1]:.2f} to {f['team_corr_pooled'][2]:.2f}, {f['team_seasons_pooled']} team-seasons). It is a correlation, not proof a team should pass more.",
        ],
        question="Passing has been more efficient for years. So why do teams still run, and does passing more make a team better?",
        seasons=lambda f: sorted(f["epa_gap_by_season"])[0] + "-" + sorted(f["epa_gap_by_season"])[-1],
        tags=["EPA", "pass rate over expected", "team bootstrap"],
        hero=("epa_pass_vs_run.png", "EPA per play on neutral early downs: dropbacks vs designed runs, by season."),
        figs={3: [("proe_vs_epa.png", "Team pass rate over expected vs EPA per play, every team-season, last full season labeled.")]},
        key=lambda f: [
            ("Seasons passing beat running (neutral early downs)", f"{f['seasons_pass_better']} of {f['seasons_total']}"),
            ("EPA per play gap, last full season", f"{f['epa_gap_by_season'][sorted(f['epa_gap_by_season'])[-2]]:.2f}"),
            ("Pass rate, first to last full season", f"{_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[0]])} to {_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[-2]])}"),
            ("Team pass rate over expected vs EPA, all team-seasons (r)", f"{f['team_corr_pooled'][0]:.2f} ({f['team_corr_pooled'][1]:.2f} to {f['team_corr_pooled'][2]:.2f})"),
            ("Same team, change vs change (r)", f"{f['within_team_change_corr'][0]:.2f} ({f['within_team_change_corr'][1]:.2f} to {f['within_team_change_corr'][2]:.2f})"),
            ("Last full season alone (r)", f"{f['team_corr_proe_epa_last_full']:.2f} ({f['team_corr_last_full_ci'][0]:.2f} to {f['team_corr_last_full_ci'][1]:.2f})"),
        ],
        why=[
            "**Offensive tendencies:** the league-wide edge for passing on early downs shows up in every season.",
            "**Team-specific calls:** teams that pass more than expected are a little more efficient, but good passing teams choose to pass, so the answer for one team is a personnel question, not a league average.",
            "**Opponent scouting:** pass rate over expected is a clean tendency number for the weekly packet.",
        ],
        method_eq=[r"Pass rate over expected (PROE) $=$ actual dropback rate $- \overline{\text{xpass}}$, where xpass is nflfastR's dropback probability given the situation."],
        validation=lambda f: [
            f"The pass edge holds in {f['seasons_pass_better']} of {f['seasons_total']} seasons, and its 95% interval is above zero in {f['seasons_gap_interval_above_zero']}.",
            f"The team-level link is tested on {f['team_seasons_pooled']} team-seasons and within teams, not on one season of 32 teams.",
            "Dropbacks include sacks and scrambles, so passing is charged its true cost.",
        ],
        next=["Sequencing: does an early run set up play action later (FTN charting, 2022 on)?",
              "Second-down run tendencies by personnel."],
        files={"neutral_early_downs_by_season.csv": "Plays, EPA, success rate and pass rate by season",
               "team_proe_vs_epa.csv": "Team PROE and EPA per play, every team-season"},
    ),
    "07-box-score-tax": dict(
        headline=1,
        short="The Box-Score Tax",
        tldr=lambda f: [
            f"Pressures repeat (r = {f['yoy_r_pressure_rate']:.2f}); sacks bounce (r = {f['yoy_r_sack_rate']:.2f}); sacks beyond what pressures predict barely repeat (r = {f['yoy_r_sack_luck']:.2f}).",
            f"A sack beyond what pressures predict adds about ${f['musd_per_lucky_sack_2026']:.2f}M a year to a veteran contract ({f['market_contracts']} contracts, 95% CI ${f['musd_per_lucky_sack_ci'][0]:.2f}-{f['musd_per_lucky_sack_ci'][1]:.2f}M) and predicts {f['future_sacks_per_lucky_sack']:.2f} extra sacks the next year.",
            f"Priced against a pressure, that is {f['tax_ratio']:.2f} times what it predicts (90% interval {f['tax_ratio_ci90'][0]:.2f} to {f['tax_ratio_ci90'][1]:.2f}; 95% interval {f['tax_ratio_ci95'][0]:.2f} to {f['tax_ratio_ci95'][1]:.2f}). " + ("The 95% interval excludes 1." if f['tax_ratio_ci95'][0] > 1 else "Suggestive of overpaying; the 95% interval includes 1, so it is not settled."),
        ],
        question="Do NFL teams pay pass rushers more for sacks than sacks predict, when pressures predict future sacks better?",
        seasons=lambda f: f["seasons"],
        tags=["clustered OLS", "player bootstrap", "contract valuation", "market pricing"],
        hero=("sack_tax.png", "Cost of one expected future sack bought through sack luck vs through pressures, with 90% bootstrap intervals."),
        figs={1: [("rush_stability.png", "Year-to-year stability: pressure rate vs sack rate.")],
              5: [("buy_low_rushers.png", "Sacks vs what pressures predict, last full season.")],
              8: [("coverage_stability.png", "Coverage stats: how much each one repeats.")]},
        key=lambda f: [
            ("Pressure rate, year-to-year r", f"{f['yoy_r_pressure_rate']:.2f}"),
            ("Sack rate, year-to-year r", f"{f['yoy_r_sack_rate']:.2f}"),
            ("Sack luck, year-to-year r", f"{f['yoy_r_sack_luck']:.2f}"),
            ("Sacks per pressure: edge / interior", f"{f['sacks_per_pressure_by_group']['edge']:.3f} / {f['sacks_per_pressure_by_group']['interior']:.3f}"),
            ("Paid per lucky sack, per year (2026 dollars)", f"${f['musd_per_lucky_sack_2026']:.2f}M (95% CI ${f['musd_per_lucky_sack_ci'][0]:.2f}-{f['musd_per_lucky_sack_ci'][1]:.2f}M)"),
            ("Next-year sacks per lucky sack", f"{f['future_sacks_per_lucky_sack']:.2f} (95% CI {f['future_sacks_per_lucky_sack_ci'][0]:.2f} to {f['future_sacks_per_lucky_sack_ci'][1]:.2f})"),
            ("Test ratio: relative price / relative prediction (1 = fair)", f"{f['tax_ratio']:.2f} (90% {f['tax_ratio_ci90'][0]:.2f}-{f['tax_ratio_ci90'][1]:.2f}; 95% {f['tax_ratio_ci95'][0]:.2f}-{f['tax_ratio_ci95'][1]:.2f})"),
            (f"Price per lucky sack, deals signed {f['recent_deals_label']}", f"${f['recent_deals_price'][0]:.2f}M (95% CI {f['recent_deals_price'][1]:.2f} to {f['recent_deals_price'][2]:.2f})"),
            ("Contracts / players", f"{f['market_contracts']} / {f['market_players']}"),
        ],
        why=[
            "**Free agency:** read a sack total next to the pressure total. The gap between them is the part of the platform year least likely to come back.",
            "**Negotiation:** the evidence that the market overpays for that gap is suggestive, not settled, so it is a reason to hold a line on price, not a rule.",
            "**Pro scouting:** pair the film with the pressure-to-sack gap to separate a finisher from a hot year.",
        ],
        method_eq=[
            r"$\text{sack luck}_i = \text{sacks}_i - c_g \cdot \text{pressures}_i$, where $c_g$ is the sacks-per-pressure rate of the player's group, edge or interior (see key numbers).",
            r"Price: $\dfrac{\text{APY}_i}{\text{cap}_t} = \beta_0 + \beta_1\,\text{pressures}_i + \beta_2\,\text{sack luck}_i + \beta_3\,\text{snaps}_i + \text{controls}_i + \varepsilon_i$, standard errors clustered by player. Controls: age, age squared, prior-season pressures and sacks.",
            r"Prediction: $\text{sacks}_{i,t+1} = \gamma_0 + \gamma_1\,\text{pressures}_{i,t} + \gamma_2\,\text{sack luck}_{i,t} + \gamma_3\,\text{snaps}_{i,t} + \text{controls}_{i,t} + u_{i,t}$.",
            r"Test: $T = \dfrac{\beta_2 / \beta_1}{\gamma_2 / \gamma_1}$. $T = 1$ means a lucky sack is priced in line with what it predicts.",
        ],
        validation=lambda f: [
            f"The test statistic was fixed before the run: relative price over relative prediction, players resampled {f['tax_ratio_boot_n']:,} times. It is above 1 in {100 * f['tax_ratio_share_above_1']:.0f}% of samples.",
            f"{f['robust_n']} versions of the price model (with and without age and prior-season controls, edge or interior only, multi-year deals, deals over 1% of the cap, earlier and recent deals): ${f['robust_min']:.2f}M to ${f['robust_max']:.2f}M per lucky sack; {f['robust_ci_above_zero']} of {f['robust_n']} intervals exclude zero.",
            f"One deal per player-year. Before that fix the sample double-counted tags and extensions signed in the same year.",
            "The same idea was tested on coverage stats and rejected (finding 8).",
        ],
        next=["Repeat with a second charting source (NGS or PFF pressures).",
              "Price guarantees and three-year cash, not only average per year.",
              "Add run-defense value so the contract model credits the whole player."],
        files={"rusher_contracts_with_platform.csv": "Each veteran ED/IDL contract with the platform season's stats",
               "rusher_sack_luck_board.csv": "Every rusher-season: sacks, pressures, expected sacks, sack luck",
               "free_agents_2027_rushers.csv": "2027 free-agent rushers with pressure rate and sack luck",
               "robustness_lucky_sack_price.csv": "Price per lucky sack under eight model versions",
               "models.txt": "Full regression output"},
    ),
    "08-yac-tax": dict(
        headline=1,
        short="The YAC Tax",
        tldr=lambda f: [
            f"YAC over expected is noisy per catch (r = {f['yoy_r']['avg_yac_above_expectation']:.2f}), but a season of it predicts next year like air yards ({f['predict_next_yards_per_yard']['yacoe_yds']:.2f} vs {f['predict_next_yards_per_yard']['air_yds']:.2f} yards per yard).",
            f"No YAC tax detected: ${f['musd_per_100_future_yards']['yacoe_yds']:.2f}M per 100 future yards bought through YAC over expected vs ${f['musd_per_100_future_yards']['air_yds']:.2f}M through air yards ({f['market_contracts']} veteran WR/TE contracts).",
            f"The test has low power: the price-to-prediction ratio is {f['tax_ratio']:.2f} with a 90% interval of {f['tax_ratio_ci90'][0]:.2f} to {f['tax_ratio_ci90'][1]:.2f}, so it cannot rule out a tax or a discount of about 2x.",
        ],
        question="Do teams pay receivers for yards after the catch that won't come back?",
        seasons=lambda f: f["seasons"],
        tags=["Next Gen Stats", "clustered OLS", "player bootstrap", "null result"],
        hero=("yac_tax.png", "Price per 100 future yards for each part of a receiver's production."),
        figs={1: [("receiver_stability.png", "Year-to-year stability of receiving traits.")]},
        key=lambda f: [
            ("YAC over expected per catch, year-to-year r", f"{f['yoy_r']['avg_yac_above_expectation']:.2f}"),
            ("Next-year yards per yard: YAC over expected", f"{f['predict_next_yards_per_yard']['yacoe_yds']:.2f}"),
            ("Next-year yards per yard: air yards", f"{f['predict_next_yards_per_yard']['air_yds']:.2f}"),
            ("Price per 100 future yards: YACOE / air / expected YAC", f"${f['musd_per_100_future_yards']['yacoe_yds']:.2f}M / ${f['musd_per_100_future_yards']['air_yds']:.2f}M / ${f['musd_per_100_future_yards']['xyac_yds']:.2f}M"),
            ("Test ratio: relative price / relative prediction (1 = fair)", f"{f['tax_ratio']:.2f} (90% {f['tax_ratio_ci90'][0]:.2f}-{f['tax_ratio_ci90'][1]:.2f})"),
            ("Contracts / players", f"{f['market_contracts']} / {f['market_players']}"),
        ],
        why=[
            "**Receiver evaluation:** don't discount a receiver's YAC as luck by default; a season of it predicts next year like air yards do.",
            "**Where to look for edges:** no mispricing shows up here, but the sample is too small to call the receiver market efficient.",
            "**Free agency:** the free-agent receiver list shows who leaned on YAC, as a reason to check the film, not to pass.",
        ],
        method_eq=[r"Receiving yards $=$ air yards on catches $+$ expected YAC $+$ YAC over expected (NGS), so the three parts add to the total.",
                   r"Price and prediction models regress APY share of the cap, and next-season yards, on the three parts plus targets, with standard errors clustered by player."],
        validation=lambda f: [
            f"{len(f['robustness']) - 1} robustness versions (WR only, TE only, multi-year deals, deals over 1% of the cap, 2023-2026 deals) recompute the price per 100 yards (not per future yard). YAC over expected is priced at or above air yards in {sum(r['yacoe_yds_musd_per_100'] >= r['air_yds_musd_per_100'] for r in f['robustness'][1:])} of them.",
            f"95% interval for next-year yards per YACOE yard: {f['predict_ci']['yacoe_yds'][0]:.2f}-{f['predict_ci']['yacoe_yds'][1]:.2f}, overlapping air yards.",
            f"A null result is reported as one, with its power: the ratio is above 1 in {100 * f['tax_ratio_share_above_1']:.0f}% of {f['tax_ratio_boot_n']:,} bootstrap samples.",
        ],
        next=["Route-level separation once public route data allows it.", "Tight ends below the NGS qualifying line."],
        files={"receivers_2025.csv": "Last full season: each receiver's yards split three ways",
               "free_agents_2027_receivers.csv": "2027 free-agent receivers",
               "robustness_price_per_100_yards.csv": "Price per 100 yards under each model version",
               "models.txt": "Full regression output"},
    ),
    "09-run-game-value": dict(
        headline=1,
        short="Run Game Value",
        tldr=lambda f: [
            f"The blocking part of yards per carry repeats more than the back's part (expected YPC r = {f['yoy_r']['xypc']:.2f} vs RYOE per carry r = {f['yoy_r']['ryoe_pc']:.2f}; {f['yoy_r_150car']['xypc']:.2f} vs {f['yoy_r_150car']['ryoe_pc']:.2f} for 150+ carry backs), and no rushing stat predicts next season's rushing EPA well.",
            f"Inconclusive on {f['market_contracts']} contracts: I expected teams to pay blocked yards like the back's own, and the data neither shows that nor rules it out. Holding carries fixed, +1 yard over expected per carry adds ${f['musd_per_ypc_part']['ryoe_pc']:.2f}M a year vs ${f['musd_per_ypc_part']['xypc']:.2f}M for +1 expected yard per carry ({f['market_contracts']} contracts); per yard the gap is {f['price_ratio_ryoe_to_expected_yard']:.2f}x but fades to {f['robust_ratio']['plus platform carries']:.2f}x with workload controlled.",
            f"Per carry, both parts predict next season about equally (+1 yard per carry of each adds {f['predict_next_ypc_per']['ryoe_pc']:.2f} vs {f['predict_next_ypc_per']['xypc']:.2f} to next season's yards per carry), so I found no mispricing, though a per-carry price gap under about ${f['price_per_carry_min_detectable_musd']:.1f}M would be too small for this sample to detect; includes the {f['fa_class']} free-agent backs, every name news-checked.",
        ],
        question="How much of a running back's production is his, and do contracts pay for that part?",
        seasons=lambda f: f"{f['seasons'].split('-')[0]}-{f['current_season']}",
        tags=["Next Gen Stats", "clustered OLS", "bootstrap", "contract valuation", "null result"],
        hero=("rb_price.png", "What contracts pay for each part of yards per carry, and what each part predicts next season."),
        figs={1: [("stability.png", "Year-to-year stability of rushing stats, with 95% intervals.")],
              2: [("team_changers.png", "Stability for backs who stayed vs backs who changed teams.")],
              3: [("predict_epa.png", "What predicts next season's rushing EPA per carry.")],
              6: [("free_agent_rbs.png", "The 2027 free-agent backs by rush yards over expected per carry.")]},
        key=lambda f: [
            ("Expected yards per carry, year-to-year r", f"{f['yoy_r']['xypc']:.2f}"),
            ("RYOE per carry, year-to-year r (150+ carry backs)", f"{f['yoy_r']['ryoe_pc']:.2f} ({f['yoy_r_150car']['ryoe_pc']:.2f})"),
            ("Raw yards per carry, year-to-year r", f"{f['yoy_r']['ypc']:.2f}"),
            ("Best r with next-season EPA per carry", f"{max(f['r_next_epa'].values()):.2f}"),
            ("Paid per 100 yards: over expected / expected (2026 dollars)", f"${f['musd_per_100_yards']['ryoe_yds']:.2f}M / ${f['musd_per_100_yards']['x_yds']:.2f}M"),
            ("Next-season YPC per +1 YPC: over expected / expected", f"{f['predict_next_ypc_per']['ryoe_pc']:.2f} / {f['predict_next_ypc_per']['xypc']:.2f}"),
            ("Back-to-back pairs (backs) / contracts (backs)", f"{f['pairs']} ({f['pair_players']}) / {f['market_contracts']} ({f['market_players']})"),
        ],
        why=[
            "**Free agency:** split a back's yards per carry before paying for it; about half of what repeats is the expected part, which depends on the line, the box and his role.",
            "**Contract talks:** the market pays for yards per carry, not workload; a big carry total is not worth paying for in itself.",
            "**Expectations:** rushing EPA per carry barely carries over for any back, so a contract should not assume last year's efficiency comes back.",
        ],
        method_eq=[
            r"Yards per carry $=$ expected yards per carry $+$ RYOE per carry (NGS), so the two parts add to the total.",
            r"Price: $\dfrac{\text{APY}_i}{\text{cap}_t} = \beta_0 + \beta_1\,\text{expected yds}_i + \beta_2\,\text{RYOE}_i + \beta_3\,\text{rush TD}_i + \beta_4\,\text{rec yds}_i + \varepsilon_i$, standard errors clustered by player.",
            r"Prediction per carry: $\text{YPC}_{i,t+1} = \gamma_0 + \gamma_1\,\text{xYPC}_{i,t} + \gamma_2\,\text{RYOE per carry}_{i,t} + u_{i,t}$, weighted by next-season carries.",
        ],
        validation=lambda f: [
            f"{f['robust_n']} versions of the price model (age controls, deals over 1% of the cap, multi-year deals, 2019-2022 and 2023-2026 deals, no receiving control, plus platform carries, NGS's own expected-yards column): yards over expected are paid {f['robust_ratio_min']:.2f} to {f['robust_ratio_max']:.2f} times as much as expected yards; the difference is significant (p < 0.05) in {f['robust_diff_significant']} of {f['robust_n']}. Weak versions are in the table, not hidden.",
            f"Every year-to-year r carries a 95% interval from 1,000 bootstrap samples that resample backs. Weighting pairs by carries: expected YPC {f['yoy_r_carry_weighted']['xypc']:.2f}, RYOE per carry {f['yoy_r_carry_weighted']['ryoe_pc']:.2f}.",
            f"A bigger-sample check on raw yards per carry (every back with 100+ carries in back-to-back seasons, {f['pbp_100car_pairs']} pairs): r = {f['pbp_100car_yoy_r_ypc']:.2f}.",
            f"Adding platform carries to the season-yards prediction leaves a yard over expected at {f['predict_plus_carries_per']['ryoe_yds']:.2f} future yards and an expected yard at {f['predict_plus_carries_per']['x_yds']:.2f} (interval {f['predict_plus_carries_ci']['x_yds'][0]:.2f} to {f['predict_plus_carries_ci']['x_yds'][1]:.2f}).",
            "An independent review re-ran the study, checked every number against findings.json and news-checked the main free-agent list; its corrections (a team-change coding bug, duplicate same-year contracts, an over-read workload model) are in this version.",
        ],
        next=["Separate line play from the back with blocking data (run-block win rates) once public.",
              "Add pass protection and receiving value per snap so the contract model credits the whole back.",
              "Rookie-contract backs: what a draft pick at RB buys compared with a veteran at the same price."],
        files={"back_to_back_seasons.csv": "Each back's stats in back-to-back qualified seasons, with team changes",
               "rb_contracts_with_platform.csv": "Each veteran RB contract with the platform season's NGS split",
               "robustness_price_per_100_yards.csv": "Price per 100 yards and the p-value of the difference under nine model versions",
               "free_agents_2027_rbs.csv": "2027 free-agent backs: RYOE, shrunk RYOE, expected YPC, value flag, news note",
               "free_agents_2027_rbs_no_ngs.csv": "2027 free-agent backs with 100+ carries but under 100 in NGS season rows, with news notes",
               "models.txt": "Full regression output"},
    ),
    "13-metric-stability-atlas": dict(
        short="Metric Stability Atlas",
        tldr=lambda f: [
            f"Offense numbers settle faster than defense numbers: offense EPA per play is half signal after {f['atlas']['off_epa']['k_games']:.1f} games (95% interval {f['atlas']['off_epa']['k_games_ci'][0]:.1f} to {f['atlas']['off_epa']['k_games_ci'][1]:.1f}), defense EPA per play after {f['atlas']['def_epa']['k_games']:.1f} ({f['atlas']['def_epa']['k_games_ci'][0]:.1f} to {f['atlas']['def_epa']['k_games_ci'][1]:.1f}), and {len(f['team_no_majority_by_17'])} of {sum(r['group'] in ('Offense', 'Defense', 'Special teams', 'Team') for r in f['atlas'].values())} team numbers are still less than half signal after a full season.",
            (f"After 8 games, no metric beats point differential at predicting the rest of the season; net EPA per play ties it (r = {f['predict_rest']['res_point_diff']['r_rest_pd']:.2f} vs {f['predict_rest']['net_epa']['r_rest_pd']:.2f}, {f['predict_rest']['_n']} team-seasons), and out of sample it lifts R² only from {f['predict_rest']['_oos_r2_pd_alone']:.3f} to {f['predict_rest']['_oos_r2_pd_epa']:.3f}."
             if not f["predict_beats_pd"] else
             f"After 8 games, {len(f['predict_beats_pd'])} metric(s) beat point differential at predicting the rest of the season ({f['predict_rest']['_n']} team-seasons)."),
            f"A defense's pressure rate is half signal after {f['atlas']['def_pressure_rate']['k_games']:.1f} games, its sack rate after {f['atlas']['def_sack_rate']['k_games']:.1f}; target share settles in {f['atlas']['wr_tgt_share']['k_games']:.1f} games, receiver and rusher efficiency in more than a season. Regressing by these rules beat the raw number out of sample for {f['oos_shrunk_beats_raw']} of {f['oos_metrics']} metrics.",
        ],
        question="Which team and player numbers can a club trust, and after how many games?",
        seasons=lambda f: f"{f['seasons'].split('-')[0]}-{f['current_season']}",
        tags=["split-half reliability", "regression to the mean", "year-to-year stability", "out-of-sample test", "team bootstrap"],
        hero=("team_atlas.png", "Games until each team number is half signal, with 95% intervals (resampling teams)."),
        figs={3: [("player_atlas.png", "Games of a typical qualified player's volume until each player number is half signal, with 95% intervals.")],
              4: [("within_vs_across.png", "Within-season reliability of a full season against year-to-year r, one dot per metric.")],
              5: [("predict_rest.png", "First 8 games of each team number against point differential per game over the rest of the season."),
                  ("week_curve.png", "How well each number through game N predicts point differential over the rest of the season.")],
              7: [("oos_check.png", "Out of sample: the reliability each metric's k predicts against the slope seen in later seasons.")]},
        tables=lambda f: {2: ["**The team atlas, most to least reliable over a full season.** Regress = how far to pull the number toward the league mean after 4, 8 and 17 games of typical volume.", atlas_table(f, team=True)],
                          3: ["**The player atlas.** Games are a typical qualified player's volume per game.", atlas_table(f, team=False)]},
        key=lambda f: [
            ("Offense EPA/play: games to half signal (95% interval)", f"{f['atlas']['off_epa']['k_games']:.1f} ({f['atlas']['off_epa']['k_games_ci'][0]:.1f} to {f['atlas']['off_epa']['k_games_ci'][1]:.1f})"),
            ("Defense EPA/play allowed: games to half signal", f"{f['atlas']['def_epa']['k_games']:.1f} ({f['atlas']['def_epa']['k_games_ci'][0]:.1f} to {f['atlas']['def_epa']['k_games_ci'][1]:.1f})"),
            ("Offense more reliable than defense, matched pairs", f"{f['off_more_reliable_pairs']} of {len(f['off_vs_def_pairs'])}"),
            ("Defense pressure rate / sack rate: games to half signal", f"{f['atlas']['def_pressure_rate']['k_games']:.1f} / {f['atlas']['def_sack_rate']['k_games']:.1f}"),
            ("Team numbers under half signal after 17 games", f"{len(f['team_no_majority_by_17'])} of {sum(r['group'] in ('Offense', 'Defense', 'Special teams', 'Team') for r in f['atlas'].values())}"),
            ("After 8 games, r with rest-of-season point differential: point differential / net EPA", f"{f['predict_rest']['res_point_diff']['r_rest_pd']:.2f} / {f['predict_rest']['net_epa']['r_rest_pd']:.2f}"),
            ("QB Weeks 1-9 to Weeks 10+ EPA/dropback: r from EPA / from CPOE", f"{f['qb_predict']['qb_epa']['r']:.2f} / {f['qb_predict']['qb_cpoe']['r']:.2f}"),
            ("Regressed beats raw out of sample", f"{f['oos_shrunk_beats_raw']} of {f['oos_metrics']} metrics"),
        ],
        why=[
            "**Self-scouting and game planning:** by Week 5 or 6 an offense's EPA, success rate and pass rate over expected are mostly signal; a defense's are not until late in the season, so a staff should not rebuild a defensive plan on four games.",
            "**Pro personnel, the trade deadline and free agency:** a receiver's target share and a pass rusher's pressure rate are trustworthy after a few games; a receiver's or back's per-touch efficiency is not, even after a full season, so regress it hard (the atlas says how far) before paying for it.",
            "**Front office and ownership:** at midseason, point differential and net EPA per play are the honest read of a team; turnovers forced, fumble recoveries, red-zone and field-goal rates are mostly noise and should not drive personnel moves.",
            "**Analytics staff:** every weekly board can carry the regression constant from this atlas, so a hot month is shown next to what it is likely to be worth. The rule was tested out of sample before it is offered.",
        ],
        method_eq=[
            r"Reliability of $n$ trials: $\rho(n) = \dfrac{n}{n + k}$; from a split-half $r$ on halves of $n_h$ trials, $k = n_h \dfrac{1 - r}{r}$.",
            r"Regressed estimate: $\hat\theta = \mu + \dfrac{n}{n + k}\,(x - \mu)$, so after $n$ trials regress $\dfrac{k}{n + k}$ of the way to the league mean $\mu$.",
            r"Spearman-Brown: doubling a half gives $\rho_{\text{full}} = \dfrac{2r}{1 + r}$, the same as $\rho(2n_h)$ above.",
        ],
        validation=lambda f: [
            f"Random game splits ({f['n_splits']} per metric) and the odd vs even week split agree: the mean gap in r is {f['odd_even_vs_random_mean_abs_gap']:.3f} across the {len(f['atlas'])} metrics.",
            f"Out of sample: k fit on the earlier seasons, tested by forecasting even weeks from odd weeks in the later ones. Regressed beat raw for {f['oos_shrunk_beats_raw']} of {f['oos_metrics']} metrics and the league mean for {f['oos_shrunk_beats_mean']}; predicted reliability vs observed slope r = {f['oos_calibration_r']:.2f}.",
            f"Team prediction is fit on {f['predict_rest']['_train']} and scored on {f['predict_rest']['_test']}; quarterback prediction the same. Out-of-sample R² is reported next to every in-sample r.",
            f"Every r carries a 95% interval that resamples whole teams or players ({f['boot_split']} draws for split-half r, {f['boot_r']:,} for the rest). Seasons are centred before any correlation, so league trends are not counted as signal.",
            "Logic tests on made-up data (`tests/test_stability_atlas.py`) check that the split-half engine recovers a known reliability, that k turns into the right regression share, that splits keep each unit's games whole, that season centring removes a pure trend, and that the out-of-sample test prefers the regressed forecast when the truth is noisy.",
        ],
        next=["Per-pass-rush-snap pressure and yards per route run, if public route and rush counts appear.",
              "Opponent-adjusted versions of the team numbers, to see how much of the defense noise is schedule.",
              "A weekly in-season projection that blends last season (weighted by year-to-year r) with this season (weighted by k)."],
        files={"atlas.csv": "Every metric: split-half r with interval, odd/even r, k in trials and games, regression shares, year-to-year r, out-of-sample check",
               "regression_guide.csv": "k and how far to regress after 4, 8 and 17 games, per metric",
               "predict_rest_of_season.csv": "First-8-game team numbers vs rest-of-season point differential and win %, with out-of-sample R² and next-season r",
               "teams_<season>_regressed.csv": "The season in progress: raw and regressed offense, defense and net EPA per play and point differential, by team"},
    ),
}
