"""Write every report README and the top-level README from the saved findings.

Narrative text lives here; every number comes from reports/<slug>/findings.json, so a refresh
(scripts/update.py) rewrites the numbers without anyone retyping them.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "reports"
YT = "https://www.youtube.com/watch?v="


def F(slug):
    return json.loads((R / slug / "findings.json").read_text())


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def _above(f):
    a = f["rtp_above_league"]; c = f["rtp_above_league_after_correction"]
    n = f["rtp_qbs"]; ch = f["rtp_expected_above_by_chance"]
    if not a:
        return "Nobody sits clearly above the league rate (95% interval)."
    names = " and ".join(a) if len(a) <= 2 else ", ".join(a[:-1]) + " and " + a[-1]
    after = ("None of them stays above it once the test is corrected for checking " + str(n) + " quarterbacks at once."
             if not c else f"After correcting for checking {n} quarterbacks at once, {' and '.join(c)} still {'does' if len(c) == 1 else 'do'}.")
    return (f"{names} {'has' if len(a) == 1 else 'have'} a 95% interval above the league rate. With {n} quarterbacks, about {ch:g} would by chance alone. {after}")


def flag_audit():
    f = F("01-flag-audit")
    era = {k.strip("()").replace("'", "").replace(" ", ""): v for k, v in f["home_edge_by_era"].items()}
    eras = sorted({k.split(",")[0] for k in era})
    old, new = eras[0], eras[-1]
    sk = f["objective_road_skew_top"]
    top = f["rtp_top"]
    mah = f.get("rtp_mahomes", [None, None, None])
    crew = f["crew_spread_latest"]
    return f"""# 01 Flag Audit: do NFL flags really even out?

**Inspired by:** Michael MacKelvie, [We looked at 92,255 flags - NFL refs are biased]({YT}LH3Ck59I8V0).
**Data:** nflverse play-by-play and officials, {f['seasons']} ({f['games']:,} games, {f['flags']:,} accepted flags). Declined and offsetting flags removed.
**Code:** [`projects/flag_audit.py`](../../projects/flag_audit.py)

## What I found
1. **The road team's extra judgment-call flags have shrunk since 2023, and the data cannot yet say they are gone.** In {old}, road teams drew {era[old + ',subjective']:.2f} more subjective flags per game than home teams (holding, pass interference, roughing). Since 2023 the gap is {round(era[new + ',subjective'], 2) + 0:.2f}. Per 100 snaps that is {ci(f['road_subj_per_100_snaps_ci|' + old], 2)} before and {ci(f['road_subj_per_100_snaps_ci|' + new], 2)} since. The drop is {ci(f['road_subj_drop_per_100_snaps_ci'], 2)}. Two cautions. I picked 2023 after looking at the chart, and it gives the biggest drop of the {len(f['drop_by_break_year'])} break years I could have picked. And in close game states only (score within {f['close_score_points']}), the drop is {ci(f['road_subj_drop_per_100_close_snaps_ci'], 2)}, which {'excludes' if f['road_subj_drop_per_100_close_snaps_ci'][1] > 0 else 'includes'} zero.
2. **The road gap that is clearly still there is in rule-book flags.** Road teams still take about {era[new + ',objective']:.2f} extra rule-book flags a game. Neutral zone infractions go against the road defense {pct(sk.get('Neutral Zone Infraction', 0))} of the time, and delay of game against the road offense {pct(sk.get('Delay of Game', 0))}. False starts, the flag fans blame on crowd noise, split almost evenly ({pct(f['false_start_road_share'], 1)} on the road team). Crowd noise is one reading of the first two. This data cannot test it.
3. **Referee crews have a real, modest style.** A crew's flags per game this season predicts next season at r = {f['crew_yoy_r']:.2f} (95% interval {f['crew_yoy_r_ci'][0]:.2f} to {f['crew_yoy_r_ci'][1]:.2f}, {f['crew_pairs']} back-to-back crew seasons, crews resampled). In {f['crew_latest_season']}, {crew[1]}'s crew averaged {crew[0]:.1f} flags a game and {crew[3]}'s averaged {crew[2]:.1f}.
4. **A team's flag luck does not carry over.** Within a season, a team's net subjective flags (drawn minus committed) in odd weeks predicts even weeks at only r = {f['split_r_net']:.2f}. Committing flags is a bit more stable (r = {f['split_r_committed']:.2f}) than drawing them (r = {f['split_r_drawn']:.2f}): discipline is partly real, getting calls is mostly not.
5. **Mahomes is not the roughing-flag king.** Among {mah[2]} QBs with 1,500+ dropbacks since 2018, he ranks #{mah[1]} (by shrunk rate) at {mah[0]:.2f} roughing flags per 100 dropbacks, about the league rate of {f['rtp_league_per100']:.2f}. The top of the list is {top[0][0]} ({top[0][3]:.2f} raw), {top[1][0]} ({top[1][3]:.2f}) and {top[2][0]} ({top[2][3]:.2f}). {_above(f)}
6. **Big calls are real but random.** {f['big_calls']:,} accepted flags ({f['big_calls_reg']:,} in the regular season) moved win probability by 10+ points, about {f['big_calls_per_full_season_reg']:.0f} per full regular season. Pass interference leads. A team's net big calls this year predicts next year at r = {f['big_call_net_yoy_r']:.2f}: no team is owed them.

![Home edge](home_edge.png)
![Crew stability](crew_stability.png)
![Roughing](qb_roughing.png)

## Method
- **Objective vs subjective:** objective flags are facts at the snap (alignment, motion, clock); subjective flags need a judgment about contact or intent. The lists are in [`nflan/penalties.py`](../../nflan/penalties.py).
- **Crews:** the referee's name stands for the crew (officials table, position = Referee). Regular-season crews with 10+ games.
- **Per play and close games:** road minus home subjective flags per 100 scrimmage snaps, for all snaps and for snaps with the score within {f['close_score_points']}. 95% intervals resample games 2,000 times.
- **Split-half reliability:** for each team-season, the odd-week mean vs the even-week mean.
- **Roughing:** flags drawn per dropback, with Wilson 95% intervals and empirical-Bayes shrinkage so small samples are not ranked on noise.

## Limits
- Play-by-play has no tracking data, so this cannot judge whether a single flag was correct.
- The 2023 break was chosen from the chart, not set in advance. Four seasons after it, one of them partial, is a short record.
- {f['rtp_qbs']} quarterbacks are tested against the league roughing rate at once, so about {f['rtp_expected_above_by_chance']:g} would sit above it by chance alone.
- "Big call" uses nflfastR's WPA, which measures the flag plus the play it wiped out.

## Files
`home_edge_by_season.csv`, `home_edge_by_era.csv`, `objective_road_skew_by_type.csv`, `crew_flags_per_game.csv`, `qb_roughing_drawn.csv`, `big_calls_team_season.csv`, `findings.json`
"""


def _wp_vs_nflfastr(f):
    d = f["brier_ours"] - f["brier_nflfastR_vegas_wp"]
    if abs(d) < 0.0002:
        return "level with"
    return f"{abs(d):.4f} {'behind' if d > 0 else 'ahead of'}"


def _card_verdict(f):
    r = f["scorecard_split_half_r"]
    if r >= 0.5:
        return "That is stable enough to rank teams."
    if r >= 0.25:
        return "That is some signal and a lot of noise, so read the card as a description of the season, not a ranking of coaches."
    return "That is mostly noise, so the card describes what happened and does not rank coaches."


def fourth():
    f = F("02-fourth-down-bot")
    g = f["go_rate_clear_spots"]; ys = sorted(g)
    last_full = ys[-2]; cur = ys[-1]
    gc = f["go_rate_ci"]; gn = f["go_rate_spots"]
    mc = f["most_costly"]; lc = f["least_costly"]
    th = f["go_rate_first_vs_last_full_by_threshold"]
    row = lambda x: f"{x[0]} ({x[1]:.1f}, 90% interval {x[2]:.1f} to {x[3]:.1f})"
    return f"""# 02 Fourth-Down Bot: how often do coaches go when the math says go?

**Inspired by:** Brett Kollmann, [Are analytics ruining football?]({YT}FOnQFk5qy-4) (judge the decision apart from the play), and Michael MacKelvie, [Passing is better...so, why run?]({YT}pPXZlK9puqw) (coaches lag the math). Method follows the public idea of Ben Baldwin's [nfl4th](https://github.com/nflverse/nfl4th), rebuilt from scratch in Python.
**Data:** nflverse play-by-play 2006-{cur}.
**Code:** [`nflan/wp.py`](../../nflan/wp.py), [`nflan/fourth.py`](../../nflan/fourth.py), [`projects/fourth_down_bot.py`](../../projects/fourth_down_bot.py)

## What I found
1. **The win-probability model comes close to nflfastR out of sample.** Trained on 2006-2023 and tested on {f['wp_test_plays']:,} plays from 2024-25: Brier score {f['brier_ours']:.4f}, against {f['brier_nflfastR_vegas_wp']:.4f} for nflfastR's spread-adjusted model on the same plays (lower is better). Mine is {_wp_vs_nflfastr(f)} theirs. The two agree at r = {f['corr_with_nflfastR']:.3f}. Calibration sits close to the 45-degree line.
2. **Coaches go for it far more than they used to.** In clear go spots (going adds 2+ win-probability points and still adds some when the models are refit, score within 16, outside the last 5 minutes), teams went {pct(g[ys[0]])} of the time in {ys[0]} (95% interval {pct(gc[ys[0]][0])} to {pct(gc[ys[0]][1])}, {gn[ys[0]]} spots) and {pct(g[last_full])} in {last_full} ({pct(gc[last_full][0])} to {pct(gc[last_full][1])}, {gn[last_full]} spots). {cur} so far: {pct(g[cur])} on {gn[cur]} spots ({pct(gc[cur][0])} to {pct(gc[cur][1])}), which {'overlaps' if gc[cur][0] <= gc[last_full][1] and gc[last_full][0] <= gc[cur][1] else 'does not overlap'} the {last_full} interval. The rise does not depend on the 2-point line: at a 1-point line the rate went from {pct(th['1'][0])} to {pct(th['1'][1])}, at 5 points from {pct(th['5'][0])} to {pct(th['5'][1])}.
3. **How sure is the bot?** I refit the conversion, field-goal and punt models on {f['n_boot']} resamples of games. The typical fourth down's go-versus-kick margin moves by {f['median_go_boost_se']:.2f} win-probability points (median standard error). {pct(f['share_1pt_gaps_that_hold_up'])} of calls that miss the best option by 1+ point still miss it in 95% of refits, and {pct(f['share_2pt_go_spots_that_hold_up'])} of 2+ point go spots stay go spots. Only those are charged or counted.
4. **{f['scorecard_season']} team card (regular season): a description, not a ranking.** Most win probability lost per game on charged calls: {row(mc[0])}, {row(mc[1])}, {row(mc[2])}. Least: {row(lc[-1])}, {row(lc[-2])}, {row(lc[-3])}. Does it repeat? Odd weeks against even weeks of the same season, r = {f['scorecard_split_half_r']:.2f} ({f['scorecard_team_seasons']} team-seasons, 2018-{last_full}); one season to the next, r = {f['scorecard_yoy_r']:.2f}. {_card_verdict(f)} This season {f['scorecard_teams_clear_of_median']} of 32 teams have an interval that clears the league median.
5. **Sanity checks.** 4th-and-1 at midfield, tied, early, even teams: going adds {f['sanity_4th1_midfield_go_boost']:.1f} WP points. 4th-and-10 at your own 20: going costs {abs(f['sanity_4th10_own20_go_boost']):.1f}.

![Go rate](go_rate_trend.png)
![Scorecard](team_scorecard.png)
![Calibration](wp_calibration.png)

