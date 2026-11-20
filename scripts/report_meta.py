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

def _holdout_tldr(f):
    """One sentence on the held-out component test, written from the result whichever way it falls."""
    h = f["holdout"]; fl = h["flips"]
    comps = [h["convert_4th"]["brier"], h["fg"]["brier"], h["punt"]["rmse"]]
    n = sum(c["model_minus_league_avg"][2] < 0 for c in comps)
    beat = "all beat" if n == 3 else f"beat in {n} of 3 cases"
    moves = "moves the go rate or the team card past its interval" if h["headline"]["moves"] else "leaves the go rate and every team on the card inside their intervals"
    return (f"Its conversion, field-goal and punt models, fit on {h['train']}, {beat} the league average on {h['test']}, and a bot fit on "
            f"those seasons alone changes {_pct(fl['components'][0], 1)} of the recommendations and {moves}.")


def _holdout_table(f):
    """Held-out scores, model against each baseline, with the paired difference and its 95% interval."""
    h = f["holdout"]
    rows = ["| Component (test plays) | Score | Model | League average | Simple table | Model minus league average | Model minus table |", "|---|---|---|---|---|---|---|"]
    d = lambda v, k: f"{v[0]:+.{k}f} ({v[1]:+.{k}f} to {v[2]:+.{k}f})"
    for key, name in (("convert_4th", "Conversion, 4th downs"), ("convert", "Conversion, 3rd and 4th downs"), ("fg", "Field goal, all attempts"),
                      ("fg_in_range", f"Field goal, {h['fg_max_dist_train']} yards and in")):
        for metric, lab in (("brier", "Brier"), ("log_loss", "Log loss")):
            s = h[key][metric]
            rows.append(f"| {name} ({h[key]['n']:,}) | {lab} | {s['model'][0]:.4f} | {s['league_avg'][0]:.4f} | {s['distance_table'][0]:.4f} | "
                        f"{d(s['model_minus_league_avg'], 4)} | {d(s['model_minus_distance_table'], 4)} |")
    s = h["punt"]["rmse"]
    rows.append(f"| Punt, opponent's start ({h['punt']['n']:,}) | RMSE, yards | {s['model'][0]:.2f} | {s['league_avg'][0]:.2f} | {s['avg_net'][0]:.2f} | "
                f"{d(s['model_minus_league_avg'], 2)} | {d(s['model_minus_avg_net'], 2)} |")
    return (f"**Held-out scores, fit on {h['train']} and scored on {h['test']}.** Lower is better. The simple table is the training-season rate by distance "
            "(conversion and field goals) or the training-season average net punt from the spot. A difference whose interval stays below zero is a win for the model.\n\n"
            + "\n".join(rows))


def _jn(xs):
    xs = list(xs)
    return " and ".join(xs) if len(xs) <= 2 else ", ".join(xs[:-1]) + " and " + xs[-1]


