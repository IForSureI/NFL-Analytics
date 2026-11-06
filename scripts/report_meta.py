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


META = {
    "01-flag-audit": dict(
        short="Flag Audit",
        tldr=lambda f: [
            f"Road teams drew {_era(f)[_eras(f)[0] + ',subjective']:.2f} more judgment-call flags a game than home teams in {_eras(f)[0]}; since 2023 the gap has averaged {_era(f)[_eras(f)[-1] + ',subjective']:.2f}. What remains is a small pre-snap gap (neutral zone infractions, delay of game), not judgment calls.",
            f"Referee crews have a modest, real style (year-to-year r = {f['crew_yoy_r']:.2f}); a team's flag luck does not carry over (r = {f['split_r_net']:.2f}).",
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
            ("Same, " + _eras(f)[-1], f"{_era(f)[_eras(f)[-1] + ',subjective']:.2f}"),
            ("Crew flags per game, year-to-year r", f"{f['crew_yoy_r']:.2f}"),
            ("Team net flags, odd vs even weeks r", f"{f['split_r_net']:.2f}"),
            ("Mahomes' rank in roughing flags drawn", f"#{f['rtp_mahomes'][1]} of {f['rtp_mahomes'][2]}"),
            ("Flags that swung win probability 10+ points, per season", f"{f['big_calls_per_full_season_reg']:.0f}"),
        ],
        why=[
            "**Coaching and game prep:** the road penalty gap that is left is pre-snap communication (neutral zone infractions, delay of game), which is coachable with silent-count and cadence work in road weeks.",
            "**Weekly opponent and crew prep:** crews have a modest, repeatable style (see key numbers), worth one line in the game-plan packet, not a strategy.",
            "**Expectations:** a team's flag luck does not carry over, so a bad flag differential is not a reason to change personnel by itself.",
        ],
        method_eq=[
            r"Shrunk roughing rate for quarterback $i$ (beta-binomial empirical Bayes): $\hat p_i = \dfrac{x_i + \alpha}{n_i + \alpha + \beta}$, with $\alpha, \beta$ fit to all quarterbacks.",
            r"Split-half reliability: $r\big(\bar y_{\text{odd weeks}},\ \bar y_{\text{even weeks}}\big)$ across team-seasons.",
        ],
        validation=lambda f: [
            f"Stability is tested before anything is called a skill: crews {f['crew_yoy_r']:.2f}, team flags committed {f['split_r_committed']:.2f}, drawn {f['split_r_drawn']:.2f}, net {f['split_r_net']:.2f}.",
            "Quarterback rates are shrunk and shown with Wilson 95% intervals, so small samples are not ranked on noise.",
            "Unit tests check the flag categories and that the published stability numbers stay in sane ranges (`tests/`).",
        ],
        next=["Penalty-type profiles per crew (who calls holding vs pass interference).",
              "Add tracking-era context once public player tracking covers full seasons."],
        files={"home_edge_by_season.csv": "Road minus home flags per game by season and flag type",
               "home_edge_by_era.csv": "The same by era (2016-22 vs 2023 on)",
               "objective_road_skew_by_type.csv": "Share of each rule-book flag that goes against the road team",
               "crew_flags_per_game.csv": "Flags per game by referee crew and season",
               "qb_roughing_drawn.csv": "Roughing flags drawn per QB with shrunk rates and intervals",
               "big_calls_team_season.csv": "Flags that moved win probability 10+ points, by team-season"},
    ),
    "02-fourth-down-bot": dict(
        short="Fourth-Down Bot",
        tldr=lambda f: [
            f"I built a win-probability model that matches nflfastR out of sample (Brier {f['brier_ours']:.4f} vs {f['brier_nflfastR_vegas_wp']:.4f} on {f['wp_test_plays']:,} plays) and a fourth-down bot on top of it.",
            f"Coaches now go for it in {_pct(f['go_rate_clear_spots'][sorted(f['go_rate_clear_spots'])[-2]])} of clear go spots, up from {_pct(f['go_rate_clear_spots'][sorted(f['go_rate_clear_spots'])[0]])} in {sorted(f['go_rate_clear_spots'])[0]}; there is still win probability left on the table.",
            f"{f['scorecard_season']} report card: {f['most_costly'][0][0]} has lost the most per game on clear calls, {f['least_costly'][-1][0]} the least.",
        ],
        question="When the math says go for it on fourth down, how often do coaches go, and which teams leave the most win probability on the table?",
        seasons=lambda f: "2006-" + sorted(f["go_rate_clear_spots"])[-1],
        tags=["gradient boosting", "win probability", "decision analysis", "calibration"],
        hero=("go_rate_trend.png", "Go rate when going adds 2+ win-probability points."),
        figs={1: [("wp_calibration.png", "Out-of-sample calibration of my win-probability model, 2024-25.")],
              3: [("team_scorecard.png", "Win-probability points lost per game on clear fourth-down calls, this season.")]},
        key=lambda f: [
            ("Brier score, my WP model (out of sample)", f"{f['brier_ours']:.4f}"),
            ("Brier score, nflfastR (same plays)", f"{f['brier_nflfastR_vegas_wp']:.4f}"),
            ("Agreement with nflfastR (r)", f"{f['corr_with_nflfastR']:.3f}"),
            ("Test plays", f"{f['wp_test_plays']:,}"),
            ("Go rate in clear go spots, " + sorted(f["go_rate_clear_spots"])[0], _pct(f["go_rate_clear_spots"][sorted(f["go_rate_clear_spots"])[0]])),
            ("Go rate in clear go spots, " + sorted(f["go_rate_clear_spots"])[-2], _pct(f["go_rate_clear_spots"][sorted(f["go_rate_clear_spots"])[-2]])),
        ],
        why=[
            "**Game day:** the same engine could produce a pregame go/kick chart by field position and distance for the head coach's call sheet.",
            "**Post-game review:** every fourth down graded against the best option, so the staff argues about inputs (our kicker, our short-yardage offense) rather than outcomes.",
            "**Front office:** a running count of win probability lost to conservative calls, in wins, is a number ownership understands.",
        ],
        method_eq=[
            r"$\text{WP}_{\text{go}} = P(\text{convert})\cdot \text{WP}(\text{first down}) + \big(1 - P(\text{convert})\big)\cdot \text{WP}(\text{opponent ball at the spot})$",
            r"$\text{WP}_{\text{FG}} = P(\text{make})\cdot \text{WP}(+3,\ \text{kickoff}) + \big(1 - P(\text{make})\big)\cdot \text{WP}(\text{opponent ball after a miss})$",
            r"A call is charged $\max_k \text{WP}_k - \text{WP}_{\text{call}}$ only when that gap is at least 1 point. Brier score $= \frac{1}{N}\sum_i (p_i - y_i)^2$.",
        ],
        validation=lambda f: [
            f"Trained on 2006-2023, tested on {f['wp_test_plays']:,} plays from 2024-25: Brier {f['brier_ours']:.4f} vs nflfastR {f['brier_nflfastR_vegas_wp']:.4f} on the same rows; r = {f['corr_with_nflfastR']:.3f}.",
            "Calibration plot under result 1: predicted vs actual win rate by bin, close to the 45-degree line.",
            f"Football sanity checks run as unit tests: 4th-and-1 at midfield favors going (+{f['sanity_4th1_midfield_go_boost']:.1f} WP), 4th-and-10 at your own 20 favors kicking ({f['sanity_4th10_own20_go_boost']:.1f}).",
            "Monotone constraints keep the model football-logical (a bigger lead never lowers WP).",
        ],
        next=["Team-specific inputs: the offense's short-yardage success and the kicker's range.",
              "Two-point decisions and end-of-half clock management.",
              "A one-page in-game chart per opponent."],
        files={"fourth_downs_scored.parquet": "Every fourth down with WP for go, field goal and punt",
               "team_scorecard.csv": "WP points lost per game by team, current season",
               "go_rate_when_math_says_go.csv": "Go rate in clear go spots by season",
               "costliest_calls_current_season.csv": "The current season's most expensive calls",
               "wp_calibration_2024_2025.csv": "Calibration bins for the out-of-sample test",
               "kickoff_start_by_season.csv": "Average drive start after a kickoff, used by the bot",
               "model_summary.txt": "Model settings and test scores"},
    ),
    "03-sack-leverage": dict(
        short="Sack Leverage",
        tldr=lambda f: [
            f"Down and distance decide a sack's worth: short 3rd-down sacks take the most (3rd-and-1-2: {f['epa_lost_per_sack']['3&1-2']:.2f} expected points), and an average 2nd-down sack ({f['epa_lost_2nd_down_sack_avg']:.2f}) beats a 3rd-and-11+ sack ({f['epa_lost_per_sack']['3&11+']:.2f}).",
            f"{_pct(f['share_2nd_down_sacks_to_3rd_and_11plus'])} of 2nd-down sacks leave 3rd-and-11 or longer, and the series survives only {_pct(f['series_success_after_2nd_down_sack'])} of the time.",
            f"Brett Kollmann's third-down table replicates with public data (3rd-and-1-2 conversion {f['third_down_conversion_by_distance']['1-2']}% vs his 62.8%), and ranking rushers by value instead of sack count reorders the list.",
        ],
        question="Are all sacks equal, or does the down and distance decide how much a sack is worth?",
        seasons=lambda f: "2016-now",
        tags=["expected points", "replication", "player valuation"],
        hero=("epa_per_sack.png", "Expected points taken away per sack, by down and distance."),
        figs={4: [("pass_rusher_board.png", "Pass rushers ranked by expected points taken, not sack count.")]},
        key=lambda f: [
            ("Average 2nd-down sack, EPA taken", f"{f['epa_lost_2nd_down_sack_avg']:.2f}"),
            ("3rd-and-11+ sack, EPA taken", f"{f['epa_lost_per_sack']['3&11+']:.2f}"),
            ("2nd-down sacks that leave 3rd-and-11+", _pct(f["share_2nd_down_sacks_to_3rd_and_11plus"])),
            ("Series still converted after a 2nd-down sack", _pct(f["series_success_after_2nd_down_sack"])),
            ("3rd-and-1-2 conversion rate (" + f["third_down_window"] + ")", f"{f['third_down_conversion_by_distance']['1-2']}%"),
        ],
        why=[
            "**Pass-rush evaluation:** rank rushers by the expected points their sacks took, not the count; it reorders the list.",
            "**Defensive game planning:** a second-down sack ends more drives than a long third-down sack. That is the value of the sack, not of calling pressure; whether a pressure call pays depends on what it gives up when it does not get home.",
            "**Free agency:** a sack total built on long third downs is worth less than it looks.",
        ],
        method_eq=[r"Value of a sack $= -\text{EPA}_{\text{play}}$ (nflfastR expected points), credited half and half on shared sacks."],
        validation=lambda f: [
            "Replicates Brett Kollmann's third-down conversion table from PFF data with public play-by-play: "
            f"{f['third_down_conversion_by_distance']['1-2']}/{f['third_down_conversion_by_distance']['3-6']}/{f['third_down_conversion_by_distance']['7-10']}/{f['third_down_conversion_by_distance']['11+']}% vs his 62.8/46.8/34.4/16.3.",
            "A unit test checks that conversion falls as distance grows.",
        ],
        next=["Credit pressures, not only sacks, from nflverse participation data (2023 on).",
              "Split credit between the rusher who finished and the one who forced it."],
        files={"third_down_by_distance.csv": "Third-down conversion and sack rate by distance",
               "epa_lost_per_sack.csv": "EPA taken per sack by down and distance",
               "pass_rusher_board_2025.csv": "Rushers ranked by EPA taken, last full season",
               "pass_rusher_board_2026.csv": "The same for the season in progress"},
    ),
    "04-luck-index": dict(
        short="Luck Index",
        tldr=lambda f: [
            f"Fumble, field-goal and close-game luck do not repeat (year-to-year r = {f['yoy_r_fumble_luck']:.2f}, {f['yoy_r_fg_luck']:.2f}, {f['yoy_r_one_score_luck']:.2f}).",
            f"Points predict next season better than record (r = {f['r_next_winpct_from_pythag']:.2f} vs {f['r_next_winpct_from_winpct']:.2f}).",
            f"Teams that won 2+ more games than their points said changed by {f['lucky_change_wins_per17']:+.1f} wins the next year; the unlucky ones by {f['unlucky_change_wins_per17']:+.1f}.",
        ],
        question="How many wins does chance hand out, and do the lucky teams fall back the next year?",
        seasons=lambda f: "2006-now",
        tags=["Pythagorean expectation", "regression to the mean", "year-to-year stability"],
        hero=("luck_regression.png", "Wins above points this year vs change in wins next year."),
        figs={4: [("luck_2026.png", "This season: actual wins vs what points scored and allowed predict.")]},
        key=lambda f: [
            ("Fumble-recovery luck, year-to-year r", f"{f['yoy_r_fumble_luck']:.2f}"),
            ("One-score record luck, year-to-year r", f"{f['yoy_r_one_score_luck']:.2f}"),
            ("Next-year win %: r with Pythagorean win %", f"{f['r_next_winpct_from_pythag']:.2f}"),
            ("Next-year win %: r with actual win %", f"{f['r_next_winpct_from_winpct']:.2f}"),
            ("Teams 2+ wins over their points: next-year change", f"{f['lucky_change_wins_per17']:+.1f} wins"),
            ("Teams 2+ wins under: next-year change", f"{f['unlucky_change_wins_per17']:+.1f} wins"),
        ],
        why=[
            "**Front office planning:** judge a season by points, not record, before extending a coach or buying at the deadline.",
            "**Projections:** start next year's win projection from Pythagorean wins.",
            "**Communication:** a simple, honest way to tell ownership how much of a record was the bounces.",
        ],
        method_eq=[r"Pythagorean win % $= \dfrac{PF^{2.37}}{PF^{2.37} + PA^{2.37}}$",
                   r"Fumble luck $=$ fumbles recovered $- \tfrac12 \times$ all fumbles in the team's games; one-score luck $=$ one-score wins $- \tfrac12 \times$ one-score games."],
        validation=lambda f: [
            f"Each luck type is tested for repeatability first: fumbles r = {f['yoy_r_fumble_luck']:.2f}, field goals r = {f['yoy_r_fg_luck']:.2f}, one-score games r = {f['yoy_r_one_score_luck']:.2f}.",
            "A unit test fails the build if any of these rises above 0.2.",
        ],
        next=["Add drops and dropped interceptions (FTN charting, 2022 on).",
              "A weekly luck-adjusted standings table in season."],
        files={"team_season_luck.csv": "Every team-season with each luck component",
               "luck_2026.csv": "The season in progress"},
    ),
    "05-kickoff-value": dict(
        short="Kickoff Value",
        tldr=lambda f: [
            f"The new kickoff brought returns back: {_pct(f['by_season']['2023']['return_rate'])} of kickoffs returned in 2023, {_pct(f['by_season']['2025']['return_rate'])} in 2025.",
            f"Drives start {f['by_season']['2025']['avg_start_own'] - f['by_season']['2023']['avg_start_own']:.1f} yards further up than in 2023, but the average return still lands {abs(f['returned_vs_tb_league']):.1f} yards behind a touchback.",
            f"Kickers now create field position: {f['best_kickers'][0][0]} holds opponents {abs(f['best_kickers'][0][2]):.1f} yards short of the touchback spot on average ({f['best_kickers'][0][1]} kickoffs, so a small sample).",
        ],
        question="What did the new kickoff rule do to field position, and who creates value under it?",
        seasons=lambda f: "2016-" + sorted(f["by_season"])[-1],
        tags=["rule-change analysis", "special teams", "player valuation"],
        hero=("kickoff_era.png", "Return rate and drive start by season, across the 2024 and 2025 rule changes."),
        figs={3: [("returners.png", "Returners since 2025: average start vs where a touchback would have put the ball.")]},
        key=lambda f: [
            ("Kickoffs returned, 2023", _pct(f["by_season"]["2023"]["return_rate"])),
            ("Kickoffs returned, 2025", _pct(f["by_season"]["2025"]["return_rate"])),
            ("Average drive start, 2023 to 2025", f"own {f['by_season']['2023']['avg_start_own']:.1f} to {f['by_season']['2025']['avg_start_own']:.1f}"),
            ("Average return vs a touchback (2025 on)", f"{f['returned_vs_tb_league']:+.1f} yards"),
            ("Best kicker: opponent start short of the touchback spot", f"{f['best_kickers'][0][0]}, {abs(f['best_kickers'][0][2]):.1f} yards ({f['best_kickers'][0][1]} kickoffs)"),
        ],
        why=[
            "**Kicker evaluation:** kickoff placement is now worth yards; it belongs in the kicker grade next to field goals.",
            "**Roster spots:** a returner who lands behind the touchback spot is costing field position.",
            "**Special-teams scheme:** where to aim kickoffs, by kicker and coverage unit.",
        ],
        method_eq=[r"Yards vs touchback $=$ receiving team's first-snap yard line $-$ touchback spot for that rule year (25 through 2023, 30 in 2024, 35 from 2025)."],
        validation=lambda f: [
            "Fair catches are not counted as returns. Kickoffs returned for a touchdown or lost on a fumble have no receiving-team first snap, so they drop out of the whole sample.",
            "The rule-year touchback spot is applied by season, so eras are compared on their own terms.",
        ],
        next=["Separate hang time from coverage once public tracking allows it.",
              "A return-or-kneel decision model for returners."],
        files={"kickoffs_by_season.csv": "Kickoffs, touchback and return rates, drive start and EP by season",
               "kickers_2025_on.csv": "Kickers since 2025: opponent start vs the touchback",
               "returners_2025_on.csv": "Returners since 2025: start vs the touchback"},
    ),
    "06-pass-run": dict(
        short="Pass vs Run",
        tldr=lambda f: [
            f"Passing beat running on neutral early downs in {f['seasons_pass_better']} of {f['seasons_total']} seasons.",
            f"Teams moved slowly: early-down pass rate {_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[0]])} to {_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[-2]])}.",
            f"At team level, passing more tracks efficiency only at r = {f['team_corr_proe_epa_last_full']:.2f}: the edge depends on the quarterback and line.",
        ],
        question="Passing has been more efficient for years. So why do teams still run, and does passing more make a team better?",
        seasons=lambda f: sorted(f["epa_gap_by_season"])[0] + "-" + sorted(f["epa_gap_by_season"])[-1],
        tags=["EPA", "pass rate over expected", "team-level correlation"],
        hero=("epa_pass_vs_run.png", "EPA per play on neutral early downs: dropbacks vs designed runs, by season."),
        figs={3: [("proe_vs_epa.png", "Team pass rate over expected vs EPA per play, last full season.")]},
        key=lambda f: [
            ("Seasons passing beat running (neutral early downs)", f"{f['seasons_pass_better']} of {f['seasons_total']}"),
            ("EPA per play gap, last full season", f"{f['epa_gap_by_season'][sorted(f['epa_gap_by_season'])[-2]]:.2f}"),
            ("Pass rate, first to last full season", f"{_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[0]])} to {_pct(f['pass_rate_by_season'][sorted(f['pass_rate_by_season'])[-2]])}"),
            ("Team pass rate over expected vs EPA (r)", f"{f['team_corr_proe_epa_last_full']:.2f}"),
        ],
        why=[
            "**Offensive tendencies:** the league-wide edge for passing on early downs is real and stable.",
            "**Team-specific calls:** whether a team can cash it depends on its quarterback and line, so the answer is a personnel question, not a league average.",
            "**Opponent scouting:** pass rate over expected is a clean tendency number for the weekly packet.",
        ],
        method_eq=[r"Pass rate over expected (PROE) $=$ actual dropback rate $- \overline{\text{xpass}}$, where xpass is nflfastR's dropback probability given the situation."],
        validation=lambda f: [
            f"The pass edge holds in every season ({f['seasons_pass_better']} of {f['seasons_total']}), so it is not one era.",
            "Dropbacks include sacks and scrambles, so passing is charged its true cost.",
        ],
        next=["Sequencing: does an early run set up play action later (FTN charting, 2022 on)?",
              "Second-down run tendencies by personnel."],
        files={"neutral_early_downs_by_season.csv": "Plays, EPA, success rate and pass rate by season",
               "team_proe_vs_epa.csv": "Team PROE and EPA per play, last full season"},
    ),
    "07-box-score-tax": dict(
        headline=1,
        short="The Box-Score Tax",
        tldr=lambda f: [
            f"Pressures repeat (r = {f['yoy_r_pressure_rate']:.2f}); sacks bounce (r = {f['yoy_r_sack_rate']:.2f}); sacks beyond what pressures predict barely repeat at all (r = {f['yoy_r_sack_luck']:.2f}).",
            f"Teams still pay about ${f['musd_per_lucky_sack_2026']:.2f}M a year for each sack beyond what pressures predict ({f['market_contracts']} contracts, 95% CI ${f['musd_per_lucky_sack_ci'][0]:.2f}-{f['musd_per_lucky_sack_ci'][1]:.2f}M).",
            f"A future sack costs ${f['musd_per_future_sack_via_luck']:.2f}M bought through sack luck vs ${f['musd_per_future_sack_via_pressure']:.2f}M through pressures. Evidence of a market inefficiency, not proof; includes the {f['fa_class']} free-agent target list.",
        ],
        question="Do NFL teams pay pass rushers for sacks that won't repeat, when pressures predict future sacks better?",
        seasons=lambda f: f["seasons"],
        tags=["clustered OLS", "bootstrap", "contract valuation", "market pricing"],
        hero=("sack_tax.png", "What the market pays for a sack vs what a sack predicts, in non-sack pressures."),
        figs={1: [("rush_stability.png", "Year-to-year stability: pressure rate vs sack rate.")],
              4: [("buy_low_rushers.png", "Sacks vs what pressures predict, last full season.")],
              7: [("coverage_stability.png", "Coverage stats: how much each one repeats.")]},
        key=lambda f: [
            ("Pressure rate, year-to-year r", f"{f['yoy_r_pressure_rate']:.2f}"),
            ("Sack rate, year-to-year r", f"{f['yoy_r_sack_rate']:.2f}"),
            ("Sack luck, year-to-year r", f"{f['yoy_r_sack_luck']:.2f}"),
            ("League sacks per pressure", f"{f['league_sacks_per_pressure']:.3f}"),
            ("Paid per lucky sack, per year (2026 dollars)", f"${f['musd_per_lucky_sack_2026']:.2f}M (95% CI ${f['musd_per_lucky_sack_ci'][0]:.2f}-{f['musd_per_lucky_sack_ci'][1]:.2f}M)"),
            ("Cost per future sack: via sack luck vs via pressures", f"${f['musd_per_future_sack_via_luck']:.2f}M vs ${f['musd_per_future_sack_via_pressure']:.2f}M"),
            ("Contracts / players", f"{f['market_contracts']} / {f['market_players']}"),
        ],
        why=[
            "**Free agency:** shop by pressure rate; the same future sacks cost less when the platform year was unlucky. The study ends with a free-agent target list.",
            "**Negotiation:** a sack total well above what pressures predict is the part of a résumé least likely to repeat, and the part to pay least for.",
            "**Pro scouting:** pair the film with the pressure-to-sack gap to separate a finisher from a lucky year.",
        ],
        method_eq=[
            r"$\text{sack luck}_i = \text{sacks}_i - c \cdot \text{pressures}_i$, where $c$ is the league's sacks per pressure (see key numbers).",
            r"Price: $\dfrac{\text{APY}_i}{\text{cap}_t} = \beta_0 + \beta_1\,\text{pressures}_i + \beta_2\,\text{sack luck}_i + \beta_3\,\text{snaps}_i + \varepsilon_i$, standard errors clustered by player.",
            r"Prediction: $\text{sacks}_{i,t+1} = \gamma_0 + \gamma_1\,\text{pressures}_{i,t} + \gamma_2\,\text{sack luck}_{i,t} + \gamma_3\,\text{snaps}_{i,t} + u_{i,t}$.",
        ],
        validation=lambda f: [
            f"{f['robust_n']} robustness versions (age controls, edge or interior only, multi-year deals, deals over 1% of the cap, recent deals): ${f['robust_min']:.2f}M to ${f['robust_max']:.2f}M per lucky sack. Every point estimate is positive; the recent-deals interval includes zero.",
            f"Deals signed 2023-2026 alone: ${f['recent_deals_price'][0]:.2f}M and not significant; reported, not hidden.",
            f"1,000 bootstrap samples resampling players: the market ratio exceeds the predictive ratio in {100 * f['share_boot_market_above_predict']:.0f}%.",
            "The same idea was tested on coverage stats and rejected (finding 7).",
        ],
        next=["Repeat with a second charting source (NGS or PFF pressures).",
              "Add run-defense value so the contract model credits the whole player."],
        files={"rusher_contracts_with_platform.csv": "Each veteran ED/IDL contract with the platform season's stats",
               "rusher_sack_luck_board.csv": "Every rusher-season: sacks, pressures, expected sacks, sack luck",
               "free_agents_2027_rushers.csv": "2027 free-agent rushers with pressure rate and sack luck",
               "robustness_lucky_sack_price.csv": "Price per lucky sack under six model versions",
               "models.txt": "Full regression output"},
    ),
    "08-yac-tax": dict(
        headline=1,
        short="The YAC Tax",
        tldr=lambda f: [
            f"YAC over expected is noisy per catch (r = {f['yoy_r']['avg_yac_above_expectation']:.2f}), but a season of it predicts next year like air yards ({f['predict_next_yards_per_yard']['yacoe_yds']:.2f} vs {f['predict_next_yards_per_yard']['air_yds']:.2f} yards per yard).",
            f"Contracts price each part of receiving production about the same per future yard (${f['musd_per_100_future_yards']['yacoe_yds']:.2f}M per 100 YAC-over-expected yards vs ${f['musd_per_100_future_yards']['air_yds']:.2f}M per 100 air yards): no YAC tax.",
            f"The receiver market looks efficient where the pass-rush market (study 07) does not; {f['market_contracts']} veteran WR/TE contracts.",
        ],
        question="Do teams pay receivers for yards after the catch that won't come back?",
        seasons=lambda f: f["seasons"],
        tags=["Next Gen Stats", "clustered OLS", "contract valuation", "null result"],
        hero=("yac_tax.png", "Price per 100 future yards for each part of a receiver's production."),
        figs={1: [("receiver_stability.png", "Year-to-year stability of receiving traits.")]},
        key=lambda f: [
            ("YAC over expected per catch, year-to-year r", f"{f['yoy_r']['avg_yac_above_expectation']:.2f}"),
            ("Next-year yards per yard: YAC over expected", f"{f['predict_next_yards_per_yard']['yacoe_yds']:.2f}"),
            ("Next-year yards per yard: air yards", f"{f['predict_next_yards_per_yard']['air_yds']:.2f}"),
            ("Price per 100 future yards: YACOE / air / expected YAC", f"${f['musd_per_100_future_yards']['yacoe_yds']:.2f}M / ${f['musd_per_100_future_yards']['air_yds']:.2f}M / ${f['musd_per_100_future_yards']['xyac_yds']:.2f}M"),
            ("Contracts / players", f"{f['market_contracts']} / {f['market_players']}"),
        ],
        why=[
            "**Receiver evaluation:** don't discount a receiver's YAC as luck by default; a season of it predicts next year like air yards do.",
            "**Where to look for edges:** the receiver market prices production about right, unlike the pass-rush market in study 07.",
            "**Free agency:** the free-agent receiver list shows who leaned on YAC, as a reason to check the film, not to pass.",
        ],
        method_eq=[r"Receiving yards $=$ air yards on catches $+$ expected YAC $+$ YAC over expected (NGS), so the three parts add to the total.",
                   r"Price and prediction models regress APY share of the cap, and next-season yards, on the three parts plus targets, with standard errors clustered by player."],
        validation=lambda f: [
            f"{len(f['robustness']) - 1} robustness versions (WR only, TE only, multi-year deals, deals over 1% of the cap, 2023-2026 deals) recompute the price per 100 yards (not per future yard). YAC over expected is priced at or above air yards in {sum(r['yacoe_yds_musd_per_100'] >= r['air_yds_musd_per_100'] for r in f['robustness'][1:])} of them.",
            f"95% interval for next-year yards per YACOE yard: {f['predict_ci']['yacoe_yds'][0]:.2f}-{f['predict_ci']['yacoe_yds'][1]:.2f}, overlapping air yards.",
            "A null result is reported as one: the hypothesis was a tax, and the data does not show it.",
        ],
        next=["Route-level separation once public route data allows it.", "Tight ends below the NGS qualifying line."],
        files={"receivers_2025.csv": "Last full season: each receiver's yards split three ways",
               "free_agents_2027_receivers.csv": "2027 free-agent receivers",
               "robustness_price_per_100_yards.csv": "Price per 100 yards under each model version",
               "models.txt": "Full regression output"},
    ),
}