## How the bot works
- **Win probability:** gradient-boosted trees on score, clock, field position, down and distance, timeouts, the second-half kickoff and the point spread. Like nflfastR, the spread fades as the game goes on and a lead counts more late. Monotone constraints keep it football-logical (more points ahead never lowers WP).
- **Go:** P(convert) from every 3rd and 4th down since 2016, by distance, field position and the offense's pregame spread (a better offense converts more), x WP after a first down (median extra yards by distance), plus (1 - P) x WP with the opponent taking over at the spot.
- **Field goal:** make probability by distance, dome and season, then WP after +3 and a kickoff (season-average drive start) or after a miss (opponent at the spot of the kick or the 20). No kick longer than {f['fg_max_dist']:.0f} yards is offered. That is the longest distance at which coaches still kick on at least a quarter of fourth downs; {f['fg_attempts_beyond_range']} of {f['fg_attempts_total']:,} attempts since 2016 were longer, and their make rate reflects strong legs and good conditions, not an average kicker.
- **Punt:** opponent's expected next start from the punt spot, then WP.
- **Grading:** a call is charged only when it misses the best option by 1+ WP point and the miss survives the refits (finding 3).

## Limits
- One average team: it knows the pregame spread, not a team's QB, kicker or short-yardage offense.
- Only the win-probability model is tested out of sample. The conversion, field-goal and punt models are fit and applied on the same 2016-{cur} plays; in that sample the conversion model predicts {pct(f['convert_in_sample'][0], 1)} and {pct(f['convert_in_sample'][1], 1)} converted.
- The refits vary the conversion, kick and punt models. The win-probability model is held fixed, so the true uncertainty is larger than finding 3 shows.
- Third downs feed the conversion model. Defenses play fourth down differently, which a 4th-down flag only partly covers.
- Seasons through 2023 are scored with a win-probability model trained on them (in sample); 2024 on is out of sample.
- No clock management beyond fixed play lengths, and fake punts count as "go".

## Files
`fourth_downs_scored.parquet` (every 4th down with WP by option and the refit standard errors), `team_scorecard.csv`, `go_rate_when_math_says_go.csv`, `costliest_calls_current_season.csv`, `wp_calibration_2024_2025.csv`, `kickoff_start_by_season.csv`, `model_summary.txt`, `findings.json`
"""


def _sack_trait(f):
    return ("EPA per sack repeats a little for a rusher." if f["epa_per_sack_repeats"]
            else "EPA per sack is not a repeatable trait of the rusher.")


def sacks():
    f = F("03-sack-leverage")
    c = f["third_down_conversion_by_distance"]; e = f["epa_lost_per_sack"]; b = f["board_top5"]; r = f["board_biggest_risers"]; d = f["third_minus_second_same_distance"]
    return f"""# 03 Sack Leverage: not all sacks are created equal

**Inspired by:** Brett Kollmann, [Not all sacks are created equal.]({YT}o6q1dd0mI8Q). He used PFF data; this rebuilds his table with public play-by-play, tests his second-down point at matched distances, and checks whether a rusher's value per sack repeats.
**Data:** nflverse play-by-play, regular seasons 2016 to now.
**Code:** [`projects/sack_leverage.py`](../../projects/sack_leverage.py)

## What I found
1. **His 3rd-down table roughly replicates.** 3rd-down conversion (first down or touchdown), {f['third_down_window']}: 1-2 yards {c['1-2']}%, 3-6 {c['3-6']}%, 7-10 {c['7-10']}%, 11+ {c['11+']}% (Kollmann, from PFF: 62.8, 46.8, 34.4, 16.3). The closest bucket is within a point; 7-10 yards is about two points lower here.
2. **Distance decides a sack's worth, and at the same distance third down usually costs more.** Expected points taken per sack ({f['sacks_in_table']:,} sacks): 3rd-and-1-2 {e['3&1-2']}, 3rd-and-3-6 {e['3&3-6']}, 3rd-and-7-10 {e['3&7-10']}, 3rd-and-11+ {e['3&11+']}; 2nd-and-1-2 {e['2&1-2']}, 2nd-and-3-6 {e['2&3-6']}, 2nd-and-7-10 {e['2&7-10']}, 2nd-and-11+ {e['2&11+']}. Third down minus second down at the same distance: {d['1-2'][0]:+.2f} at 1-2 yards (95% interval {d['1-2'][1]:+.2f} to {d['1-2'][2]:+.2f}), {d['3-6'][0]:+.2f} at 3-6 ({d['3-6'][1]:+.2f} to {d['3-6'][2]:+.2f}), {d['7-10'][0]:+.2f} at 7-10 ({d['7-10'][1]:+.2f} to {d['7-10'][2]:+.2f}), {d['11+'][0]:+.2f} at 11+ ({d['11+'][1]:+.2f} to {d['11+'][2]:+.2f}). The average third-down sack takes {f['epa_lost_3rd_down_sack_avg']:.2f} points and the average second-down sack {f['epa_lost_2nd_down_sack_avg']:.2f}. The one place a second-down sack matches a third-down sack is third-and-long, where the offense was unlikely to convert anyway.
3. **Why a 2nd-down sack still hurts: it usually ends the series.** {pct(f['share_2nd_down_sacks_to_3rd_and_11plus'])} of 2nd-down sacks leave 3rd-and-11 or longer. The offense extends the series {pct(f['series_success_after_2nd_down_sack'])} of the time after a 2nd-down sack, vs {pct(f['series_success_after_other_2nd_down_dropbacks_no_conversion'])} after other 2nd-down dropbacks that also failed to convert.
4. **{_sack_trait(f)}** For rushers with {f['min_sacks']}+ sacks in back-to-back seasons ({f['epa_per_sack_yoy_pairs']} pairs), EPA per sack repeats at r = {f['epa_per_sack_yoy_r']:.2f} (95% interval {f['epa_per_sack_yoy_ci'][0]:.2f} to {f['epa_per_sack_yoy_ci'][1]:.2f}); odd weeks against even weeks inside a season, r = {f['epa_per_sack_split_half_r']:.2f}. Sack counts repeat at r = {f['sack_count_yoy_r']:.2f} for the same players. So the board below records what happened in {f['board_season']}; it does not rate a rusher's skill at picking his spots, and it should not move a contract number.
5. **{f['board_season']} sacks by value (descriptive).** Top five by expected points taken: {', '.join(f'{x[0]} ({x[2]:g} sacks, {x[3]:.1f} EPA)' for x in b)}. Largest gaps between sack rank and value rank: {', '.join(f'{x[0]} (#{x[2]} in sacks, #{x[3]} in value)' for x in r)}.

![EPA per sack](epa_per_sack.png)
![Board](pass_rusher_board.png)

## Method
- Sacks are dropbacks with `sack == 1`; value is the negative of nflfastR EPA on the play.
- Half sacks get half credit. Boards: 6+ sacks for a full season, 3+ for the season in progress.
- Intervals on the down-and-distance table resample games 1,000 times. Stability intervals resample rushers 2,000 times.
- Series success is nflfastR's `series_success` (the series earned a first down or scored a touchdown; field goals count as failures).

## Limits
- Sacks only. Pressures and hurries need charting (`was_pressure` exists from 2023 in nflverse participation data); that is the next version.
- EPA blames or credits the whole defense, not just the rusher who finished the play.
- No garbage-time filter: sacks in decided games count the same as sacks in close ones.

## Files
`third_down_by_distance.csv`, `epa_lost_per_sack.csv`, `pass_rusher_board_<season>.csv`, `findings.json`
"""


def ci(v, d=2, flip=False):
    """[point, low, high] as 'x (95% interval a to b)'. flip swaps the bounds after a sign change."""
    p, lo, hi = v
    if flip:
        lo, hi = hi, lo
    return f"{p:.{d}f} (95% interval {lo:.{d}f} to {hi:.{d}f})"


def _luck_matched(f):
    a, b = f["lucky_minus_matched_wins"], f["unlucky_minus_matched_wins"]
    clear = [a[2] < 0, b[1] > 0]
    return "exclude zero" if all(clear) else ("include zero" if not any(clear) else "are borderline: one includes zero")


def luck():
    f = F("04-luck-index")
    lk = f["current_luckiest"]; ul = f["current_unluckiest"]
    ys = sorted(int(p.stem.split("_")[1]) for p in (R / "04-luck-index").glob("luck_20*.png"))[-1]
    return f"""# 04 Luck Index: how many wins does chance hand out?