def draft_table(f):
    """The positions-by-round table: career AV over the curve per pick (rounds 1-7) and second-contract money (rounds 3-7 pooled)."""
    rs = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    head = "| Position | " + " | ".join(f"Rd {r[1]}" for r in rs) + " | Rds 3-7 AV vs slot | Rds 3-7 money vs slot (pts of cap) | Rds 3-7 picks |"
    out = [head, "|---" * (len(rs) + 4) + "|"]
    for p in f["grid_av"]:
        cells = [f"{f['grid_av'][p][r]:+.1f}" + ("*" if f["grid_av_clear"][p][r] else "") for r in rs]
        x = f["r37"][p]
        av = f"{100 * x['av_rel']:+.0f}%" + ("*" if x["av_ci"][0] > 0 or x["av_ci"][1] < 0 else "")
        mo = f"{x['apy_surplus']:+.2f}" + ("*" if x["apy_ci"][0] > 0 or x["apy_ci"][1] < 0 else "")
        out.append(f"| {p} | " + " | ".join(cells) + f" | {av} | {mo} | {x['picks']} |")
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
            f"I built a win-probability model that comes close to nflfastR out of sample (Brier {f['brier_ours']:.4f} vs {f['brier_nflfastR_vegas_wp']:.4f} on {f['wp_test_plays']:,} plays) and a fourth-down bot on top of it. " + _holdout_tldr(f),
            f"Coaches now go for it in {_pct(f['go_rate_clear_spots'][sorted(f['go_rate_clear_spots'])[-2]])} of clear go spots, up from {_pct(f['go_rate_clear_spots'][sorted(f['go_rate_clear_spots'])[0]])} in {sorted(f['go_rate_clear_spots'])[0]}. Only spots that stay go spots when the models are refit are counted. The held-out test caught an error in the punt model; before the fix these read {_pct(f['punt_fix']['go_rate_before'][sorted(f['go_rate_clear_spots'])[-2]][0])} and {_pct(f['punt_fix']['go_rate_before'][sorted(f['go_rate_clear_spots'])[0]][0])}.",
            f"The team card is a description, not a ranking: a team's lost win probability in odd weeks predicts its even weeks at r = {f['scorecard_split_half_r']:.2f}, and {f['scorecard_teams_clear_of_median']} of 32 teams clear the league median this season.",
        ],
        question="When the math says go for it on fourth down, how often do coaches go, and can the cost be pinned on a team?",
        seasons=lambda f: "2006-" + sorted(f["go_rate_clear_spots"])[-1],
        tags=["gradient boosting", "win probability", "decision analysis", "game bootstrap"],
        hero=("go_rate_trend.png", "Go rate when going adds 2+ win-probability points."),
        figs={1: [("wp_calibration.png", "Out-of-sample calibration of my win-probability model, 2024-25.")],
              4: [("holdout_components.png", "The conversion, field-goal and punt models on seasons they were not fit on: predicted against actual, with the number of plays in each bin.")],
              7: [("team_scorecard.png", "Win-probability points lost per game on charged fourth-down calls, this season, with 90% intervals.")]},
        key=lambda f: [
            ("Brier score, my WP model (out of sample)", f"{f['brier_ours']:.4f}"),
            ("Brier score, nflfastR (same plays)", f"{f['brier_nflfastR_vegas_wp']:.4f}"),
            ("Agreement with nflfastR (r)", f"{f['corr_with_nflfastR']:.3f}"),
            ("Test plays", f"{f['wp_test_plays']:,}"),
            ("Go rate in clear go spots, " + sorted(f["go_rate_clear_spots"])[0], _pct(f["go_rate_clear_spots"][sorted(f["go_rate_clear_spots"])[0]])),
            ("Go rate in clear go spots, " + sorted(f["go_rate_clear_spots"])[-2], _pct(f["go_rate_clear_spots"][sorted(f["go_rate_clear_spots"])[-2]])),
            ("Median standard error of the go-vs-kick margin (WP points)", f"{f['median_go_boost_se']:.2f}"),
            (f"4th-down conversion Brier, held out {f['holdout']['test']} (league average)", f"{f['holdout']['convert_4th']['brier']['model'][0]:.4f} ({f['holdout']['convert_4th']['brier']['league_avg'][0]:.4f})"),
            ("Field-goal Brier, held out (league average)", f"{f['holdout']['fg']['brier']['model'][0]:.4f} ({f['holdout']['fg']['brier']['league_avg'][0]:.4f})"),
            ("Punt start RMSE in yards, held out (league average)", f"{f['holdout']['punt']['rmse']['model'][0]:.1f} ({f['holdout']['punt']['rmse']['league_avg'][0]:.1f})"),
            (f"Recommendations that change with components fit on {f['holdout']['train']} only", f"{100 * f['holdout']['flips']['components'][0]:.1f}% ({100 * f['holdout']['flips']['components'][1]:.1f}% to {100 * f['holdout']['flips']['components'][2]:.1f}%)"),
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
            f"The conversion, field-goal and punt models are fit on {f['holdout']['train']} and scored on {f['holdout']['test']} (result 4): Brier score and log loss against the league-average rate and a distance-only table for the two probability models, RMSE against two baselines for punts, each with a 95% interval from resampling games. Calibration by bin with counts is in `holdout_calibration.csv` and the figure under result 4.",
            f"A second bot built only from the {f['holdout']['train']} fits rescored every {f['holdout']['test']} fourth down (result 5): {100 * f['holdout']['flips']['components'][0]:.1f}% of recommendations change, and the rule for whether the headline numbers move was written before the run.",
            f"The win-probability, conversion, field-goal and punt models are refit on {f['n_boot']} resamples of games, so every recommendation carries a standard error.",
            f"The team card is tested for repeatability before it is read: split-half r = {f['scorecard_split_half_r']:.2f}, year-to-year r = {f['scorecard_yoy_r']:.2f}.",
            f"Football sanity checks: 4th-and-1 at midfield favors going ({f['sanity_4th1_midfield_go_boost']:+.1f} WP), 4th-and-10 at your own 20 favors kicking ({f['sanity_4th10_own20_go_boost']:+.1f}). The bot's arithmetic is unit-tested on a made-up model (`tests/test_logic.py`).",
            "Monotone constraints keep the model football-logical (a bigger lead never lowers WP).",
        ],
        next=["Team-specific inputs: the offense's short-yardage success and the kicker's range.",
              "Two-point decisions and end-of-half clock management.",
              "A one-page in-game chart per opponent."],
        tables=lambda f: {4: [_holdout_table(f)]},
        files={"fourth_downs_scored.parquet": "Every fourth down with WP for go, field goal and punt, and the refit standard errors",
               "holdout_scores.csv": "Held-out scores for the conversion, field-goal and punt models and their baselines, with 95% game-bootstrap intervals",
               "holdout_calibration.csv": "Held-out calibration: predicted against actual by bin, with counts",
               "holdout_fourth_downs.parquet": "Every test-season fourth down with the production and the training-seasons-only recommendation",
               "holdout_team_card.csv": "The team card under both versions of the bot",
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
    "10-draft-value": dict(
        headline=1,
        short="Draft Value",
        tldr=lambda f: [
            f"The value of a pick falls steeply through round 1 and flattens after: on the smoothed curve pick 32 keeps {100 * f['av_share_of_top5']['32']:.0f}% of a top-five pick's career AV and pick 100 {100 * f['av_share_of_top5']['100']:.0f}% ({f['picks']:,} picks, drafts {f['draft_classes']}).",
            f"In rounds 3-7, linemen beat their slot in career AV (OT {100 * f['r37']['OT']['av_rel']:+.0f}%, IOL {100 * f['r37']['IOL']['av_rel']:+.0f}%, IDL {100 * f['r37']['IDL']['av_rel']:+.0f}%, intervals clear of zero) but second-contract money does not clearly confirm it; the only clear money gap is running backs ({f['r37']['RB']['apy_surplus']:+.2f} points of cap a year, {100 * f['r37']['RB']['apy_rel']:+.0f}% vs slot), and the two measures disagree most on quarterbacks and tight ends (rank r across 11 positions {f['r37_rank_corr_av_apy']:.2f}, {f['r37_rank_corr_av_apy_no_qb']:.2f} without quarterbacks).",
            f"By a rule set before the results, the three clearest inefficiencies are {', '.join(x['pos'] + ' (' + x['direction'] + ')' for x in f['inefficiencies'])}: clear in AV, same direction but not clear in contract APY, and {' and '.join(sorted(set.intersection(*[set(p for p, _ in v) for v in f['rule_versions'].values()]))) or 'no position'} stays in the top three under every alternative I tried. Only {100 * f['share_beat_slot_all']:.0f}% of late-round picks beat their slot, so no position is a safe bet (best Sharpe ratio {f['r37'][f['r37_by_sharpe'][0]]['sharpe']:+.2f}).",
        ],
        question="In rounds 3-7, which positions return the most value per pick, and are some positions drafted too late?",
        seasons=lambda f: f"drafts {f['draft_classes']}",
        tags=["pick-value curve", "kernel smoothing", "bootstrap", "cross-validation", "contract valuation"],
        hero=("gm_one_page.png", "Rounds 3-7 by position: career AV, second-contract money and second-contract rate, each against the average pick at the same slots."),
        figs={1: [("pick_value_curve.png", "The pick-value curve in career AV and second-contract money.")],
              2: [("surplus_heatmap.png", "Career AV over the curve by position and round.")],
              4: [("hit_rates.png", "Starter and second-contract rates against the rate expected at the same picks.")],
              5: [("risk_return.png", "Mean surplus against its spread, rounds 3-7 (MacKelvie's Sharpe ratio).")]},
        tables=lambda f: {2: ["**Positions by round.** Career AV over the pick-value curve per pick (rounds 1-2 for reference), and rounds 3-7 pooled in AV (% vs slot) and second-contract money (APY points of cap a year). * = 95% bootstrap interval clear of zero.", draft_table(f)]},
        key=lambda f: [
            ("Picks (drafts) / rounds 3-7", f"{f['picks']:,} ({f['draft_classes']}) / {f['picks_r37']:,}"),
            ("Pick 32 / pick 100 as a share of a top-five pick (career AV)", f"{100 * f['av_share_of_top5']['32']:.0f}% / {100 * f['av_share_of_top5']['100']:.0f}%"),
            ("Rounds 3-7 positions clear of the slot in AV (after Holm)", f"{len(f['r37_av_clear'])} of 11 ({len(f['r37_av_holm_clear'])})"),
            ("Rounds 3-7 positions clear of the slot in second-contract money", f"{len(f['r37_apy_clear'])} of 11 ({', '.join(f['r37_apy_clear']) or 'none'})"),
            ("Rank correlation, AV vs money, 11 positions (without QB)", f"{f['r37_rank_corr_av_apy']:.2f} ({f['r37_rank_corr_av_apy_no_qb']:.2f})"),
            ("OT / IOL / IDL career AV vs slot", f"{100 * f['r37']['OT']['av_rel']:+.0f}% / {100 * f['r37']['IOL']['av_rel']:+.0f}% / {100 * f['r37']['IDL']['av_rel']:+.0f}%"),
            ("RB second-contract APY vs slot (95% interval)", f"{f['r37']['RB']['apy_surplus']:+.2f} pts of cap ({f['r37']['RB']['apy_ci'][0]:+.2f} to {f['r37']['RB']['apy_ci'][1]:+.2f})"),
            ("Late-round picks that beat their slot", f"{100 * f['share_beat_slot_all']:.0f}%"),
        ],
        why=[
            "**Draft room:** on a tie in rounds 3-7, the evidence leans to the interior lineman over the corner or the running back; it is a tiebreaker, not a reason to reach.",
            "**Trade value:** the curve says what a pick is expected to return, so a pick-for-pick trade can be checked against it in AV or in second-contract money.",
            "**Roster planning:** late-round running backs return less second-contract money than their slot and late-round quarterbacks rarely become starters, so a depth chart that counts on either is a depth chart with a hole.",
        ],
        method_eq=[
            r"Curve: $\hat{y}(p) = \text{isotonic}\!\left(\dfrac{\sum_i K_h(\log p - \log p_i)\, y_i}{\sum_i K_h(\log p - \log p_i)}\right)$, Gaussian $K_h$, bandwidth $h$ chosen by leaving out one draft class at a time.",
            r"Surplus of pick $i$: $s_i = y_i - \hat{y}(p_i)$; a position's value over the curve is $\bar{s}$ over its picks, and AV vs slot is $\bar{y}/\bar{\hat{y}} - 1$.",
            r"Sharpe ratio for position $g$: $\bar{s}_g / \text{sd}(s_g)$, rounds 3-7.",
        ],
        validation=lambda f: [
            f"Out of sample: fit on all classes but one, scored on the class left out, the smoothed curve beats plain round averages for every outcome (career AV {f['curve_cv']['w_av_adj']['improvement_pct']:.1f}%, money {f['curve_cv']['apy_pct']['improvement_pct']:.1f}%, starter {f['curve_cv']['started']['improvement_pct']:.1f}%, second contract {f['curve_cv']['second']['improvement_pct']:.1f}%, snaps {f['curve_cv']['snap_games']['improvement_pct']:.1f}% lower squared error).",
            f"{f['robust_n']} versions of the rounds 3-7 position test (classes {f['draft_classes'].split('-')[0]}-2017 only, 2011-2021 only, 2019-2021 left out, AV not class-scaled, AV for the drafting team, positions from the draft label only, second-contract money in a 2-5 and a 3-6 year window, second-contract rate, rookie-deal snaps, starter rate) are in `robustness_rounds_3_7.csv`. OT and IOL keep their sign in {f['robust_sign_agree']['OT']} and {f['robust_sign_agree']['IOL']} of {f['robust_n']}; RB stays below its slot in {f['robust_sign_agree']['RB']} of {f['robust_n']}; TE flips in {f['robust_n'] - f['robust_sign_agree']['TE']} (below in AV, above in starts).",
            f"A bootstrap that resamples whole draft classes instead of picks keeps the same AV result ({_jn(f['class_boot_av_clear'])} clear) and widens the money result to {_jn(f['class_boot_apy_clear'])}; the pick bootstrap is the more conservative for money, so the page reports it.",
            f"Intervals come from 1,000 bootstrap samples that refit the curve each time. A regression check with errors clustered by drafting team gives the same rounds 3-7 position means (`models.txt`), and with draft-class fixed effects and log pick, {', '.join(p for p, v in f['ols_vs_wr_fe'].items() if v[1] > 0)} stay clearly above WR.",
            f"Multiple tests: {len(f['r37_av_holm_clear'])} of 11 AV results and {len(f['r37_apy_holm_clear'])} of 11 money results survive a Holm correction; in the full table {f['grid_cells_clear']} of {f['grid_cells']} cells clear zero against about {0.05 * f['grid_cells']:.0f} expected by chance.",
            "An independent review re-ran the study, checked every number on this page against findings.json, tested robustness, checked the definition of each nflverse column used and web-checked the named players; its corrections are in this version.",
        ],
        next=["Replace AV with a position-neutral value measure (wins above replacement by position) when a public one covers 2006 onward.",
              "Price the surplus in cap dollars: what a late-round starter at each position saves against the veteran market for the same snaps.",
              "Add pre-draft consensus boards, so the test is against where a player was expected to go, not only where he went."],
        files={"surplus_by_position_round.csv": "Every position-round cell for all six outcomes: mean, expected, surplus, 95% interval, n",
               "rounds_3_7_summary.csv": "Rounds 3-7 by position: AV, money, hit rates, snaps, Sharpe ratio, Holm-adjusted p",
               "rounds_3_7_by_position.csv": "Rounds 3-7 by position for each outcome: picks earlier and Sharpe ratio with intervals",
               "robustness_rounds_3_7.csv": "The rounds 3-7 position test (% vs slot) under nine outcomes and samples",
               "pick_value_curve.csv": "The smoothed curve at every pick for each outcome",
               "late_round_picks.csv": "Every round 3-7 pick with its outcomes and AV surplus",
               "models.txt": "Regression output: position means with team-clustered errors, and the fixed-effects check"},
    ),
    "11-turnovers-forced": dict(
        headline=1,
        short="Turnovers Forced",
        tldr=lambda f: [
            f"Takeaways repeat less than the rest of a defense: with the league trend taken out, takeaways per play repeat year to year at r = {f['yoy_r']['to_rate'][0]:.2f} against {f['yoy_r']['epa_noto'][0]:.2f} for EPA allowed without takeaways (gap {f['yoy_r_diff']['epa_noto_minus_to_rate'][0]:.2f}, 95% interval {f['yoy_r_diff']['epa_noto_minus_to_rate'][1]:.2f} to {f['yoy_r_diff']['epa_noto_minus_to_rate'][2]:.2f}), and who recovers a fumble does not repeat at all (r = {f['yoy_r']['fum_rec_share'][0]:.2f}; {f['pairs']} team-season pairs, {f['seasons']}).",
            f"Top-5 takeaway defenses keep {100 * f['top5_excess_retained'][0]:.0f}% of their takeaway edge next year, but whether a takeaway year fools people is {f['fooled_verdict']}: against same-points defenses their points allowed move {f['top5_pa_change_vs_matched'][0]:+.2f} per game (95% interval {f['top5_pa_change_vs_matched'][1]:+.2f} to {f['top5_pa_change_vs_matched'][2]:+.2f}), and my hypothesis predicts {f['top5_gap_predicted_if_fooled']:+.2f}.",
            f"EPA without turnovers predicts next year's points allowed better than takeaways in {f['oos_epa_beats_to_in']} of {len(f['oos_splits'])} out-of-sample splits, by a small margin; a defensive back's interceptions per snap repeat at r = {f['player_yoy']['DB']['ints100'][0]:.2f}, his pass breakups at {f['player_yoy']['DB']['pbu100'][0]:.2f}.",
        ],
        question="Do defenses that force turnovers keep doing it, and does a takeaway-heavy year fool people?",
        seasons=lambda f: f"{f['seasons'].split('-')[0]}-{f['current_season']}",
        tags=["play-by-play", "franchise bootstrap", "clustered OLS", "out-of-sample", "inconclusive test"],
        hero=("stability.png", "Year-to-year stability of each defensive measure, with each season's league average taken out."),
        figs={2: [("predict_points.png", "How well each measure predicts next season's points allowed.")],
              4: [("top5_regression.png", "Top-5 and bottom-5 takeaway defenses, the year of and the year after."),
                  ("fooled_test.png", "Next-year change in points allowed: top takeaway defenses minus same-season defenses that allowed the same points, against the gap my hypothesis predicts.")],
              5: [("player_interceptions.png", "Year-to-year stability of interceptions and coverage stats for players.")],
              7: [("buy_sell_2026.png", "2026 through the latest completed week: points per game from takeaways against a league-average rate.")]},
        key=lambda f: [
            ("Year-to-year r (league trend out): takeaways per play / INT rate / recovery share", f"{f['yoy_r']['to_rate'][0]:.2f} / {f['yoy_r']['int_rate'][0]:.2f} / {f['yoy_r']['fum_rec_share'][0]:.2f}"),
            ("Year-to-year r: EPA without takeaways / sack or hit rate / points allowed", f"{f['yoy_r']['epa_noto'][0]:.2f} / {f['yoy_r']['press_rate'][0]:.2f} / {f['yoy_r']['pa_pg'][0]:.2f}"),
            ("Next-year points, base out-of-sample RMSE: takeaways / EPA / points allowed", f"{f['oos']['takeaways per 100 plays']['rmse']:.2f} / {f['oos']['EPA allowed, no-takeaway plays']['rmse']:.2f} / {f['oos']['points allowed this year']['rmse']:.2f}"),
            ("Top-5 takeaway edge kept next year (95% interval)", f"{100 * f['top5_excess_retained'][0]:.0f}% ({100 * f['top5_excess_retained'][1]:.0f}% to {100 * f['top5_excess_retained'][2]:.0f}%)"),
            ("Top-5 extra points allowed next year vs same-points defenses / predicted if fooled", f"{f['top5_pa_change_vs_matched'][0]:+.2f} ({f['top5_pa_change_vs_matched'][1]:+.2f} to {f['top5_pa_change_vs_matched'][2]:+.2f}) / {f['top5_gap_predicted_if_fooled']:+.2f}"),
            ("Carry share of points: takeaways / EPA without takeaways", f"{100 * f['carry_share_to_rate'][0]:.0f}% ({100 * f['carry_share_to_rate'][1]:.0f}% to {100 * f['carry_share_to_rate'][2]:.0f}%) / {100 * f['carry_share_epa_noto'][0]:.0f}%"),
            ("DB year-to-year r: INTs per snap / breakups per snap / INTs per target (PFR)", f"{f['player_yoy']['DB']['ints100'][0]:.2f} / {f['player_yoy']['DB']['pbu100'][0]:.2f} / {f['pfr_yoy']['int_rate'][0]:.2f}"),
            (f"{f['current_season']} sell / buy flags (through Week {f['through_week']}; no tested forecast edge)", f"{', '.join(x['team'] for x in f['sell']) or 'none'} / {', '.join(x['team'] for x in f['buy']) or 'none'}"),
        ],
        why=[
            "**Pro personnel and the coaching staff:** a defense's takeaway count is mostly this year's bounces; its success rate, EPA allowed without takeaways and pass rush are what carry, and fumble recoveries carry nothing.",
            "**Front office and free agency:** a big interception year from one defensive back mostly goes away; his pass breakups are the steadier sign of coverage, though they do not predict next year's interceptions.",
            "**Projecting next season:** start from points allowed and EPA without takeaways, not takeaways; whether a takeaway-heavy defense needs extra regression beyond that is not settled by this data.",
        ],
        method_eq=[
            r"Takeaway rate $= 100 \times (\text{INT} + \text{fumbles lost by the offense}) / \text{scrimmage plays}$; recovery share $= \text{defense recoveries} / \text{offense fumbles with a recovering team}$.",
            r"Carry share $= \beta_{\text{next}} / \beta_{\text{same}}$ from $\text{PA}_{t} \text{ or } \text{PA}_{t+1} = \alpha + \beta_1 \text{EPA}^{\text{no TO}}_t + \beta_2 \text{TO rate}_t + \varepsilon$, every term relative to its season's league average.",
            r"Top-5 gap $= \overline{\Delta \text{PA}}_{\text{top 5}} - \overline{\Delta \text{PA}}_{\text{same-season controls within 1 point}}$; predicted gap if fooled $=$ EPA carry share $\times$ points per game the takeaways saved.",
        ],
        validation=lambda f: [
            f"Out of sample in three splits (seasons {f['oos_train']} to {f['oos_test']}, the reverse, and leave one season out): EPA without takeaways beats takeaways in {f['oos_epa_beats_to_in']} of {len(f['oos_splits'])}, and adding takeaways to EPA helps in {f['oos_adding_to_helps_in']}. The in-season version fits weeks 1-{f['split_week']} to weeks {f['split_week'] + 1}+ (points so far: RMSE {f['inseason_oos_rmse']['points allowed so far']:.2f}; takeaways: {f['inseason_oos_rmse']['takeaways per 100 plays']:.2f}; EPA without takeaways: {f['inseason_oos_rmse']['EPA allowed, no-takeaway plays']:.2f}).",
            f"{len(f['top5_robustness'])} versions of the top-5 test (top 3, top 8, match windows of 2 and 3 points, ranking per play, ranking by interception rate, controls from any season) are in `robustness_top5.csv`; the gap runs {min(r['pa_change_vs_matched'][0] for r in f['top5_robustness']):+.2f} to {max(r['pa_change_vs_matched'][0] for r in f['top5_robustness']):+.2f} points per game and {sum(r['pa_change_vs_matched'][1] < 0 < r['pa_change_vs_matched'][2] for r in f['top5_robustness'])} of {len(f['top5_robustness'])} intervals cross zero.",
            f"Within a season, which no league trend can touch, odd-week and even-week halves agree at r = {f['split_half']['to_rate']['split_half_r']:.2f} for takeaway rate, {f['split_half']['int_rate']['split_half_r']:.2f} for interception rate and {f['split_half']['fum_rec_share']['split_half_r']:.2f} for recovery share, against {f['split_half']['epa_noto']['split_half_r']:.2f} for EPA without takeaways: the same order as year to year.",
            f"The player result does not depend on era: defensive backs' interceptions per snap repeat at r = {f['db_ints100_yoy_2018on'][0]:.2f} ({f['db_ints100_yoy_2018on'][1]:.2f} to {f['db_ints100_yoy_2018on'][2]:.2f}) in 2018 onward, the seasons study 07 covers. Study 07's PFR numbers are recomputed here with its own code and match.",
            "The buy/sell rule was fixed before the list was run and back-tested at the same week of every season since 2006; the back-test found no forecast edge, and the page says so.",
            "An independent review re-ran the study and checked every number, column definition and named player. It found that the year-to-year correlations were inflated by the league-wide fall in interceptions (now taken out), that the top-5 test matched controls across seasons (now within the season) and could not tell the two answers apart (now reported as inconclusive, with the predicted effect shown), that a claimed gain from adding takeaways to EPA did not survive other splits (removed), and that special-teams recoveries are outside the takeaway count and one interception leader had been traded (both now stated).",
        ],
        next=["Opponent-adjust takeaway rates for the quarterbacks a defense faced.",
              "Use FTN charting (2022+) for dropped interceptions and tipped balls, so interceptions can be split into the defender's part and the quarterback's.",
              "A more powerful version of the fooled test: points per drive allowed by the defense alone, without return touchdowns, and more seasons as they come."],
        files={"team_season_defense.csv": "Every team-season, 2006 to the last full season: defensive takeaways, recovery share, pass rush, EPA and points allowed",
               "top5_takeaway_seasons.csv": "The top-5 takeaway seasons and the season after",
               "robustness_top5.csv": "The top-5 test under eight versions",
               "backtest_week10_flags.csv": "The buy/sell rule applied at the split week of every past season, with the rest-of-season result",
               "buy_sell_2026.csv": "This season through the latest completed week: every defense, its takeaway points and flag",
               "models.txt": "Regression output, errors clustered by franchise"},
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