**Inspired by:** Michael MacKelvie, [We Measured "Luck" in the NFL. It's a BIG deal.]({YT}Zfin10hS0YM), which builds on the NFL's own luck work (Tom Bliss).
**Data:** nflverse play-by-play, regular seasons 2006 to now.
**Code:** [`projects/luck_index.py`](../../projects/luck_index.py)

## What I found
1. **Luck does not repeat.** Year-to-year correlation: fumble-recovery luck r = {f['yoy_r_fumble_luck']:.2f}, opponent field-goal luck r = {f['yoy_r_fg_luck']:.2f}, one-score-game record r = {f['yoy_r_one_score_luck']:.2f}, wins above Pythagorean r = {f['yoy_r_wins_over_pythag']:.2f}.
2. **Points predict next year a little better than wins do.** Next season's win % correlates r = {f['r_next_winpct_from_pythag']:.2f} with this season's Pythagorean win % and r = {f['r_next_winpct_from_winpct']:.2f} with actual win %. The gap is {ci(f['r_pythag_minus_r_wins'], 2)}, small but above zero ({f['team_season_pairs']} team-season pairs, teams resampled {f['boot_n']:,} times).
3. **Wins that points do not explain do not carry over.** In a regression of next year's wins on this year's Pythagorean wins and the wins above them, a Pythagorean win is worth {ci(f['next_wins_per_pythag_win'], 2)} wins next year. A win above Pythagorean is worth {ci(f['next_wins_per_luck_win'], 2)}, which is no different from zero.
4. **The lucky fall back, mostly because every good record does.** Teams that won {f['lucky_cutoff_wins']:g}+ games more than their points said ({f['lucky_teams_n']} of them) changed by {f['lucky_change_wins_per17']:+.1f} wins the next year (per 17 games); teams that far below ({f['unlucky_teams_n']}) changed by {f['unlucky_change_wins_per17']:+.1f}. Against teams with the same record (within {f['match_window_wins']:g} win) whose record matched their points, the lucky fell {ci([-x for x in f['lucky_minus_matched_wins']][::1], 1, flip=True)} wins further and the unlucky rose {ci(f['unlucky_minus_matched_wins'], 1)} more. Both intervals {_luck_matched(f)}.
5. **Which luck matters.** With Pythagorean wins held fixed, next year's wins move by {ci(f['next_wins_per_fumble_recovery_over_exp'], 2)} per extra fumble recovery, {ci(f['next_wins_per_fg_point_of_luck'], 2)} per point of opponent field-goal luck, and {ci(f['next_wins_per_one_score_win_over_half'], 2)} per one-score win above half. None is clearly different from zero, so none of them is a skill to pay for.
6. **This season so far.** Above their points: {', '.join(f'{t} ({w:g} win{"" if w == 1 else "s"}, {p:.1f} expected)' for t, w, p in reversed(lk))}. Below: {', '.join(f'{t} ({w:g} win{"" if w == 1 else "s"}, {p:.1f} expected)' for t, w, p in ul)}.

![Regression](luck_regression.png)
![This season](luck_{ys}.png)

## Method
- **Pythagorean wins:** points for and against with exponent 2.37 (the usual NFL value).
- **Fumble luck:** fumbles recovered by the team in its games minus half of all fumbles in its games (a loose ball is close to a coin flip).
- **Field-goal luck:** points the opponent's kicker left short of a logistic make-probability model (distance, dome, season); positive = the opponent missed more than expected.
- **One-score luck:** wins in games decided by 8 or fewer minus half of those games.
- **Matched comparison:** each lucky team is compared with the teams within {f['match_window_wins']:g} win of its record (per 17 games) that finished within 1 win of their Pythagorean record.
- **Intervals:** 95%, from resampling the 32 teams with all their seasons {f['boot_n']:,} times.

## Limits
- No dropped passes or dropped interceptions: public charting of drops starts in 2022 (FTN), so the 20-year version leaves them out.
- The raw fall-back in finding 4 mixes luck with ordinary regression to the mean. The matched comparison separates them, and with {f['lucky_teams_n']} lucky and {f['unlucky_teams_n']} unlucky teams its intervals are wide.
- Fumble luck treats every loose ball as a coin flip. Recovery odds differ by fumble type, which this version ignores.
- Intervals resample teams, not seasons, so a league-wide shock in one year is not covered.

## Files
`team_season_luck.csv`, `luck_<season>.csv`, `findings.json`
"""


def kickoff():
    f = F("05-kickoff-value")
    s = f["by_season"]; ys = sorted(s)
    a, b2, c = s["2023"], s["2024"], s["2025"]
    bk = f["best_kickers"]; br = f["best_returners"]; ls = f["return_epa_by_landing_spot"]; MINR = 20
    return f"""# 05 Kickoff Value: the new kickoff, kickers and returners

**Inspired by:** Brett Kollmann, [Kick Returners are in Absolute Hell.]({YT}ELjLAp4eyic) and [Kickers are taking over the NFL.]({YT}UufAB2UcVMw).
**Data:** nflverse play-by-play, regular seasons 2016-{ys[-1]}. The NFL adopted the dynamic kickoff in 2024 (touchback to the 30) and moved the touchback to the 35 in 2025.
**Code:** [`projects/kickoff_value.py`](../../projects/kickoff_value.py)

## What I found
1. **Returns came back.** Return rate: {pct(a['return_rate'])} in 2023, {pct(b2['return_rate'])} in 2024, {pct(c['return_rate'])} in 2025, {pct(s[ys[-1]]['return_rate'])} in {ys[-1]} so far.
2. **Drives start about five yards further up.** Average start: own {a['avg_start_own']:.1f} in 2023, {b2['avg_start_own']:.1f} in 2024, {c['avg_start_own']:.1f} in 2025. Expected points at the first snap rose from {a['ep_first_snap']:.2f} to {c['ep_first_snap']:.2f}.
3. **Returns start behind the touchback, but that is the rule, not the returner.** Since 2025 the average return starts {abs(f['returned_vs_tb_league']):.1f} yards behind the touchback spot. A ball that lands in the landing zone has to be returned, so the returner cannot choose the 35. The fair baseline is a typical return from where the ball came down: worth {ls['end zone']:+.2f} expected points from the end zone, {ls['1-5']:+.2f} from the 1-5, {ls['6-10']:+.2f} from the 6-10, {ls['11-15']:+.2f} from the 11-15 and {ls['16-20']:+.2f} from the 16-20 (touchback: {f['touchback_epa']:+.2f}).
4. **Against that baseline the data cannot yet tell returners apart.** {f['returns']:,} returns in {f['era']}, with the {f['return_tds_kept']} return touchdowns and {f['return_fumbles_lost_kept']} lost fumbles included. For returners with {MINR}+ returns ({f['returners_rated']}), value per return over expected has a split-half r of {f['returner_split_half_r']:.2f}, and the estimated true spread between returners is {f['returner_signal_sd']:.2f} points per return. {f['returners_clear']} of {f['returners_rated']} have a 90% interval that excludes zero; about {f['returners_clear_expected_by_chance']:.0f} would by chance. The top of the raw list ({', '.join(f'{n} ({t}, {y:+.2f} ± {h:.2f} on {int(k)} returns)' for n, t, k, y, h in br)}) is a list of results, not of proven skill.
5. **Kickers show a small, real spread, and no one is clear of average yet.** Expected points allowed per kickoff, all outcomes, onside kicks and squibs removed ({f['onside_squib_dropped']} dropped): split-half r = {f['kicker_split_half_r']:.2f} across {f['kicker_split_half_n']} kickers, and the estimated true spread is {f['kicker_signal_sd']:.3f} points per kick, about {17 * 5 * f['kicker_signal_sd']:.1f} points over an 85-kick season for a kicker one standard deviation better. After shrinking toward average, the best estimates are {', '.join(f'{n} ({y:+.3f} ± {h:.3f}, {int(k)} kicks)' for n, k, y, h in bk)}; {f['kickers_clear']} of {f['kickers_rated']} intervals exclude zero.

![Era](kickoff_era.png)
![Returners](returners.png)

## Method
- **Season trends:** the receiving team's first snap after each kickoff (merge on game and play order). Touchback spot by rule year: own 25 through 2023, 30 in 2024, 35 from 2025; the code raises an error for a season with no rule entered.
- **Player value:** nflfastR EPA on the kickoff play from the receiving team's side, on kickoffs from the 35. Return touchdowns and lost fumbles stay in. Onside kicks, squibs and kicks recovered by the kicking team are removed.
- **Expected return value:** a gradient-boosted fit of EPA on the yard line where the ball came down (65 minus kick distance), minimum 150 returns per leaf.
- **Estimates:** empirical Bayes (normal-normal): each player's mean is shrunk by signal variance / (signal variance + play variance / n). When the estimated signal variance is zero, every player's estimate is the league average, which is the returner result here.
- **Split-half:** each player's odd-numbered plays against his even-numbered plays, in game order.

## Limits
- Kicker value mixes the kick, the coverage unit and the opponent's return team; play-by-play cannot split them.
- Two seasons of the current rule (one partial) is a small sample: a returner has 20 to 60 returns, and one touchdown moves his average a lot.
- The expected-value fit and the players it grades use the same returns.
- Landing spot is taken from the kick distance in the play-by-play, not from tracking data.

## Files
`kickoffs_by_season.csv`, `return_value_by_landing_spot.csv`, `kickers_2025_on.csv`, `returners_2025_on.csv`, `findings.json`
"""


def passrun():
    f = F("06-pass-run")
    g = f["epa_gap_by_season"]; ys = sorted(g)
    return f"""# 06 Pass vs Run: passing is better, so why run?

**Inspired by:** Michael MacKelvie, [Passing is better...so, why run?]({YT}pPXZlK9puqw) and Brett Kollmann, [Does "establishing the run" even work?]({YT}-W6orkJ_-Qg).
**Data:** nflverse play-by-play, regular seasons {ys[0]}-{ys[-1]}.
**Code:** [`projects/pass_run.py`](../../projects/pass_run.py)

## What I found
1. **Passing beat running on neutral early downs in {f['seasons_pass_better']} of {f['seasons_total']} seasons.** The gap's 95% interval sits above zero in {f['seasons_gap_interval_above_zero']} of them. The gap in expected points per play ranged from {min(g.values()):.2f} to {max(g.values()):.2f}; {ys[-2]} was {g[ys[-2]]:.2f}. Success rate favored passing by {100 * f['success_rate_gap_by_season'][ys[-2]]:.1f} points in {ys[-2]}.
2. **Teams barely moved.** Neutral early-down pass rate went from {pct(f['pass_rate_by_season'][ys[0]])} in {ys[0]} to {pct(f['pass_rate_by_season'][ys[-2]])} in {ys[-2]}.
3. **Teams that pass more than expected are a little more efficient.** Across {f['team_seasons_pooled']} team-seasons, pass rate over expected and EPA per play correlate at r = {ci(f['team_corr_pooled'], 2)}. The sign is positive in {f['team_corr_seasons_positive']} of {f['team_corr_seasons']} full seasons, and single seasons run from {f['team_corr_by_season_range'][0]:.2f} to {f['team_corr_by_season_range'][1]:.2f}. One season is too few teams to read: {ys[-2]} alone is r = {f['team_corr_proe_epa_last_full']:.2f} (95% interval {f['team_corr_last_full_ci'][0]:.2f} to {f['team_corr_last_full_ci'][1]:.2f}).
4. **The same team gets a little better when it passes more.** A team's year-to-year change in pass rate over expected tracks its change in EPA per play at r = {ci(f['within_team_change_corr'], 2)} ({f['within_team_pairs']} back-to-back team seasons). That is about {f['epa_per_play_per_proe_point_within_team']:.3f} EPA per play for each extra point of pass rate. It is still not cause and effect. A team that upgrades at quarterback passes more and scores more for the same reason.

![EPA](epa_pass_vs_run.png)
![PROE](proe_vs_epa.png)

## Method
- Neutral early downs: 1st and 2nd down, win probability 20-80%, more than 2 minutes left in the half; kneels, spikes and two-point tries removed.
- Dropbacks include sacks and scrambles (the true cost of calling a pass).
- Pass rate over expected uses nflfastR's `xpass` model.
- Team-level intervals are 95%, from resampling teams with all their seasons 2,000 times. Season gaps use play-level standard errors, which treat plays as independent.

## Limits
- EPA per play ignores sequencing (does a run set up play action later?). Kollmann's 2nd-down tendency idea is the next test.
- The team-level link is a correlation. Good passing teams choose to pass more, so it does not show that any team would gain by passing more.
- The league gap is an average over plays teams chose. It does not say the next extra pass is worth that much, because defenses adjust.
- The season in progress is left out of the team-level numbers.

## Files
`neutral_early_downs_by_season.csv`, `team_proe_vs_epa.csv`, `findings.json`
"""


def _usd(x):
    return f"-${abs(x):.2f}M" if x < 0 else f"${x:.2f}M"


def _tax_verdict(f):
    """Wording follows the test, so a refresh cannot leave a stale verdict."""
    if f["tax_ratio_ci95"][0] > 1:
        return "sack luck is priced above what it predicts"
    if f["tax_ratio_ci90"][0] > 1:
        return "sack luck looks overpriced, short of the 95% bar"
    return "no clear overpricing of sack luck"


def box_score_tax():
    f = F("07-box-score-tax")
    bl = f["buy_low_last_full"]; sh = f["sell_high_last_full"]; fa = f["fa_buy_targets"]; ca = f["fa_careful"]
    def rusher(x):
        return f"{x[0]} ({x[1]}: {x[2]:g} sacks on {x[3]:g} pressures, {x[4]:.1f} expected)"
    return f"""# 07 The Box-Score Tax: do NFL teams overpay for sacks?

**The question:** where is value hiding that people aren't looking at? My bet: in the gap between what a stat says about the past and what it says about the future. Sacks are the headline pass-rush stat. They are also rare, so they are noisy. Pressures happen two to four times as often. If teams pay for sacks more than sacks predict, a team that shops by pressures buys the same future sacks for less.
**Data:** Pro Football Reference advanced defense ({f['seasons']}), nflverse snap counts, and {f['market_contracts']} veteran edge and interior DL contracts ({f['market_players']} players) from Over The Cap (signed 2019-2026), all via [nflverse](https://github.com/nflverse/nflverse-data). Dollars use the 2026 salary cap (${f['cap_2026_musd']}M).
**Code:** [`projects/box_score_tax.py`](../../projects/box_score_tax.py). Prior work: PFF's Sam Monson made this argument in 2021 with player examples ([link](https://www.pff.com/news/nfl-teams-are-still-paying-for-sacks-in-free-agency-and-the-edge-defender-market-is-suffering-because-of-it)); this study puts a price on it with public data.

## What I found
1. **Pressures repeat; sacks bounce.** For pass rushers with 300+ snaps in back-to-back seasons ({f['rush_pairs']:,} pairs), pressure rate repeats at r = {f['yoy_r_pressure_rate']:.2f}, sack rate at r = {f['yoy_r_sack_rate']:.2f}. This year's pressure rate predicts next year's sack rate (r = {f['r_next_sack_rate_from_pressure_rate']:.2f}) better than this year's sack rate does (r = {f['r_next_sack_rate_from_sack_rate']:.2f}).
2. **Teams pay for sack luck, and it does predict a little.** "Sack luck" means sacks above what a player's pressures predict at his group's rate (edge {f['sacks_per_pressure_by_group']['edge']:.3f}, interior {f['sacks_per_pressure_by_group']['interior']:.3f} sacks per pressure). It barely repeats (r = {f['yoy_r_sack_luck']:.2f} year to year). Holding pressures, snaps, age and the prior season fixed, one lucky sack predicts {f['future_sacks_per_lucky_sack']:.2f} extra sacks next year (95% interval {f['future_sacks_per_lucky_sack_ci'][0]:.2f} to {f['future_sacks_per_lucky_sack_ci'][1]:.2f}), so it is not pure noise. Each one adds about **${f['musd_per_lucky_sack_2026']:.2f}M a year** to a veteran contract (95% interval ${f['musd_per_lucky_sack_ci'][0]:.2f}M to ${f['musd_per_lucky_sack_ci'][1]:.2f}M, 2026 dollars, one deal per player-year, errors clustered by player).
3. **The test: {_tax_verdict(f)}.** Stated before running it: relative to a pressure, is a lucky sack priced above what it predicts? The ratio is {f['tax_ratio']:.2f} (1.00 means fairly priced), with a 90% bootstrap interval of {f['tax_ratio_ci90'][0]:.2f} to {f['tax_ratio_ci90'][1]:.2f} and a 95% interval of {f['tax_ratio_ci95'][0]:.2f} to {f['tax_ratio_ci95'][1]:.2f}; it is above 1 in {100 * f['tax_ratio_share_above_1']:.0f}% of {f['tax_ratio_boot_n']:,} samples that resample players. In dollars, an expected future sack costs about ${f['musd_per_future_sack_via_luck']:.2f}M bought through sack luck (90% interval ${f['musd_per_future_sack_via_luck_ci90'][0]:.2f}M to ${f['musd_per_future_sack_via_luck_ci90'][1]:.2f}M) against ${f['musd_per_future_sack_via_pressure']:.2f}M through pressures (${f['musd_per_future_sack_via_pressure_ci90'][0]:.2f}M to ${f['musd_per_future_sack_via_pressure_ci90'][1]:.2f}M). The wide upper end comes from dividing by a small, noisy number.
4. **It has not clearly faded.** Deals signed {f['recent_deals_label']} ({f['recent_deals_n']} contracts): ${f['recent_deals_price'][0]:.2f}M per lucky sack (95% interval {_usd(f['recent_deals_price'][1])} to {_usd(f['recent_deals_price'][2])}). Deals signed {f['earlier_deals_label']}: ${f['earlier_deals_price'][0]:.2f}M ({_usd(f['earlier_deals_price'][1])} to {_usd(f['earlier_deals_price'][2])}). Across the {f['robust_n']} versions in `robustness_lucky_sack_price.csv` the price runs ${f['robust_min']:.2f}M to ${f['robust_max']:.2f}M, and {f['robust_ci_above_zero']} of {f['robust_n']} intervals exclude zero.
5. **Sacks short of pressures ({f['current_season'] - 1}).** {'; '.join(rusher(x) for x in bl[:4])}.
6. **Sacks ahead of pressures ({f['current_season'] - 1}).** {'; '.join(rusher(x) for x in sh[:3])}. Elite rushers can beat the group rate for years, so this is a list of where the excess sits, not a forecast of decline for any one player.
7. **The {f['fa_class']} free-agent rushers.** Contracts ending after {f['current_season']} (Over The Cap via nflverse), still active in {f['current_season']}, rookie first-rounders with a fifth-year option left out. A flag needs {f['fa_flag_rule']['min_pressures']}+ pressures in {f['current_season'] - 1} and a gap of {f['fa_flag_rule']['luck_cut_sacks']:g}+ sacks between actual and expected. Pressure without the sacks ({f['fa_flag_rule']['buy_n']}): {', '.join(f"{x[0]} ({x[1]}, age {x[6]:g} in {f['current_season'] - 1}, {x[4]:g} pressures, {x[3]:g} sacks)" for x in fa[:5]) or 'none this year'}. Sacks ahead of pressures ({f['fa_flag_rule']['careful_n']}): {', '.join(f"{x[0]} (age {x[5]:g}, {x[3]:g} sacks on {x[4]:g} pressures)" for x in ca[:5]) or 'none'}. Ages and contract status come from the data files and were not news-checked; check both before acting.
8. **Coverage: the same idea failed, and that matters.** I expected interceptions to be the coverage version of sacks. In PFR's charting, interception rate repeats best (r = {f['yoy_r_int_rate']:.2f}), above completion % allowed (r = {f['yoy_r_cmp_pct']:.2f}) and yards per target allowed (r = {f['yoy_r_yds_per_target']:.2f}). The market pays about ${f['musd_per_int_2026']:.2f}M per platform-year interception. Public coverage stats are too noisy to call that a mistake, so I don't.

![Stability](rush_stability.png)
![Tax](sack_tax.png)
![Buy low](buy_low_rushers.png)
![Coverage](coverage_stability.png)

## Method
- **Traded players:** PFR lists a combined row plus one row per team; only the combined row is kept.
- **Pass rushers:** player-seasons with 300+ regular-season defensive snaps, listed DE/DT/DL/NT or with 15+ pressures (catches 3-4 outside linebackers). Edge and interior players get their own sacks-per-pressure rate. PFR pressures = sacks + hurries + knockdowns; "non-sack pressures" removes the sacks so the two are not double counted.
- **Contracts:** veteran deals only (rookie contracts dropped), one deal per player-year (a tag or tender and a long-term deal signed the same year count once: the longer, then richer, deal), at least 0.4% of the cap, matched to the player's season right before signing. Price and prediction models both control for snaps, age, age squared and the season before the platform year (pressures and sacks). Pay is measured as APY as a share of that year's cap, so 2019 and 2026 deals compare fairly. Pay and prediction regressions cluster standard errors by player (many players sign several deals); full output in `models.txt`.
- **The test statistic:** (price per lucky sack / price per pressure) divided by (next-year sacks per lucky sack / next-year sacks per pressure). Both samples are resampled by player 2,000 times. A lucky sack also predicts {f['future_pressures_per_lucky_sack']:.2f} extra pressures next year (95% interval {f['future_pressures_per_lucky_sack_ci'][0]:.2f} to {f['future_pressures_per_lucky_sack_ci'][1]:.2f}), which is not distinguishable from zero.
- **Shrinkage:** a player's own conversion rate carries little signal. The method-of-moments prior is worth about {f['shrink_prior_pressures']:.0f} pressures, so a 40-pressure season moves the estimate of his true rate only slightly; the `sack_luck_shrunk` column shows it.

## Limits
- Pressure charting is PFR's, which differs from PFF and NGS; all charting has judgment in it.
- Contracts reflect more than stats: injuries, scheme fit and run defense. The models hold pressures, snaps, age and the prior season fixed but not those.
- The prediction sample needs 300+ snaps in back-to-back seasons, so players who were hurt or lost their jobs drop out.
- Pay is average per year, not guarantees or cash in the first three years.
- The future outcome is next season's sacks. A team may also be paying for pressure it expects in later years or for run defense.
- Free-agent status comes from Over The Cap via nflverse and can lag a new extension or a retirement. Check a player's status before acting.
- The platform season is the season before signing, which mis-times in-season extensions slightly.
- PFR's current-season file lags the snap counts, so player ratings use full seasons only.

## Files
`rusher_contracts_with_platform.csv`, `rusher_sack_luck_board.csv`, `free_agents_{f['fa_class']}_rushers.csv`, `models.txt`, `findings.json`
"""


def yac_tax():
    f = F("08-yac-tax")
    y = f["yoy_r"]; pr = f["predict_next_yards_per_yard"]; pc = f["predict_ci"]; pay = f["musd_per_100_yards"]; pci = f["musd_per_100_yards_ci"]
    fut = f["musd_per_100_future_yards"]
    def lst(xs):
        return ", ".join(f"{x[0]} ({x[1]}, {x[2]:,.0f} yds, {x[3]:+.0f} YAC over expected)" for x in xs)
    return f"""# 08 The YAC Tax: do teams pay receivers for yards after the catch that won't come back?

**The question:** study 07 tested whether teams pay for sacks beyond what pressures predict. Receivers have the same shape of problem. A receiver's yards split three ways, using NFL Next Gen Stats tracking: air yards on his catches, the yards after the catch a typical receiver would get on those same catches (expected YAC), and **YAC above expected**, where broken tackles, missed angles and luck live. If YAC above expected repeats less than the rest but is paid like the rest, it is a tax.
**Data:** NFL Next Gen Stats receiving ({f['seasons']}, qualified receivers, {f['player_seasons']:,} player-seasons) and {f['market_contracts']} veteran WR/TE contracts from Over The Cap ({f['market_players']} players, signed 2019-2026), via [nflverse](https://github.com/nflverse/nflverse-data). Dollars in 2026 cap terms ($301.2M).
**Code:** [`projects/yac_tax.py`](../../projects/yac_tax.py)

## What I found
1. **Where the catch happens repeats; what happens after is shakier.** Year to year: depth of target r = {y['avg_intended_air_yards']:.2f}, separation r = {y['avg_separation']:.2f}, catch rate r = {y['catch_percentage']:.2f}, YAC per catch r = {y['avg_yac']:.2f}, **YAC above expected per catch r = {y['avg_yac_above_expectation']:.2f}** ({f['pairs']} back-to-back receiver seasons).
2. **A season of YAC above expected is not just luck.** Per catch it is noisy. Over a season each yard of it predicts {pr['yacoe_yds']:.2f} yards the next season (95% interval {pc['yacoe_yds'][0]:.2f}-{pc['yacoe_yds'][1]:.2f}), about the same as an air yard ({pr['air_yds']:.2f}).
3. **No YAC tax detected, and the test could not have seen a moderate one.** Contracts pay ${pay['yacoe_yds']:.2f}M a year per 100 yards of YAC above expected, ${pay['air_yds']:.2f}M per 100 air yards and ${pay['xyac_yds']:.2f}M per 100 expected-YAC yards. Per future yard that is ${fut['yacoe_yds']:.2f}M (YAC above expected, 90% interval ${f['musd_per_100_future_yards_ci90']['yacoe_yds'][0]:.2f}M to ${f['musd_per_100_future_yards_ci90']['yacoe_yds'][1]:.2f}M) against ${fut['air_yds']:.2f}M (air yards, ${f['musd_per_100_future_yards_ci90']['air_yds'][0]:.2f}M to ${f['musd_per_100_future_yards_ci90']['air_yds'][1]:.2f}M) per 100. The test ratio (relative price over relative prediction, 1.00 = fairly priced) is {f['tax_ratio']:.2f}, with a 90% interval of {f['tax_ratio_ci90'][0]:.2f} to {f['tax_ratio_ci90'][1]:.2f} from {f['tax_ratio_boot_n']:,} samples that resample players. That range runs from a discount of about half to a tax of about double, so this is a null result with low power, not proof the market is efficient.
4. **What that means for a front office.** The data gives no reason to discount a receiver's YAC as luck by default. The most stable traits are target depth and separation.
5. **The {f['fa_class']} free-agent receivers.** Contracts ending after {f['current_season']} (Over The Cap, extensions counted), still active: most {f['current_season'] - 1} yards came from {lst(f['fa_top_yards'][:4])}. Leaned most on YAC above expected (100+ yards): {lst(f['fa_leaned'])}. Given finding 2, that is a reason to look closer, not to pass.

![Stability](receiver_stability.png)
![Price vs prediction](yac_tax.png)

## Method
- **Yards split:** air yards on catches = yards - catches x YAC per catch; expected YAC = catches x NGS expected YAC per catch; YAC above expected = catches x NGS YAC above expectation per catch. The three add up to total receiving yards.
- **Prediction:** next season's yards on this season's three parts plus targets; **price:** APY as % of the cap on the platform season's three parts plus targets. Both cluster standard errors by player. Output in `models.txt`.
- **Contracts:** veteran WR/TE deals (rookie deals dropped; one deal per player-year, keeping the longer, then richer, deal when a tag and an extension share a year), at least 0.4% of the cap, platform season = the season before signing.
- **Test:** the same statistic as study 07: (price per YAC-over-expected yard / price per air yard) divided by (next-year yards per YAC-over-expected yard / per air yard), players resampled in both samples.
- **Free agents:** end year from each player's Over The Cap contract history, with extensions added after the deal they extend; first-round rookie deals (fifth-year option) left out; must have played offense this season.

## Limits
- NGS season tables only include qualified receivers, so part-time players and many tight ends are missing.
- Expected YAC is the NFL's model; the split is only as good as it is.
- The prediction sample needs a qualified season in back-to-back years ({f['pairs']} pairs from {f['qualified_seasons']:,} qualified seasons), so receivers who were hurt or lost their role drop out.
- Contract status can lag a new extension. Puka Nacua and George Pickens (franchise tag) were both in the final year of their deals as of this writing; check before acting.

## Files
`receivers_{f['current_season'] - 1}.csv`, `free_agents_{f['fa_class']}_receivers.csv`, `robustness_price_per_100_yards.csv`, `models.txt`, `findings.json`
"""


def run_game_value():
    f = F("09-run-game-value")
    y = f["yoy_r"]; ci = f["yoy_r_ci"]; po = f["portability"]; pay = f["musd_per_100_yards"]; pci = f["musd_per_100_yards_ci"]
    pr = f["predict_next_yards_per"]; pq = f["predict_next_ypc_per"]; pqc = f["predict_next_ypc_ci"]
    pp = f["musd_per_ypc_part"]; ppc = f["musd_per_ypc_part_ci"]; bs = f["boxscore_model"]; ne = f["r_next_epa"]; nec = f["r_next_epa_ci"]
    fa = f["fa_list"]; last = f["current_season"]; c150 = f["yoy_r_150car"]; cw = f["yoy_r_carry_weighted"]; rp = f["robust_p"]; rr = f["robust_ratio"]
    def yrs(s):
        return s.replace("+", " and ")
    def back(x):
        return f"{x[0]} ({x[1]}, {x[5]:+.2f} on {x[2]:.0f} carries, {yrs(x[9])})"
    pos = [x for x in fa if x[5] > 0]; neg = [x for x in fa if x[5] < 0]
    val = [x for x in fa if str(x[8]).startswith("value")]
    rem = f["fa_removed_after_news_check"]
    other = f["fa_other_100car"]; on = f["fa_other_notes"]
    return f"""# 09 Run Game Value: no mispricing found between the back's part and the blocked part, on a sample too small to rule one out

**The question:** Brett Kollmann's line is that the offensive line sets a back's floor and the back sets his ceiling. NFL Next Gen Stats lets that be measured. It splits every carry into the yards a typical back would gain given his blockers, the defenders, the box count and the space at the handoff (**expected yards**), and the yards he gains over that (**rush yards over expected, RYOE**). If RYOE is the back's part, it should repeat, follow him to a new team, predict next season and be what contracts pay for. My hypothesis going in was that teams pay backs for yards their blocking made as if the back had made them. It failed: contracts pay more for the back's part than for the blocking part, though they pay for both. The back's part also turned out noisier than I expected (most of the spread in yards per carry, but the part that repeats less), and I cannot show the market misprices either part.
**Inspired by:** Brett Kollmann, [The Running Back Problem.]({YT}PLGJLH4xQcA) and [Should Running Backs go in the Top 10?]({YT}8ymN2_OBGuE). Method mirrors studies [07](../07-box-score-tax/) and [08](../08-yac-tax/).
**Data:** NFL Next Gen Stats rushing ({f['seasons']}, qualified rushers only: {f['qualified_seasons']} back-seasons, {f['qualified_players']} backs), nflverse play-by-play {f['seasons'].split('-')[0]}-{last} (through Week {f['through_week']} of {last}), and {f['market_contracts']} veteran RB contracts from Over The Cap ({f['market_players']} backs, signed 2019-2026), all via [nflverse](https://github.com/nflverse/nflverse-data). Dollars in 2026 cap terms (${f['cap_2026_musd']}M).
**Code:** [`projects/run_game_value.py`](../../projects/run_game_value.py)

## What I found
1. **The blocking part of yards per carry repeats more than the back's part.** Year to year ({f['pairs']} back-to-back qualified seasons, {f['pair_players']} backs): expected yards per carry r = {y['xypc']:.2f} (95% interval {ci['xypc'][0]:.2f} to {ci['xypc'][1]:.2f}), raw yards per carry r = {y['ypc']:.2f}, RYOE per carry r = {y['ryoe_pc']:.2f} ({ci['ryoe_pc'][0]:.2f} to {ci['ryoe_pc'][1]:.2f}). The gap is positive in {100 * f['stability_gap_share_positive']:.0f}% of 1,000 bootstrap samples that resample backs, but it narrows for workhorse backs: with 150+ carries in both seasons ({c150['n']} pairs) it is {c150['xypc']:.2f} against {c150['ryoe_pc']:.2f}. RYOE makes up most of the spread in yards per carry ({100 * f['var_share_ypc']['ryoe']:.0f}% of its variance), yet of the yards per carry that carry into next season, {100 * f['share_of_repeatable_ypc_expected']:.0f}% comes through the expected part. Facing more eight-man boxes goes with fewer expected yards (r = {f['r_box8_xypc']:.2f}), and the box share itself repeats (r = {y['box8']:.2f}).
2. **Changing teams: neither part clearly travels better.** For backs who changed teams ({f['changers_n']} pairs), RYOE per carry repeated at r = {po['ryoe_pc']['changers']:.2f} ({po['ryoe_pc']['changers_ci'][0]:.2f} to {po['ryoe_pc']['changers_ci'][1]:.2f}) and expected yards per carry at r = {po['xypc']['changers']:.2f} ({po['xypc']['changers_ci'][0]:.2f} to {po['xypc']['changers_ci'][1]:.2f}); for those who stayed ({f['stayers_n']} pairs), {po['ryoe_pc']['stayers']:.2f} and {po['xypc']['stayers']:.2f}. The changer-minus-stayer differences have 95% intervals of {f['changer_minus_stayer_ci']['ryoe_pc'][0]:.2f} to {f['changer_minus_stayer_ci']['ryoe_pc'][1]:.2f} (RYOE) and {f['changer_minus_stayer_ci']['xypc'][0]:.2f} to {f['changer_minus_stayer_ci']['xypc'][1]:.2f} (expected yards): too few team changes to tell. Expected yards following a back to a new team at all says they are not only the line's; they also carry the back's role and how he is used.
3. **No rushing stat predicts next season's rushing EPA well.** Among {f['predict_epa_n']} qualified back-seasons followed by 100+ carries, expected yards per carry (r = {ne['xypc']:.2f}, {nec['xypc'][0]:.2f} to {nec['xypc'][1]:.2f}) and raw yards per carry (r = {ne['ypc']:.2f}) do best; this season's EPA per carry gives r = {ne['epa']:.2f} and RYOE per carry r = {ne['ryoe_pc']:.2f}. A model with four of them explains {100 * f['epa_model_r2']:.0f}% of next season's EPA per carry.
4. **Contracts pay more per yard for the back's part, not less.** In veteran deals, each 100 platform-year rush yards over expected is paid ${pay['ryoe_yds']:.2f}M a year (95% interval ${pci['ryoe_yds'][0]:.2f}M to ${pci['ryoe_yds'][1]:.2f}M) against ${pay['x_yds']:.2f}M per 100 expected yards (${pci['x_yds'][0]:.2f}M to ${pci['x_yds'][1]:.2f}M), holding rushing touchdowns and receiving yards fixed: {f['price_ratio_ryoe_to_expected_yard']:.2f} times as much (difference p = {f['price_diff_p']:.3f}). Teams pay for the expected part too; its interval excludes zero. The premium is fragile: it stays significant in {f['robust_diff_significant']} of {f['robust_n']} model versions, but falls to {rr['no receiving-yards control']:.2f} times without the receiving control (p = {rp['no receiving-yards control']:.2f}), {rr['plus platform carries']:.2f} times once platform carries are added (p = {rp['plus platform carries']:.2f}) and {rr['multi-year deals']:.2f} times in multi-year deals (p = {rp['multi-year deals']:.2f}). Per carry, +1 yard over expected per carry is paid ${pp['ryoe_pc']:.2f}M a year and +1 expected yard per carry ${pp['xypc']:.2f}M, holding carries, touchdowns and receiving fixed (difference p = {f['price_per_carry_diff_p']:.2f}). Seen through the box score, the market pays for yards per carry, not workload: with yards fixed, 100 more carries lowers pay by {_usd(abs(bs['musd_per_100_carries']))} a year (interval {_usd(abs(bs['carries_ci'][1]))} to {_usd(abs(bs['carries_ci'][0]))}), and RYOE per carry adds nothing measurable once yards and carries are known (R² +{f['r2_gain_from_ryoe']:.3f}). A rushing touchdown adds about ${f['musd_per_td']:.2f}M, and its 95% interval reaches zero (up to ${f['musd_per_td_ci'][1]:.2f}M).
5. **Per carry, both parts carry over about equally, so I can't call the premium a mistake.** Next season's yards per carry (backs with 50+ carries, weighted by carries, {f['predict_ypc_n']} back-seasons) rise {pq['ryoe_pc']:.2f} for each yard over expected per carry ({pqc['ryoe_pc'][0]:.2f} to {pqc['ryoe_pc'][1]:.2f}) and {pq['xypc']:.2f} for each expected yard per carry ({pqc['xypc'][0]:.2f} to {pqc['xypc'][1]:.2f}); the difference is not significant (p = {f['predict_next_ypc_diff_p']:.2f}). In season totals, a yard over expected comes back as {pr['ryoe_yds']:.2f} rushing yards next season and an expected yard as {pr['x_yds']:.2f}, but expected yards are mostly workload (r = {f['r_xyds_with_carries']:.2f} with carries), and a signing team sets the workload itself. Paid somewhat more and predicting slightly more per carry, the back's part looks roughly fairly priced. The evidence does not support a tax in either direction.
6. **The {f['fa_class']} free-agent backs.** Contracts ending after {last} (Over The Cap, extensions counted), active in {last}, first-round option deals left out, each name checked against news on November 12, 2026. {len(fa)} have 100+ carries in NGS season rows for {last - 1} and {last}; ranked by RYOE per carry, above expectation: {'; '.join(back(x) for x in pos)}. Below: {'; '.join(back(x) for x in neg)}. Value flags (RYOE over +0.3 a carry, at or below the list's median pay of ${f['fa_median_apy_musd']:.2f}M): {', '.join(x[0] for x in val)}. Kimani Vidal is a restricted free agent; Zach Charbonnet tore his ACL in the January 2026 playoffs; Brian Robinson Jr. went on injured reserve on November 7. Given finding 1, one or two seasons of RYOE per carry is a weak signal; the CSV also gives each back's RYOE shrunk toward zero, and the news note behind every name. {('Removed after the news check: ' + '; '.join(f'{a} ({b})' for a, b in rem) + '.') if rem else ''} {len(other)} more free-agent backs have 100+ carries in play-by-play but fewer than 100 in NGS season rows, so no RYOE: {'; '.join(f'{x[0]} ({x[1]}, {x[2]} carries: {on.get(x[0], "")})' for x in other)}.

![Stability](stability.png)
![Team changers](team_changers.png)
![Prediction](predict_epa.png)
![Price](rb_price.png)
![Free agents](free_agent_rbs.png)

## Method
- **Yards split:** for each back-season, RYOE = NGS `rush_yards_over_expected`; expected yards = rushing yards minus RYOE, so the two parts add to his rushing yards exactly. Per-carry versions divide both by all carries, so yards per carry = expected yards per carry + RYOE per carry. NGS's own expected-yards column runs about {f['ngs_untracked_yards_mean']:.0f} yards a season below this because a few carries have no tracking; using it instead leaves the price ratio about the same (see `robustness_price_per_100_yards.csv`).
- **Samples:** NGS season rows (week 0, regular season) list qualified rushers only; RYOE starts in 2018. EPA, success rate and touchdowns come from nflverse play-by-play (designed runs: `rush_attempt` with no QB scramble and no two-point try). "Changed teams" means the NGS team differs between seasons; {f['ngs_team_filled_from_pbp']} NGS rows with no team are filled with the team the back carried for most that season.
- **Prediction:** next season comes from play-by-play for every back. The season-total yards model counts zero for a back who did not carry the ball; the per-carry model uses backs with 50+ carries next season, weighted by those carries. Models cluster standard errors by player; output in `models.txt`.
- **Contracts:** veteran RB deals (rookie deals dropped), at least 0.4% of the cap, one deal per back per signing year (a tag or tender and a long-term deal in the same year count once, as the longer deal), platform season = the NGS-qualified season before signing. Pay is APY as a share of that year's cap, priced in 2026 dollars.
- **Free agents:** end year from each player's Over The Cap contract history (extensions added; the active deal wins a same-year tie), checked against news; RYOE combines the {last - 1} and {last} NGS season rows. RYOE shrunk toward zero adds about {f['ryoe_shrink_k_carries']} carries of league-average play, set by the year-to-year r of RYOE per carry.

## Limits
- The pricing test is inconclusive, not a clean bill for the market. With {f['market_contracts']} contracts, the per-carry price gap between the two parts is ${f['price_per_carry_diff_musd']:.2f}M (95% interval ${f['price_per_carry_diff_ci'][0]:.2f}M to ${f['price_per_carry_diff_ci'][1]:.2f}M), and the smallest gap this sample would find 80% of the time is about ${f['price_per_carry_min_detectable_musd']:.2f}M per yard per carry. On the prediction side the gap is {f['predict_next_ypc_diff']:.2f} yards per carry ({f['predict_next_ypc_diff_ci'][0]:.2f} to {f['predict_next_ypc_diff_ci'][1]:.2f}), and the smallest detectable gap is about {f['predict_next_ypc_min_detectable']:.2f}. A real mispricing smaller than those would not show up here.
- Only qualified rushers have NGS season rows (about 50 a season), so backups and part-time backs are missing and the samples are small ({f['pairs']} back-to-back pairs, {f['changers_n']} of them team changes, {f['market_contracts']} contracts).
- Expected yards is the NFL's model. It sees the blockers and defenders at the handoff, not how well the line sustains its blocks, so some line play sits inside RYOE; and it reflects the back's role and usage, so some of the back sits inside expected yards.
- A contract buys several years, pass protection and receiving; receiving yards are controlled for, pass protection is not measured.
- Back-to-back pairs need two qualified seasons, so backs who lost the job are missing from the stability numbers (the season-total yards prediction counts them, with zero yards).
- Over The Cap end years miss fifth-year option years on older first-round deals (Christian McCaffrey's case), which is why every name was checked by hand.

## Files
`back_to_back_seasons.csv`, `rb_contracts_with_platform.csv`, `robustness_price_per_100_yards.csv`, `free_agents_{f['fa_class']}_rbs.csv`, `free_agents_{f['fa_class']}_rbs_no_ngs.csv`, `models.txt`, `findings.json`
"""


REPORTS = [("01-flag-audit", flag_audit), ("02-fourth-down-bot", fourth), ("03-sack-leverage", sacks),
           ("04-luck-index", luck), ("05-kickoff-value", kickoff), ("06-pass-run", passrun), ("07-box-score-tax", box_score_tax), ("08-yac-tax", yac_tax),
           ("09-run-game-value", run_game_value)]


UPCOMING = [("09", "Run Game Value", "How much of a running back's production is his, and do contracts pay for that part?"),
            ("10", "Draft Value", "In rounds 3-7, which positions return the most value per pick?"),
            ("11", "Turnovers Forced", "Do defenses that force turnovers keep doing it, and does a takeaway-heavy year fool people?"),
            ("12", "Backup QB Value", "What is a good backup quarterback worth, in expected wins and in cap dollars?")]


def _html_badge(md):
    alt, url = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", md).groups()
    return f'<img src="{url}" alt="{alt}">'


def _n_tests():
    return sum((ROOT / "tests" / p.name).read_text().count("\ndef test_") for p in (ROOT / "tests").glob("test_*.py"))


SNIP = "2026-in-season-snippets"
WEB = "https://iforsurei.github.io/NFL-Analytics/snippets.html"


def _press(d):
    lo, hi = d["corr_ci"]
    r = d["corr_press_epa"]
    if lo < 0 < hi:
        return (f"So far there is no clear link between hitting the QB and EPA allowed per dropback (r = {r:.2f}, 95% interval {lo:.2f} to {hi:.2f} on 32 teams). "
                "The proxy counts only sacks and hits, so this says little about pressure itself.")
    return (f"Defenses that hit the QB more allow {'less' if r < 0 else 'more'} per dropback (r = {r:.2f}, 95% interval {lo:.2f} to {hi:.2f}), with a wide spread around the line.")


def snippets():
    """README for the in-season snippets folder; every number comes from its findings.json."""
    f = F(SNIP)
    w = f"Weeks {f['weeks'][0]}-{f['weeks'][1]}"
    q, rb, t, pr, rc, d = (f["qb_epa_cpoe"], f["rb_success"], f["team_tiers"], f["early_down_proe"],
                          f["receiver_share"], f["defense_pressure"])
    nm = lambda r: f"{r['name']} ({r['team']})"
    top = q["top3_epa"]
    r1 = rb["top5"]
    tt = t["top5_net"]
    rw = rc["top5_wopr"][0]
    a7, r8, y9, d10, p11, k12 = (f["qb_adot_yac"], f["receiver_epa_adot"], f["yac_over_expected"], f["defense_run_pass"],
                                 f["pass_rush_leaders"], f["kicker_fgoe"])
    pp = list(pr["most_pass_happy"].items())
    rh = list(pr["most_run_heavy"].items())
    return f"""# 2026 In-Season Snippets

Twelve quick charts on the season in progress, across positions, the kind a staff looks at on a Monday. Same data and code standard as the studies; lighter write-ups. Through **{w} of {f['season']}** (regular season, completed weeks only; {f['plays']:,} plays). Rebuilt on every weekly refresh.

**Interactive version:** [every chart on one page]({WEB}), where hovering (or tapping) any player or team opens the breakdown: a quarterback's efficiency by down and by throw depth, a back's success by down, a receiver's role and value by depth, a team's offense and defense split into run and pass, a pass rusher's and every team's week by week, a kicker's makes by distance.

| | |
|---|---|
| <img src="qb_epa_cpoe.png" width="100%"> | <img src="rb_success.png" width="100%"> |
| <img src="team_tiers.png" width="100%"> | <img src="early_down_proe.png" width="100%"> |
| <img src="receiver_share.png" width="100%"> | <img src="defense_pressure.png" width="100%"> |
| <img src="qb_adot_yac.png" width="100%"> | <img src="receiver_epa_adot.png" width="100%"> |
| <img src="yac_over_expected.png" width="100%"> | <img src="defense_run_pass.png" width="100%"> |
| <img src="pass_rush_leaders.png" width="100%"> | <img src="kicker_fgoe.png" width="100%"> |

## What each one says

1. **QB Efficiency: EPA vs. CPOE** ([chart](qb_epa_cpoe.png)). {nm(top[0])} leads in EPA per dropback ({top[0]['epa']:+.3f}), ahead of {nm(top[1])} ({top[1]['epa']:+.3f}). Accuracy and efficiency move together this year (r = {q['corr_epa_cpoe']:.2f}, 95% interval {q['corr_ci'][0]:.2f} to {q['corr_ci'][1]:.2f}, across {q['n_qbs']} QBs with 150+ dropbacks).
2. **Running Back Success Rate** ([chart](rb_success.png)). {r1[0]['rusher_player_name']} ({r1[0]['team']}) leads the {rb['n_qualified']} backs with 60+ carries at {pct(r1[0]['success'], 1)} of runs gaining positive EPA, ahead of {r1[1]['rusher_player_name']} ({r1[1]['team']}, {pct(r1[1]['success'], 1)}) and {r1[2]['rusher_player_name']} ({r1[2]['team']}, {pct(r1[2]['success'], 1)}). The RB average is {pct(rb['rb_average_success'], 1)}. On {r1[0]['carries']} carries the leader's 95% interval runs {pct(rb['leader_success_ci'][0])} to {pct(rb['leader_success_ci'][1])}, and only {rb['top30_clear_of_average']} of the top 30 are clearly above average, so the order inside the list is mostly noise this early. Success rate mixes a back's work with his blocking; [study 09](../09-run-game-value/) splits the two.
3. **2026 Team Tiers** ([chart](team_tiers.png)). Best net EPA per play: {tt[0]['team']} ({tt[0]['net']:+.3f}), {tt[1]['team']} ({tt[1]['net']:+.3f}), {tt[2]['team']} ({tt[2]['net']:+.3f}).
4. **Early-Down Pass Rate Over Expected** ([chart](early_down_proe.png)). {pp[0][0]} throws {100 * pp[0][1]:+.1f} points over expectation in neutral early downs; {rh[-1][0]} sits at {100 * rh[-1][1]:+.1f}. Teams that throw more than expected also have the better offenses so far (r = {pr['corr_proe_off_epa']:.2f} with offensive EPA per play, 95% interval {pr['corr_ci'][0]:.2f} to {pr['corr_ci'][1]:.2f} on 32 teams). [Study 06](../06-pass-run/) finds the same direction across {F('06-pass-run')['team_seasons_pooled']} team-seasons, at a smaller r = {F('06-pass-run')['team_corr_pooled'][0]:.2f}. It is a correlation: good passing teams choose to pass.
5. **Receiver Roles: Targets vs. Air Yards** ([chart](receiver_share.png)). {rw['receiver_player_name']} ({rw['team']}) carries the league's biggest role: {pct(rw['tgt_share'])} of targets and {pct(rw['air_share'])} of air yards (WOPR {rw['wopr']:.2f}). Points above the dashed line are used downfield; points below it are volume options on shorter throws.
6. **Pass Defense: Pressure vs. Results** ([chart](defense_pressure.png)). {_press(d)}

7. **Where QB Yards Come From** ([chart](qb_adot_yac.png)). {a7['most_yac'][0]['name']} ({a7['most_yac'][0]['team']}) gets {pct(a7['most_yac'][0]['yac_share'])} of his passing yards after the catch on a {a7['most_yac'][0]['adot']:.1f}-yard average depth of target. The shorter the throws, the bigger the YAC share (r = {a7['corr_adot_yac_share']:.2f}, 95% interval {a7['corr_ci'][0]:.2f} to {a7['corr_ci'][1]:.2f}), so a high YAC share is a style, not a skill by itself.
8. **Receivers: Role vs. Value** ([chart](receiver_epa_adot.png)). Among the {r8['n']} most-targeted receivers, {r8['top5_epa_per_target'][0]['receiver_player_name']} ({r8['top5_epa_per_target'][0]['team']}) adds the most per target ({r8['top5_epa_per_target'][0]['epa']:+.2f} EPA on a {r8['top5_epa_per_target'][0]['adot']:.1f}-yard depth). Deeper roles earn somewhat more per target (r = {r8['corr_adot_epa']:.2f}, 95% interval {r8['corr_ci'][0]:.2f} to {r8['corr_ci'][1]:.2f}), so compare a receiver with others at his depth.
9. **YAC Over Expected per Catch** ([chart](yac_over_expected.png)). {y9['top5'][0]['receiver_player_name']} ({y9['top5'][0]['team']}) gains {y9['top5'][0]['yacoe']:+.2f} yards after the catch beyond what the nflverse xYAC model expects per reception, then {y9['top5'][1]['receiver_player_name']} ({y9['top5'][1]['team']}, {y9['top5'][1]['yacoe']:+.2f}). The minimum is {y9['min_catches']} catches, which is thin: the leader's 95% interval is {y9['leader_ci'][0]:+.2f} to {y9['leader_ci'][1]:+.2f}, and {y9['top30_clear_of_league']} of the top 30 {'is' if y9['top30_clear_of_league'] == 1 else 'are'} clearly above the league mean. [Study 08](../08-yac-tax/) uses full seasons for this reason.
10. **Defense: Run Stopping vs. Pass Defense** ([chart](defense_run_pass.png)). Best run defense by EPA per run allowed: {", ".join(list(d10['best_run_d'])[:3])}; best pass defense: {", ".join(list(d10['best_pass_d'])[:3])}. The two go together loosely (r = {d10['corr_run_pass']:.2f}, 95% interval {d10['corr_ci'][0]:.2f} to {d10['corr_ci'][1]:.2f}).
11. **Pass Rush Leaders** ([chart](pass_rush_leaders.png)). {p11['top5'][0]['name']} ({p11['top5'][0]['team']}) has a sack or QB hit on {p11['top5'][0]['events']} plays, ahead of {' and '.join(r['name'] + ' (' + r['team'] + ')' for r in p11['top5'][1:] if r['events'] == p11['top5'][1]['events'])} with {p11['top5'][1]['events']} each. [Study 07](../07-box-score-tax/) showed hits and pressures predict future sacks better than sacks do, which is why this counts both.
12. **Kickers: FG Points Over Expected** ([chart](kicker_fgoe.png)). {k12['top3'][0]['kicker_player_name']} ({k12['top3'][0]['team']}, {k12['top3'][0]['made']}-{k12['top3'][0]['att']}) is {k12['top3'][0]['fgoe_pts']:+.1f} points above what an average kicker makes from the same distances; the expected rate comes from a distance-and-roof model fit on {k12['model_kicks']:,} kicks from 2022-25. An average kicker would land within about {k12['leader_chance_band_pts']:.1f} points of zero on those same kicks 95% of the time, and {k12['outside_chance_band']} of the {k12['n']} kickers with {k12['min_attempts']}+ attempts sit outside their own band. Read this as who has made their kicks, not who is the better kicker.

## Method notes

- Data: [nflverse](https://github.com/nflverse/nflverse-data) play-by-play (EPA, CPOE, xpass from the nflfastR models) and nflverse team colors. Teams are drawn as color-coded markers with abbreviations.
- A week counts once all of its games are in the file; a week in progress is left out.
- Dropbacks include sacks and scrambles; two-point tries and penalty no-plays are excluded.
- Field-goal model: logistic regression on distance, distance squared and a dome flag (regular seasons 2022-25). Blocked kicks count as misses.
- Pressure proxy = sack or QB hit. Play-by-play has no hurries, so this undercounts pressure; treat it as a rate comparison between teams, not a pressure rate.
- Early-down PROE: 1st and 2nd down, win probability 20-80%, outside the last two minutes of each half.
- Receiver shares are computed over the games each player appeared in (so injuries don't shrink them).
- Small samples: part of a season is early. These are snapshots, not projections. Rankings use minimum samples (150 dropbacks, 60 carries, 25 catches, 8 field-goal attempts) and most gaps inside a list are within noise.
- Correlation intervals are 95%, from resampling the players or teams on the chart 2,000 times. With 32 teams they are wide.
- Nothing here is adjusted for opponent or game script.

## Reproduce

```bash
python -m projects.in_season_snippets --refresh   # re-downloads the season in progress
```

Code: [`projects/in_season_snippets.py`](../../projects/in_season_snippets.py). Numbers: [`findings.json`](findings.json).
"""


def snippets_section():
    p = R / SNIP / "findings.json"
    if not p.exists():
        return ""
    f = F(SNIP)
    figs = ["qb_epa_cpoe", "team_tiers", "early_down_proe", "receiver_share", "rb_success", "defense_pressure"]
    cells = "".join(f'<td width="33%"><a href="reports/{SNIP}/"><img src="reports/{SNIP}/{x}.png" width="100%"></a></td>' for x in figs[:3])
    cells2 = "".join(f'<td width="33%"><a href="reports/{SNIP}/"><img src="reports/{SNIP}/{x}.png" width="100%"></a></td>' for x in figs[3:])
    return (f"\n## 2026 in-season snippets\n\nTwelve quick charts on the season in progress, through Weeks {f['weeks'][0]}-{f['weeks'][1]}: "
            f"QB, running back, receiver, pass rusher, defense, kicker and team views. "
            f"[See them all](reports/{SNIP}/). "
            f"**Hover for the breakdown:** the [interactive version]({WEB}) opens every player's and team's numbers by down, by depth and week by week.\n\n<table><tr>{cells}</tr><tr>{cells2}</tr></table>\n")


DRAFT = "draft-2027-drew-mestemaker"


def draft_section():
    """Link to the draft evaluation (built by projects/draft_mestemaker.py); numbers from its findings.json."""
    p = R / DRAFT / "findings.json"
    if not p.exists():
        return ""
    f = F(DRAFT)
    L, o = f["line"], f["opp"]
    me = o["cls"][0]
    band = next(b for b in f["base_rate"] if b["his_band"])
    return (f"\n## Draft board: 2027 quarterbacks\n\n[**Drew Mestemaker, QB, Oklahoma State: is he QB1?**](reports/{DRAFT}/) "
            f"NFL scouts have him first. Through {L['G']} games he has {L['Yards']:,} yards and {L['TD']} touchdowns, but against what his opponents allow he is "
            f"{me['over']:+.1f} rating points over expected, #{o['class_rank']} of {o['class_n']} in the class and below the first-round median ({o['fr_median']:+.1f}). "
            f"The evaluation uses nine-game comparisons with every first-round quarterback since 2021, an opponent adjustment, base rates "
            f"({band['round1']} of {band['n']} quarterbacks with a rating like his went in round 1) and a test of which numbers repeat.\n\n"
            f'<p align="center"><a href="reports/{DRAFT}/"><img src="reports/{DRAFT}/opponent_adjusted.png" width="720"></a></p>\n')


def _refreshed():
    """Date of the last data refresh in LOG.md (a new study is not a refresh); today if none is logged."""
    for l in reversed((ROOT / "LOG.md").read_text().splitlines()):
        if l.startswith("- 20") and l[14:].lower().startswith("weekly refresh"):   # the entry itself, not a study line that mentions one
            return date.fromisoformat(l[2:12])
    return date.today()


def top_readme():
    f2 = F("02-fourth-down-bot")
    g = f2["go_rate_clear_spots"]; ys = sorted(g)
    done = {s[:2] for s, _ in REPORTS}
    rows = []
    for slug, _ in REPORTS:
        m = META.get(slug, {})
        f = F(slug)
        t = m["tldr"](f)[m.get("headline", 0)] if m else ""
        rows.append(f"| {slug[:2]} | [**{m.get('short', slug)}**](reports/{slug}/) | {m.get('question', '')} | {t} | {', '.join(m.get('tags', []))} |")
    cells = []
    for slug, _ in REPORTS:
        m = META.get(slug, {})
        hero = m.get("hero", ("", ""))[0]
        cells.append(f'<td width="25%" valign="top"><a href="reports/{slug}/"><img src="reports/{slug}/{hero}" width="100%"></a><br><sub><b>{slug[:2]} {m.get("short", slug)}</b></sub></td>')
    gallery = "<table>\n" + "\n".join("<tr>" + "".join(cells[i:i + 4]) + "</tr>" for i in range(0, len(cells), 4)) + "\n</table>"
    up = [u for u in UPCOMING if u[0] not in done]
    upcoming = ("\n## Coming next\n\nNew studies are on the way; each follows the same [report standard](docs/report-standard.md).\n\n| # | Study | The question |\n|---|---|---|\n"
                + "\n".join(f"| {n} | {t} | {q} |" for n, t, q in up) + "\n") if up else ""
    log = [l for l in (ROOT / "LOG.md").read_text().splitlines() if l.startswith("- ")][-3:]
    badges = " ".join(_html_badge(b) for b in [
        badge("python", "3.10+", "1d2433"),
        badge("data", f"nflverse 2006-{ys[-1]}", "1d2433"), badge("studies", str(len(REPORTS)), "c2410c"),
        badge("refreshed", f"{_refreshed():%b %d %Y}", "6b7280"), badge("license", "all rights reserved", "6b7280")])
    ci = f'<a href="{REPO}/actions/workflows/tests.yml"><img src="{REPO}/actions/workflows/tests.yml/badge.svg" alt="tests"></a>'
    return f"""<p align="center"><img src="assets/banner.png" alt="NFL Analytics by Dylan Fanelli" width="100%"></p>

<p align="center">{ci} {badges}</p>

<p align="center"><b><a href="#the-studies">Studies</a> &nbsp;|&nbsp; <a href="#what-a-club-gets">What a club gets</a> &nbsp;|&nbsp; <a href="#how-i-work">How I work</a> &nbsp;|&nbsp; <a href="#under-the-hood">Under the hood</a> &nbsp;|&nbsp; <a href="docs/glossary.md">Glossary</a> &nbsp;|&nbsp; <a href="#about">About</a></b></p>

I'm Dylan Fanelli, and this is the NFL analytics portfolio I am building toward a job in a club front office. Each study starts from a question a coach, scout or general manager actually argues about, answers it with public data and a model I built, and ends with what a club would do with the answer. I test each model out of sample or with a bootstrap where the data allows and say so where it does not, I say what the data can't show, and the numbers on the study pages are written by code from each study's `findings.json`, not typed by hand.

**Headline work:** a [fourth-down decision bot](reports/02-fourth-down-bot/) on my own win-probability model, which comes close to nflfastR out of sample without beating it (Brier {f2['brier_ours']:.4f} vs {f2['brier_nflfastR_vegas_wp']:.4f} on {f2['wp_test_plays']:,} plays), and a [test of whether teams overpay for sacks](reports/07-box-score-tax/): a sack beyond what pressures predict adds about ${F('07-box-score-tax')['musd_per_lucky_sack_2026']:.2f}M a year to a contract, and against a pressure it is priced {F('07-box-score-tax')['tax_ratio']:.1f} times what it predicts (90% interval {F('07-box-score-tax')['tax_ratio_ci90'][0]:.1f} to {F('07-box-score-tax')['tax_ratio_ci90'][1]:.1f}).

<p align="center"><img src="assets/at-a-glance.png" alt="Selected studies at a glance" width="100%"></p>

<p><img src="assets/img/strip-helmets.jpg" width="100%" alt="All 32 NFL helmets on one wall"></p>

## The studies

| # | Study | The question | Headline | Methods |
|---|---|---|---|---|
{chr(10).join(rows)}

{gallery}
{snippets_section()}{draft_section()}{upcoming}
<a id="what-a-club-gets"></a>
## What a club gets

| Department | Question it answers | Study |
|---|---|---|
| Head coach and game management | Go, kick or punt on this fourth down? | [02 Fourth-Down Bot](reports/02-fourth-down-bot/) |
| Pro personnel and free agency | Are pass rushers, receivers and running backs priced for what repeats? Who to target in free agency? | [07 Box-Score Tax](reports/07-box-score-tax/), [08 YAC Tax](reports/08-yac-tax/), [09 Run Game Value](reports/09-run-game-value/) |
| Defensive staff | When is a sack worth the most? | [03 Sack Leverage](reports/03-sack-leverage/) |
| Offensive staff | Should we pass more on early downs? | [06 Pass vs Run](reports/06-pass-run/) |
| Special teams | What is a kickoff worth under the new rule, and can returners or kickers be told apart yet? | [05 Kickoff Value](reports/05-kickoff-value/) |
| Front office and ownership | How much of our record will carry over, and how much was the bounces? | [04 Luck Index](reports/04-luck-index/) |
| Game prep | What does this crew call, and where does the road flag gap sit? | [01 Flag Audit](reports/01-flag-audit/) |

<a id="how-i-work"></a>
## How I work

Every study follows the same [report standard](docs/report-standard.md), modeled on how Big Data Bowl entries, Open Source Football articles and the nflverse model write-ups are built:

1. **A question first,** stated before the data, with prior public work credited.
2. **Stability before value.** A stat has to repeat before it can be called a skill or priced.
3. **Validation in the open:** out-of-sample tests, calibration, bootstraps, clustered standard errors and robustness tables.
4. **Results under headings that state the finding,** each with its figure.
5. **What a club does with it,** limitations and next steps on every page.
6. **Reproducible:** one command re-downloads the data and rebuilds the studies, charts and pages; `pytest` (run by GitHub Actions on every change, Python 3.10 and 3.12) tests the model and study logic on small made-up tables, checks that saved results are internally consistent, and checks that every page meets the standard. The tests do not prove a finding is right.

**Techniques used here:** gradient-boosted win probability with monotone constraints; decision analysis; expected points (EPA); empirical-Bayes shrinkage and Wilson intervals; split-half and year-to-year reliability; OLS with player-clustered standard errors; bootstrap resampling; Pythagorean expectation; contract valuation in cap-share terms; DuckDB SQL.

<a id="under-the-hood"></a>
## Under the hood

```mermaid
flowchart LR
    A[nflverse data<br>play-by-play, NGS, PFR,<br>Over The Cap, snaps] --> B[nflan library<br>loaders, WP model,<br>4th-down bot, stats]
    B --> C[projects/<br>one script per study]
    C --> D[reports/<br>findings.json, CSVs, charts]
    D --> E[scripts/build_readmes.py<br>scripts/build_figures.py]
    E --> F[README pages]
    B --> G[pytest<br>logic tests on made-up data,<br>consistency and page checks]
    D --> G
```

```
nflan/          library: data loading, win-probability model, 4th-down bot, penalty and stats helpers (unit-tested in tests/)
projects/       one script per study (python -m projects.<name>)
reports/        each study's write-up, figures, CSV outputs and findings.json
sql/            DuckDB queries answering the same questions straight from the parquet files
scripts/        update.py (weekly refresh), build_readmes.py, build_figures.py, report_meta.py
tests/          logic tests on made-up data, consistency checks on saved results, page-standard checks
docs/           report standard, glossary, data dictionary, inspiration notes
assets/         banner and at-a-glance figure
```

### Reproduce

```bash
pip install -r requirements.txt
python scripts/update.py          # downloads nflverse data (about 400 MB), runs every study, figures, tests and READMEs (the fourth-down bootstrap takes a while)
pytest -q
```

Each study also runs alone, for example `python -m projects.fourth_down_bot`.

## Data, glossary and credit

- Data: [nflverse](https://github.com/nflverse/nflverse-data) (CC-BY 4.0): play-by-play with nflfastR's EPA and win-probability models, officials, NFL Next Gen Stats, Pro Football Reference advanced stats, snap counts and Over The Cap contracts. See the [data dictionary](docs/data-dictionary.md).
- Terms used on these pages (EPA, WP, Brier score, PROE, clustered standard errors and more): [glossary](docs/glossary.md).
- Fourth-down method: the public idea behind [nfl4th](https://github.com/nflverse/nfl4th) by Ben Baldwin, rebuilt from scratch in Python.
- Inspiration: **Michael MacKelvie** (data storytelling) and **Brett Kollmann** (film plus numbers); each report links the video that started it. Notes in [`docs/inspiration.md`](docs/inspiration.md).
- All analysis, and any mistakes, are mine.

## Changelog

{chr(10).join(log)}

Full history: [LOG.md](LOG.md). Data refreshes weekly in season (last: {_refreshed():%B %d, %Y}, through the latest completed week of {ys[-1]}).

## License and citation

© 2026 Dylan Fanelli. All rights reserved. The code, reports and figures may be viewed here; they may not be copied, modified or used without written permission. See [LICENSE](LICENSE). To cite this work, use the **Cite this repository** button (from [CITATION.cff](CITATION.cff)).

<a id="about"></a>
## About

<table>
<tr>
<td width="32%" valign="top"><img src="assets/img/about-nfl.jpg" width="100%" alt="Dylan Fanelli at the NFL offices in New York City"><br><sub>At the NFL offices in New York City</sub></td>
<td valign="top">

Dylan Fanelli, M.S. Sport Management candidate at UMass Amherst (Mark H. McCormack Department). I am building this portfolio to show proficiency in NFL statistics and sabermetrics-style analysis.

I also keep a [baseball analytics portfolio](https://github.com/IForSureI/Dylan-Fanelli-Baseball-Analytics-Portfolio). [LinkedIn](https://www.linkedin.com/in/dylanfanelli/)

<sub>Photos are my own.</sub>

</td>
</tr>
</table>
"""

# ---------------------------------------------------------------------------------------------
# Presentation layer: every study README follows docs/report-standard.md
# ---------------------------------------------------------------------------------------------
import re  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_meta import META  # noqa: E402

REPO = "https://github.com/IForSureI/NFL-Analytics"
COLORS = {"status": "0b6e4f", "seasons": "1d2433", "method": "c2410c"}


def badge(label, msg, color):
    enc = lambda t: t.replace("-", "--").replace("_", "__").replace(" ", "%20").replace("/", "%2F").replace("+", "%2B")
    return f"![{label}: {msg}](https://img.shields.io/badge/{enc(label)}-{enc(msg)}-{color})"


def _split(body):
    """Split a study body into title, preamble lines, numbered findings, method/limits/files sections."""
    lines = body.strip("\n").split("\n")
    title = lines[0].lstrip("# ").strip()
    sec, cur = {"pre": []}, "pre"
    for ln in lines[1:]:
        m = re.match(r"^## (.+)$", ln)
        if m:
            cur = m.group(1).strip(); sec[cur] = []
        else:
            sec[cur].append(ln)
    found = "\n".join(sec.get("What I found", []))
    figs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", found)
    found = re.sub(r"^!\[[^\]]*\]\([^)]+\)\s*$", "", found, flags=re.M)
    items = re.findall(r"^(\d+)\. \*\*(.+?)\*\*\s*(.*)$", found, flags=re.M)
    method_key = next((k for k in sec if k not in ("pre", "What I found", "Limits", "Files")), None)
    return title, [l for l in sec["pre"] if l.strip()], items, figs, sec.get(method_key, []), method_key, sec.get("Limits", []), sec.get("Files", [])


def _fig(slug, file, cap):
    return f'<p align="center"><img src="{file}" width="720" alt="{cap}"></p>\n<p align="center"><sub>{cap}</sub></p>'


def wrap(slug, body, idx):
    m = META.get(slug)
    if m is None:
        return body
    f = F(slug)
    title, pre, items, figs, method, method_key, limits, files = _split(body)
    num, name_rest = title.split(" ", 1)
    name, sep, sub = name_rest.partition(": ")
    prev_s = REPORTS[idx - 1][0] if idx > 0 else None
    next_s = REPORTS[idx + 1][0] if idx + 1 < len(REPORTS) else None
    nav = [f"[← Portfolio](../../README.md)"]
    if prev_s:
        nav.append(f"[← {prev_s[:2]} {META.get(prev_s, {}).get('short', prev_s)}](../{prev_s}/)")
    if next_s:
        nav.append(f"[{next_s[:2]} {META.get(next_s, {}).get('short', next_s)} →](../{next_s}/)")
    navline = " &nbsp;|&nbsp; ".join(nav)
    out = [f"<sub>{navline}</sub>", "", f"# {num} {name}", f"### {sub[0].upper() + sub[1:]}" if sub else "", ""]
    out.append(" ".join([badge("status", "published", COLORS["status"]), badge("seasons", m["seasons"](f), COLORS["seasons"])]
                        + [badge("method", t, COLORS["method"]) for t in m["tags"]]))
    out += ["", "**TL;DR**", ""]  # a bold heading and a plain list, never a quote block (GitHub draws a side bar)
    for t in (m["tldr"](f) if "tldr" in m else [lead for _, lead, _ in items[:5]]):
        out.append(f"- {t}")
    out += ["", _fig(slug, *m["hero"]), ""]
    out += ["## Key numbers", "", "| Measure | Value |", "|---|---|"] + [f"| {a} | **{b}** |" for a, b in m["key"](f)] + [""]
    out += ["## Why it matters for a club", ""] + [f"- {w}" for w in m["why"]] + [""]
    out += ["## The question", "", f"**{m['question']}**", ""]
    for l in pre:
        if l.startswith("**The question:**"):
            t = l.replace("**The question:**", "").strip()
            t = t.split("? ", 1)[1] if t.lower().startswith("where is value hiding") else t
            out += [t[0].upper() + t[1:], ""]
    for l in pre:
        if not l.startswith(("**Data:**", "**Code:**", "**The question:**")):
            out.append(l + "  ")
    out += [""]
    data = next((l for l in pre if l.startswith("**Data:**")), None)
    if data:
        out += ["## Data", "", data.replace("**Data:**", "").strip(), ""]
    out += ["## Results", ""]
    placed = {m["hero"][0]}
    for n, lead, text in items:
        out += [f"### {n}. {lead}", "", text.strip(), ""]
        for file, cap in m["figs"].get(int(n), []):
            out += [_fig(slug, file, cap), ""]; placed.add(file)
    rest = [x for x in figs if x not in placed and all(x != q for v in m["figs"].values() for q, _ in v)]
    for x in rest:
        out += [_fig(slug, x, ""), ""]
    out += [f"## {'Method' if method_key in (None, 'Method') else method_key}", ""] + [l for l in method if l.strip()] + [""]
    if m.get("method_eq"):
        out += ["**In equations**", ""]
        for e in m["method_eq"]:
            out += ["- " + re.sub(r"\$([^$`]+)\$", lambda q: "$`" + q.group(1).strip() + "`$", e)]
        out += [""]
    out += ["## Validation", ""] + [f"- {v}" for v in m["validation"](f)] + [""]
    out += ["## Limitations", ""] + [l for l in limits if l.strip()] + [""]
    out += ["## Next steps", ""] + [f"- {x}" for x in m["next"]] + [""]
    code = next((l for l in pre if l.startswith("**Code:**")), "")
    mod = re.search(r"projects/(\w+)\.py", code)
    out += ["## Reproduce", "", "```bash", "pip install -r requirements.txt",
            f"python -m projects.{mod.group(1)}" if mod else "python scripts/update.py --no-download", "```",
            code.replace("**Code:**", "Code:").strip(), ""]
    out += ["## Files in this folder", "", "| File | What it holds |", "|---|---|"]
    ftxt = " ".join(files)
    listed = re.findall(r"`([^`]+)`", ftxt)
    descs = dict(m["files"])
    for k in descs:
        if k not in listed and (R / slug / k).exists():
            listed.append(k)
    for fn in listed:
        if fn == "findings.json":
            continue
        real = fn.replace("<season>", str(f.get("current_season", ""))) if "<" in fn else fn
        d = descs.get(real) or descs.get(fn) or next((v for k, v in descs.items() if k.split("_20")[0] == fn.split("_<")[0].split("_20")[0]), "")
        out.append(f"| [`{fn}`]({real if (R / slug / real).exists() else ''}) | {d} |".replace("[`" + fn + "`]()", "`" + fn + "`"))
    out.append("| [`findings.json`](findings.json) | Every number quoted on this page, machine-readable |")
    out += ["", "---", f"<sub>{navline}</sub>", "",
            f"<sub>© 2026 Dylan Fanelli. All rights reserved. To cite: Fanelli, D. (2026). *{name}*. NFL Analytics. {REPO}/tree/main/reports/{slug}</sub>", ""]
    return "\n".join(x for x in out if x is not None)


def money(md):
    """Escape currency dollar signs so GitHub does not read '$0.62M ... $3.92M' as inline math."""
    return re.sub(r"(?<!\\)\$(?=-?\d)", r"\\$", md)


def main():
    for i, (slug, fn) in enumerate(REPORTS):
        (R / slug / "README.md").write_text(money(wrap(slug, fn(), i)))
    if (R / SNIP / "findings.json").exists():
        (R / SNIP / "README.md").write_text(money(snippets()))
    (ROOT / "README.md").write_text(money(top_readme()))
    print("READMEs written")


if __name__ == "__main__":
    main()
