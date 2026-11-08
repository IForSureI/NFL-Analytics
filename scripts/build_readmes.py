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
    a = f.get("rtp_above_league", [])
    if not a:
        return "Every interval overlaps the league rate."
    names = a[0] if len(a) == 1 else ", ".join(a[:-1]) + " and " + a[-1]
    return f"Only {names} {'sits' if len(a) == 1 else 'sit'} clearly above the league rate (95% interval); everyone else overlaps it."


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
1. **The road team's extra judgment-call flags are gone.** In {old}, road teams drew {era[old + ',subjective']:.2f} more subjective flags per game than home teams (holding, pass interference, roughing). Since 2023 the gap is {era[new + ',subjective']:.2f}.
2. **The road gap that remains is noise and communication, not referees' judgment.** Road teams still take about {era[new + ',objective']:.2f} extra rule-book flags a game. Neutral zone infractions go against the road defense {pct(sk.get('Neutral Zone Infraction', 0))} of the time, and delay of game against the road offense {pct(sk.get('Delay of Game', 0))}. False starts, the flag fans blame on crowd noise, split almost evenly ({pct(f['false_start_road_share'], 1)} on the road team).
3. **Referee crews have a real, modest style.** A crew's flags per game this season predicts next season at r = {f['crew_yoy_r']:.2f} ({f['crew_pairs']} back-to-back crew seasons). In {f['crew_latest_season']}, {crew[1]}'s crew averaged {crew[0]:.1f} flags a game and {crew[3]}'s averaged {crew[2]:.1f}.
4. **A team's flag luck does not carry over.** Within a season, a team's net subjective flags (drawn minus committed) in odd weeks predicts even weeks at only r = {f['split_r_net']:.2f}. Committing flags is a bit more stable (r = {f['split_r_committed']:.2f}) than drawing them (r = {f['split_r_drawn']:.2f}): discipline is partly real, getting calls is mostly not.
5. **Mahomes is not the roughing-flag king.** Among {mah[2]} QBs with 1,500+ dropbacks since 2018, he ranks #{mah[1]} (by shrunk rate) at {mah[0]:.2f} roughing flags per 100 dropbacks, about the league rate of {f['rtp_league_per100']:.2f}. The top of the list is {top[0][0]} ({top[0][3]:.2f} raw), {top[1][0]} ({top[1][3]:.2f}) and {top[2][0]} ({top[2][3]:.2f}). {_above(f)}
6. **Big calls are real but random.** {f['big_calls']:,} accepted flags ({f['big_calls_reg']:,} in the regular season) moved win probability by 10+ points, about {f['big_calls_per_full_season_reg']:.0f} per full regular season. Pass interference leads. A team's net big calls this year predicts next year at r = {f['big_call_net_yoy_r']:.2f}: no team is owed them.

![Home edge](home_edge.png)
![Crew stability](crew_stability.png)
![Roughing](qb_roughing.png)

## Method
- **Objective vs subjective:** objective flags are facts at the snap (alignment, motion, clock); subjective flags need a judgment about contact or intent. The lists are in [`nflan/penalties.py`](../../nflan/penalties.py).
- **Crews:** the referee's name stands for the crew (officials table, position = Referee). Regular-season crews with 10+ games.
- **Split-half reliability:** for each team-season, the odd-week mean vs the even-week mean.
- **Roughing:** flags drawn per dropback, with Wilson 95% intervals and empirical-Bayes shrinkage so small samples are not ranked on noise.

## Limits
- Play-by-play has no tracking data, so this cannot judge whether a single flag was correct.
- "Big call" uses nflfastR's WPA, which measures the flag plus the play it wiped out.

## Files
`home_edge_by_season.csv`, `home_edge_by_era.csv`, `objective_road_skew_by_type.csv`, `crew_flags_per_game.csv`, `qb_roughing_drawn.csv`, `big_calls_team_season.csv`, `findings.json`
"""


def fourth():
    f = F("02-fourth-down-bot")
    g = f["go_rate_clear_spots"]; ys = sorted(g)
    last_full = ys[-2]
    mc = f["most_costly"]; lc = f["least_costly"]
    return f"""# 02 Fourth-Down Bot: who leaves wins on the table?

**Inspired by:** Brett Kollmann, [Are analytics ruining football?]({YT}FOnQFk5qy-4) (judge the decision apart from the play), and Michael MacKelvie, [Passing is better...so, why run?]({YT}pPXZlK9puqw) (coaches lag the math). Method follows the public idea of Ben Baldwin's [nfl4th](https://github.com/nflverse/nfl4th), rebuilt from scratch in Python.
**Data:** nflverse play-by-play 2006-{ys[-1]}.
**Code:** [`nflan/wp.py`](../../nflan/wp.py), [`nflan/fourth.py`](../../nflan/fourth.py), [`projects/fourth_down_bot.py`](../../projects/fourth_down_bot.py)

## What I found
1. **The win-probability model holds up out of sample.** Trained on 2006-2023 and tested on {f['wp_test_plays']:,} plays from 2024-25: Brier score {f['brier_ours']:.4f}, against {f['brier_nflfastR_vegas_wp']:.4f} for nflfastR's spread-adjusted model on the same plays (lower is better). The two agree at r = {f['corr_with_nflfastR']:.3f}. Calibration sits close to the 45-degree line (most bins within 2 points).
2. **Coaches go for it far more than they used to, and still not enough.** In clear "go" spots (going adds 2+ win-probability points, score within 16, outside the last 5 minutes), teams went {pct(g[ys[0]])} of the time in {ys[0]} and {pct(g[last_full])} in {last_full}. {ys[-1]} so far: {pct(g[ys[-1]])}.
3. **{f['scorecard_season']} report card (regular season).** Most win probability lost per game on clear 4th-down calls: {mc[0][0]} ({mc[0][1]:.1f} points), {mc[1][0]} ({mc[1][1]:.1f}), {mc[2][0]} ({mc[2][1]:.1f}). Least: {lc[-1][0]} ({lc[-1][1]:.1f}), {lc[-2][0]} ({lc[-2][1]:.1f}), {lc[-3][0]} ({lc[-3][1]:.1f}). Totals add up small misses, so read them as a ranking, not an exact count of lost wins.
4. **Sanity checks pass.** 4th-and-1 at midfield, tied, early, even teams: going adds {f['sanity_4th1_midfield_go_boost']:.1f} WP points. 4th-and-10 at your own 20: going costs {abs(f['sanity_4th10_own20_go_boost']):.1f}.

![Go rate](go_rate_trend.png)
![Scorecard](team_scorecard.png)
![Calibration](wp_calibration.png)

## How the bot works
- **Win probability:** gradient-boosted trees on score, clock, field position, down and distance, timeouts, the second-half kickoff and the point spread. Like nflfastR, the spread fades as the game goes on and a lead counts more late. Monotone constraints keep it football-logical (more points ahead never lowers WP).
- **Go:** P(convert) from every 3rd and 4th down since 2016 x WP after a first down (median extra yards by distance), plus (1 - P) x WP with the opponent taking over at the spot.
- **Field goal:** make probability by distance, dome and season, then WP after +3 and a kickoff (season-average drive start) or after a miss (opponent at the spot of the kick or the 20).
- **Punt:** opponent's expected next start from the punt spot, then WP.
- **Grading:** only calls that miss the best option by 1+ WP point are charged, because smaller gaps sit inside the model's error.

## Limits
- One average team: it does not know a team's QB, kicker, or short-yardage offense.
- Seasons through {last_full} are scored with a model trained on them (in sample); {ys[-1]} is out of sample.
- Per-game totals add up many small misses graded by an average-team model, so they run higher than published fourth-down estimates; read the report card as a ranking.
- No clock management beyond fixed play lengths, and fake punts count as "go".

## Files
`fourth_downs_scored.parquet` (every 4th down with WP by option), `team_scorecard.csv`, `go_rate_when_math_says_go.csv`, `costliest_calls_current_season.csv`, `wp_calibration_2024_2025.csv`, `findings.json`
"""


def sacks():
    f = F("03-sack-leverage")
    c = f["third_down_conversion_by_distance"]; e = f["epa_lost_per_sack"]; b = f["board_top5"]; r = f["board_biggest_risers"]
    return f"""# 03 Sack Leverage: not all sacks are created equal

**Inspired by:** Brett Kollmann, [Not all sacks are created equal.]({YT}o6q1dd0mI8Q). He used PFF data; this rebuilds his argument with public play-by-play and turns it into a player board.
**Data:** nflverse play-by-play, regular seasons 2016 to now.
**Code:** [`projects/sack_leverage.py`](../../projects/sack_leverage.py)

## What I found
1. **His 3rd-down table replicates.** 3rd-down conversion, {f['third_down_window']}: 1-2 yards {c['1-2']}%, 3-6 {c['3-6']}%, 7-10 {c['7-10']}%, 11+ {c['11+']}% (Kollmann: 62.8, 46.8, 34.4, 16.3).
2. **Which sacks are worth most.** Expected points taken per sack: 3rd-and-1-2 {e['3&1-2']}, 3rd-and-3-6 {e['3&3-6']}, 2nd-and-3-6 {e['2&3-6']}, 2nd-and-7-10 {e['2&7-10']}, 3rd-and-11+ only {e['3&11+']}. Every 2nd-down bucket (1.57-1.83) is worth more than a 3rd-and-11+ sack.
3. **Why: a 2nd-down sack kills the series.** {pct(f['share_2nd_down_sacks_to_3rd_and_11plus'])} of 2nd-down sacks leave 3rd-and-11 or longer. The offense extends the series {pct(f['series_success_after_2nd_down_sack'])} of the time after a 2nd-down sack, vs {pct(f['series_success_after_other_2nd_down_dropbacks_no_conversion'])} after other 2nd-down dropbacks that also failed to convert.
4. **{f['board_season']} pass rushers by value, not count.** Top five by expected points taken: {', '.join(f'{x[0]} ({x[2]:g} sacks, {x[3]:.1f} EPA)' for x in b)}. Biggest risers vs the sack list: {', '.join(f'{x[0]} (#{x[2]} in sacks, #{x[3]} in value)' for x in r)}.

![EPA per sack](epa_per_sack.png)
![Board](pass_rusher_board.png)

## Method
- Sacks are dropbacks with `sack == 1`; value is the negative of nflfastR EPA on the play.
- Half sacks get half credit. Boards: 6+ sacks for a full season, 3+ for the season in progress.
- Series success is nflfastR's `series_success` (the series earned a first down or scored a touchdown; field goals count as failures).

## Limits
- Sacks only. Pressures and hurries need charting (`was_pressure` exists from 2023 in nflverse participation data); that is the next version.
- EPA blames or credits the whole defense, not just the rusher who finished the play.

## Files
`third_down_by_distance.csv`, `epa_lost_per_sack.csv`, `pass_rusher_board_<season>.csv`, `findings.json`
"""


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
2. **Points predict next year better than wins do.** Next season's win % correlates r = {f['r_next_winpct_from_pythag']:.2f} with this season's Pythagorean win % and r = {f['r_next_winpct_from_winpct']:.2f} with actual win %.
3. **The lucky fall back, the unlucky bounce.** Teams that won 2+ games more than their points said ({f['lucky_teams_n']} of them) changed by {f['lucky_change_wins_per17']:+.1f} wins the next year (per 17 games). Teams 2+ games below ({f['unlucky_teams_n']}) changed by {f['unlucky_change_wins_per17']:+.1f}.
4. **This season so far.** Above their points: {', '.join(f'{t} ({w:g} win{"" if w == 1 else "s"}, {p:.1f} expected)' for t, w, p in reversed(lk))}. Below: {', '.join(f'{t} ({w:g} win{"" if w == 1 else "s"}, {p:.1f} expected)' for t, w, p in ul)}.

![Regression](luck_regression.png)
![This season](luck_{ys}.png)

## Method
- **Pythagorean wins:** points for and against with exponent 2.37 (the usual NFL value).
- **Fumble luck:** fumbles recovered by the team in its games minus half of all fumbles in its games (a loose ball is close to a coin flip).
- **Field-goal luck:** points the opponent's kicker left short of a logistic make-probability model (distance, dome, season); positive = the opponent missed more than expected.
- **One-score luck:** wins in games decided by 8 or fewer minus half of those games.

## Limits
- No dropped passes or dropped interceptions: public charting of drops starts in 2022 (FTN), so the 20-year version leaves them out.
- Part of the fall-back in finding 3 is ordinary regression in team quality, not only luck.

## Files
`team_season_luck.csv`, `luck_<season>.csv`, `findings.json`
"""


def kickoff():
    f = F("05-kickoff-value")
    s = f["by_season"]; ys = sorted(s)
    a, b2, c = s["2023"], s["2024"], s["2025"]
    bk = f["best_kickers"]; br = f["best_returners"]
    return f"""# 05 Kickoff Value: the new kickoff, kickers and returners

**Inspired by:** Brett Kollmann, [Kick Returners are in Absolute Hell.]({YT}ELjLAp4eyic) and [Kickers are taking over the NFL.]({YT}UufAB2UcVMw).
**Data:** nflverse play-by-play, regular seasons 2016-{ys[-1]}. The NFL adopted the dynamic kickoff in 2024 (touchback to the 30) and moved the touchback to the 35 in 2025.
**Code:** [`projects/kickoff_value.py`](../../projects/kickoff_value.py)

## What I found
1. **Returns came back.** Return rate: {pct(a['return_rate'])} in 2023, {pct(b2['return_rate'])} in 2024, {pct(c['return_rate'])} in 2025, {pct(s[ys[-1]]['return_rate'])} in {ys[-1]} so far.
2. **Drives start about five yards further up.** Average start: own {a['avg_start_own']:.1f} in 2023, {b2['avg_start_own']:.1f} in 2024, {c['avg_start_own']:.1f} in 2025. Expected points at the first snap rose from {a['ep_first_snap']:.2f} to {c['ep_first_snap']:.2f}.
3. **Returners are in hell, as Kollmann said.** Since 2025 the average return starts {abs(f['returned_vs_tb_league']):.1f} yards behind where a touchback would have put the ball. Even the best returners (min. 20 returns) average behind it: {', '.join(f'{n} ({t}, {y:+.1f})' for n, t, _, y in br)}.
4. **Kickers now create value.** With returns forced, the kicker decides field position. Best since 2025 (opponent start vs the touchback, 40+ kicks): {', '.join(f'{n} ({y:+.1f} yards, {k} kicks)' for n, k, y in bk)}.

![Era](kickoff_era.png)
![Returners](returners.png)

## Method
- The receiving team's first snap after each kickoff (merge on game and play order); return touchdowns and lost fumbles drop out.
- Touchback spot by rule year: own 25 through 2023, 30 in 2024, 35 from 2025.

## Limits
- Kicker value mixes hang time and coverage; play-by-play cannot split them.
- Return touchdowns are excluded from the yards-vs-touchback average.

## Files
`kickoffs_by_season.csv`, `kickers_2025_on.csv`, `returners_2025_on.csv`, `findings.json`
"""


def passrun():
    f = F("06-pass-run")
    g = f["epa_gap_by_season"]; ys = sorted(g)
    return f"""# 06 Pass vs Run: passing is better, so why run?

**Inspired by:** Michael MacKelvie, [Passing is better...so, why run?]({YT}pPXZlK9puqw) and Brett Kollmann, [Does "establishing the run" even work?]({YT}-W6orkJ_-Qg).
**Data:** nflverse play-by-play, regular seasons {ys[0]}-{ys[-1]}.
**Code:** [`projects/pass_run.py`](../../projects/pass_run.py)

## What I found
1. **Passing beat running on neutral early downs in {f['seasons_pass_better']} of {f['seasons_total']} seasons.** The gap in expected points per play ranged from {min(g.values()):.2f} to {max(g.values()):.2f}; {ys[-2]} was {g[ys[-2]]:.2f}. Success rate favored passing by {100 * f['success_rate_gap_by_season'][ys[-2]]:.1f} points in {ys[-2]}.
2. **Teams barely moved.** Neutral early-down pass rate went from {pct(f['pass_rate_by_season'][ys[0]])} in {ys[0]} to {pct(f['pass_rate_by_season'][ys[-2]])} in {ys[-2]}.
3. **But passing more is not a free lunch at team level.** In {ys[-2]}, a team's pass rate over expected correlated only r = {f['team_corr_proe_epa_last_full']:.2f} with its EPA per play. The league edge is real; whether a given team can cash it depends on its QB and line. That is consistent with MacKelvie's game-theory point (the run keeps defenses honest), though this data cannot prove it.

![EPA](epa_pass_vs_run.png)
![PROE](proe_vs_epa.png)

## Method
- Neutral early downs: 1st and 2nd down, win probability 20-80%, more than 2 minutes left in the half; kneels, spikes and two-point tries removed.
- Dropbacks include sacks and scrambles (the true cost of calling a pass).
- Pass rate over expected uses nflfastR's `xpass` model.

## Limits
- EPA per play ignores sequencing (does a run set up play action later?). Kollmann's 2nd-down tendency idea is the next test.

## Files
`neutral_early_downs_by_season.csv`, `team_proe_vs_epa.csv`, `findings.json`
"""


def _usd(x):
    return f"-${abs(x):.2f}M" if x < 0 else f"${x:.2f}M"


def box_score_tax():
    f = F("07-box-score-tax")
    bl = f["buy_low_last_full"]; sh = f["sell_high_last_full"]; fa = f["fa_buy_targets"]; ca = f["fa_careful"]
    def rusher(x):
        return f"{x[0]} ({x[1]}: {x[2]:g} sacks on {x[3]:g} pressures, {x[4]:.1f} expected)"
    return f"""# 07 The Box-Score Tax: NFL teams pay for the stats that don't repeat

**The question:** where is value hiding that people aren't looking at? My bet: in the gap between what a stat says about the past and what it says about the future. Sacks are the headline pass-rush stat. They are also rare, so they are noisy. Pressures happen two to four times as often. If teams pay for sacks more than sacks predict, a team that shops by pressures buys the same future sacks for less.
**Data:** Pro Football Reference advanced defense ({f['seasons']}), nflverse snap counts, and {f['market_contracts']} veteran edge and interior DL contracts ({f['market_players']} players) from Over The Cap (signed 2019-2026), all via [nflverse](https://github.com/nflverse/nflverse-data). Dollars use the 2026 salary cap (${f['cap_2026_musd']}M).
**Code:** [`projects/box_score_tax.py`](../../projects/box_score_tax.py). Prior work: PFF's Sam Monson made this argument in 2021 with player examples ([link](https://www.pff.com/news/nfl-teams-are-still-paying-for-sacks-in-free-agency-and-the-edge-defender-market-is-suffering-because-of-it)); this study puts a price on it with public data.

## What I found
1. **Pressures repeat; sacks bounce.** For pass rushers with 300+ snaps in back-to-back seasons ({f['rush_pairs']:,} pairs), pressure rate repeats at r = {f['yoy_r_pressure_rate']:.2f}, sack rate at r = {f['yoy_r_sack_rate']:.2f}. This year's pressure rate predicts next year's sack rate (r = {f['r_next_sack_rate_from_pressure_rate']:.2f}) better than this year's sack rate does (r = {f['r_next_sack_rate_from_sack_rate']:.2f}).
2. **Teams pay a premium for sack luck.** "Sack luck" means sacks above what a player's pressures predict (league rate: {f['league_sacks_per_pressure']:.2f} sacks per pressure). It barely repeats (r = {f['yoy_r_sack_luck']:.2f} year to year): holding pressures and snaps equal, one extra sack this year predicts only {f['future_sacks_per_lucky_sack']:.2f} extra sacks next year. Yet each one adds about **${f['musd_per_lucky_sack_2026']:.2f}M a year** to a veteran contract (95% interval ${f['musd_per_lucky_sack_ci'][0]:.2f}M to ${f['musd_per_lucky_sack_ci'][1]:.2f}M, 2026 dollars, errors clustered by player). Per future sack, that is about **${f['musd_per_future_sack_via_luck']:.2f}M** bought through sack luck vs **${f['musd_per_future_sack_via_pressure']:.2f}M** bought through pressures. The premium stays positive in all {f['robust_n']} versions in `robustness_lucky_sack_price.csv` (${f['robust_min']:.2f}M to ${f['robust_max']:.2f}M: with age controls, edge or interior alone, multi-year deals, deals over 1% of the cap). One version is weaker and worth watching: for deals signed 2023-2026 it is ${f['recent_deals_price'][0]:.2f}M and not significant (interval {_usd(f['recent_deals_price'][1])} to {_usd(f['recent_deals_price'][2])}), so the market may be starting to learn.
3. **The price gap.** In contracts, one sack is priced like {f['market_ratio_sack_to_pressure']:.2f} non-sack pressures. In predicting next season's sacks, one sack is worth {f['predict_count_ratio']:.2f}. The 90% ranges overlap (market {f['market_ratio_ci90'][0]}-{f['market_ratio_ci90'][1]}, prediction {f['predict_ratio_ci90'][0]}-{f['predict_ratio_ci90'][1]}; the market ratio is higher in {100 * f['share_boot_market_above_predict']:.0f}% of 1,000 bootstrap samples that resample players). Two more reasons to read this as direction, not proof: the prediction side includes linebackers with 15+ pressures while contracts are ED/IDL only, and a contract pays for several years and run defense, not only next year's sacks. Finding 2 is the firmer evidence.
4. **Buy low ({f['current_season'] - 1}).** Most pressure without the sacks: {'; '.join(rusher(x) for x in bl[:4])}.
5. **Regression risk ({f['current_season'] - 1}).** Most sacks above their pressures: {'; '.join(rusher(x) for x in sh[:3])}. Garrett's season set the single-season sack record, and elite rushers can beat the league rate; the point is that the excess over pressures is the part least likely to repeat, and the part a contract should pay least for.
6. **The {f['fa_class']} free-agent rushers to target.** Contracts ending after {f['current_season']} (Over The Cap via nflverse), still active in {f['current_season']}, ranked by {f['current_season'] - 1} pressure rate (rookie first-rounders with a fifth-year option left out): above-median pressure rate with fewer sacks than expected: {', '.join(f"{x[0]} ({x[1]}, {x[4]:g} pressures, {x[3]:g} sacks)" for x in fa[:5])}. Careful, sacks above pressures: {', '.join(f"{x[0]} ({x[3]:g} sacks on {x[4]:g} pressures)" for x in ca[:4])}.
7. **Coverage: the same idea failed, and that matters.** I expected interceptions to be the coverage version of sacks. In PFR's charting, interception rate repeats best (r = {f['yoy_r_int_rate']:.2f}), above completion % allowed (r = {f['yoy_r_cmp_pct']:.2f}) and yards per target allowed (r = {f['yoy_r_yds_per_target']:.2f}). The market pays about ${f['musd_per_int_2026']:.2f}M per platform-year interception. Public coverage stats are too noisy to call that a mistake, so I don't.

![Stability](rush_stability.png)
![Tax](sack_tax.png)
![Buy low](buy_low_rushers.png)
![Coverage](coverage_stability.png)

## Method
- **Traded players:** PFR lists a combined row plus one row per team; only the combined row is kept.
- **Pass rushers:** player-seasons with 300+ regular-season defensive snaps, listed DE/DT/DL/NT or with 15+ pressures (catches 3-4 outside linebackers). PFR pressures = sacks + hurries + knockdowns; "non-sack pressures" removes the sacks so the two are not double counted.
- **Contracts:** veteran deals only (rookie contracts dropped, duplicates removed), at least 0.4% of the cap, matched to the player's season right before signing. Pay is measured as APY as a share of that year's cap, so 2019 and 2026 deals compare fairly. Pay and prediction regressions cluster standard errors by player (many players sign several deals); full output in `models.txt`.
- **Like-for-like comparison:** the price ratio (sacks vs non-sack pressures in contracts) and the prediction ratio (sacks vs non-sack pressures in next season's sacks) both control for snaps.

## Limits
- Pressure charting is PFR's, which differs from PFF and NGS; all charting has judgment in it.
- Contracts reflect more than stats: age, injuries, scheme fit and run defense. The sack-luck result holds pressures and snaps fixed but not those.
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

**The question:** study 07 found teams pay for sacks beyond what pressures predict. Receivers have the same shape of problem. A receiver's yards split three ways, using NFL Next Gen Stats tracking: air yards on his catches, the yards after the catch a typical receiver would get on those same catches (expected YAC), and **YAC above expected**, where broken tackles, missed angles and luck live. If YAC above expected repeats less than the rest but is paid like the rest, it is a tax.
**Data:** NFL Next Gen Stats receiving ({f['seasons']}, qualified receivers, {f['player_seasons']:,} player-seasons) and {f['market_contracts']} veteran WR/TE contracts from Over The Cap ({f['market_players']} players, signed 2019-2026), via [nflverse](https://github.com/nflverse/nflverse-data). Dollars in 2026 cap terms ($301.2M).
**Code:** [`projects/yac_tax.py`](../../projects/yac_tax.py)

## What I found
1. **Where the catch happens repeats; what happens after is shakier.** Year to year: depth of target r = {y['avg_intended_air_yards']:.2f}, separation r = {y['avg_separation']:.2f}, catch rate r = {y['catch_percentage']:.2f}, YAC per catch r = {y['avg_yac']:.2f}, **YAC above expected per catch r = {y['avg_yac_above_expectation']:.2f}** ({f['pairs']} back-to-back receiver seasons).
2. **But the YAC tax mostly isn't there.** Per catch, YAC above expected is noisy. Over a season of catches it adds up to something real: each yard of it predicts {pr['yacoe_yds']:.2f} yards the next season (95% interval {pc['yacoe_yds'][0]:.2f}-{pc['yacoe_yds'][1]:.2f}), about the same as an air yard ({pr['air_yds']:.2f}). Season-long YAC over expected carries over much more than the per-catch number suggests.
3. **The market prices it about right.** Contracts pay ${pay['yacoe_yds']:.2f}M a year per 100 yards of YAC above expected, ${pay['air_yds']:.2f}M per 100 air yards and ${pay['xyac_yds']:.2f}M per 100 expected-YAC yards. Per future yard, that works out to ${fut['yacoe_yds']:.2f}M (YAC above expected), ${fut['air_yds']:.2f}M (air yards) and ${fut['xyac_yds']:.2f}M (expected YAC) per 100. Those are close, and the intervals overlap. Unlike sacks in study 07, I can't find a premium for the lucky part of receiving production. The robustness table (WR only, TE only, multi-year deals, deals over 1% of the cap, 2023-2026 deals) tells the same story.
4. **What that means for a front office.** The data says not to discount a receiver's YAC as luck by default. The most stable traits are target depth and separation, and the market already pays for production built on them. The receiver market looks efficient where the pass-rush market (study 07) does not.
5. **The {f['fa_class']} free-agent receivers.** Contracts ending after {f['current_season']} (Over The Cap, extensions counted), still active: most {f['current_season'] - 1} yards came from {lst(f['fa_top_yards'][:4])}. Leaned most on YAC above expected (100+ yards): {lst(f['fa_leaned'])}. Given finding 2, that is a reason to look closer, not to pass.

![Stability](receiver_stability.png)
![Price vs prediction](yac_tax.png)

## Method
- **Yards split:** air yards on catches = yards - catches x YAC per catch; expected YAC = catches x NGS expected YAC per catch; YAC above expected = catches x NGS YAC above expectation per catch. The three add up to total receiving yards.
- **Prediction:** next season's yards on this season's three parts plus targets; **price:** APY as % of the cap on the platform season's three parts plus targets. Both cluster standard errors by player. Output in `models.txt`.
- **Contracts:** veteran WR/TE deals (rookie deals and duplicates dropped), at least 0.4% of the cap, platform season = the season before signing.
- **Free agents:** end year from each player's Over The Cap contract history, with extensions added after the deal they extend; first-round rookie deals (fifth-year option) left out; must have played offense this season.

## Limits
- NGS season tables only include qualified receivers, so part-time players and many tight ends are missing.
- Expected YAC is the NFL's model; the split is only as good as it is.
- Contract status can lag a new extension. Puka Nacua and George Pickens (franchise tag) were both in the final year of their deals as of this writing; check before acting.

## Files
`receivers_{f['current_season'] - 1}.csv`, `free_agents_{f['fa_class']}_receivers.csv`, `robustness_price_per_100_yards.csv`, `models.txt`, `findings.json`
"""


REPORTS = [("01-flag-audit", flag_audit), ("02-fourth-down-bot", fourth), ("03-sack-leverage", sacks),
           ("04-luck-index", luck), ("05-kickoff-value", kickoff), ("06-pass-run", passrun), ("07-box-score-tax", box_score_tax), ("08-yac-tax", yac_tax)]


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


def snippets():
    """README for the in-season snippets folder; every number comes from its findings.json."""
    f = F(SNIP)
    w = f"Weeks {f['weeks'][0]}-{f['weeks'][1]}"
    q, y, t, pr, rc, d = (f["qb_epa_cpoe"], f["qb_adot_yac"], f["team_tiers"], f["early_down_proe"],
                          f["receiver_share"], f["defense_pressure"])
    nm = lambda r: f"{r['name']} ({r['team']})"
    top = q["top3_epa"]
    yac = y["most_yac"]
    tt = t["top5_net"]
    rw = rc["top5_wopr"][0]
    pp = list(pr["most_pass_happy"].items())
    rh = list(pr["most_run_heavy"].items())
    return f"""# 2026 In-Season Snippets

Six quick charts on the season in progress, the kind a staff looks at on a Monday. Same data and code standard as the studies; lighter write-ups. Through **{w} of {f['season']}** (regular season, completed weeks only; {f['plays']:,} plays). Rebuilt on every weekly refresh.

| | |
|---|---|
| <img src="qb_epa_cpoe.png" width="100%"> | <img src="qb_adot_yac.png" width="100%"> |
| <img src="team_tiers.png" width="100%"> | <img src="early_down_proe.png" width="100%"> |
| <img src="receiver_share.png" width="100%"> | <img src="defense_pressure.png" width="100%"> |

## What each one says

1. **QB Efficiency: EPA vs. CPOE** ([chart](qb_epa_cpoe.png)). {nm(top[0])} leads in EPA per dropback ({top[0]['epa']:+.3f}), ahead of {nm(top[1])} and {nm(top[2])}. Accuracy and efficiency move together this year (r = {q['corr_epa_cpoe']:.2f} across {q['n_qbs']} QBs with 150+ dropbacks).
2. **Where QB Yards Come From** ([chart](qb_adot_yac.png)). {nm(yac[0])} gets {pct(yac[0]['yac_share'])} of his passing yards after the catch on a {yac[0]['adot']:.1f}-yard average depth of target; {nm(yac[1])} is next ({pct(yac[1]['yac_share'])}). The shorter the throws, the bigger the YAC share (r = {y['corr_adot_yac_share']:.2f}), so a high YAC share is a style, not a skill by itself.
3. **2026 Team Tiers** ([chart](team_tiers.png)). Best net EPA per play: {tt[0]['team']} ({tt[0]['net']:+.3f}), {tt[1]['team']} ({tt[1]['net']:+.3f}), {tt[2]['team']} ({tt[2]['net']:+.3f}).
4. **Early-Down Pass Rate Over Expected** ([chart](early_down_proe.png)). {pp[0][0]} throws {100 * pp[0][1]:+.1f} points over expectation in neutral early downs; {rh[-1][0]} sits at {100 * rh[-1][1]:+.1f}. Teams that throw more than expected also have the better offenses so far (r = {pr['corr_proe_off_epa']:.2f} with offensive EPA per play), the same pattern as [study 06](../06-pass-run/).
5. **Receiver Roles: Targets vs. Air Yards** ([chart](receiver_share.png)). {rw['receiver_player_name']} ({rw['team']}) carries the league's biggest role: {pct(rw['tgt_share'])} of targets and {pct(rw['air_share'])} of air yards (WOPR {rw['wopr']:.2f}). Points above the dashed line are used downfield; points below it are volume options on shorter throws.
6. **Pass Defense: Pressure vs. Results** ([chart](defense_pressure.png)). Defenses that hit the QB more allow less per dropback (r = {d['corr_press_epa']:.2f}), but the spread around the line is wide: teams far above it win in coverage, teams far below it get home and still leak.

## Method notes

- Data: [nflverse](https://github.com/nflverse/nflverse-data) play-by-play (EPA, CPOE, xpass from the nflfastR models) and nflverse team colors. Teams are drawn as color-coded markers with abbreviations.
- A week counts once all of its games are in the file; a week in progress is left out.
- Dropbacks include sacks and scrambles; two-point tries and penalty no-plays are excluded.
- Pressure proxy = sack or QB hit. Play-by-play has no hurries, so this undercounts pressure; treat it as a rate comparison between teams, not a pressure rate.
- Early-down PROE: 1st and 2nd down, win probability 20-80%, outside the last two minutes of each half.
- Receiver shares are computed over the games each player appeared in (so injuries don't shrink them).
- Small samples: part of a season is early. These are snapshots, not projections.

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
    figs = ["qb_epa_cpoe", "team_tiers", "early_down_proe", "receiver_share", "qb_adot_yac", "defense_pressure"]
    cells = "".join(f'<td width="33%"><a href="reports/{SNIP}/"><img src="reports/{SNIP}/{x}.png" width="100%"></a></td>' for x in figs[:3])
    cells2 = "".join(f'<td width="33%"><a href="reports/{SNIP}/"><img src="reports/{SNIP}/{x}.png" width="100%"></a></td>' for x in figs[3:])
    return (f"\n## 2026 in-season snippets\n\nSix quick charts on the season in progress, through Weeks {f['weeks'][0]}-{f['weeks'][1]}: "
            f"QB efficiency, where QB yards come from, team tiers, early-down pass rate over expected, receiver roles and pass-rush results. "
            f"[See them all](reports/{SNIP}/).\n\n<table><tr>{cells}</tr><tr>{cells2}</tr></table>\n")


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
        badge("refreshed", f"{date.today():%b %d %Y}", "6b7280"), badge("license", "all rights reserved", "6b7280")])
    ci = f'<a href="{REPO}/actions/workflows/tests.yml"><img src="{REPO}/actions/workflows/tests.yml/badge.svg" alt="tests"></a>'
    return f"""<p align="center"><img src="assets/banner.png" alt="NFL Analytics by Dylan Fanelli" width="100%"></p>

<p align="center">{ci} {badges}</p>

<p align="center"><b><a href="#the-studies">Studies</a> &nbsp;|&nbsp; <a href="#what-a-club-gets">What a club gets</a> &nbsp;|&nbsp; <a href="#how-i-work">How I work</a> &nbsp;|&nbsp; <a href="#under-the-hood">Under the hood</a> &nbsp;|&nbsp; <a href="docs/glossary.md">Glossary</a> &nbsp;|&nbsp; <a href="#about">About</a></b></p>

I'm Dylan Fanelli, and this is the NFL analytics portfolio I am building toward a job in a club front office. Each study starts from a question a coach, scout or general manager actually argues about, answers it with public data and a model I built, and ends with what a club would do with the answer. I validate every model before I trust it, I say what the data can't show, and every number on these pages is regenerated from code on each weekly refresh.

**Headline work:** a [fourth-down decision bot](reports/02-fourth-down-bot/) on my own win-probability model, which matches nflfastR out of sample (Brier {f2['brier_ours']:.4f} vs {f2['brier_nflfastR_vegas_wp']:.4f} on {f2['wp_test_plays']:,} plays), and [evidence of a market inefficiency in pass-rusher contracts](reports/07-box-score-tax/): teams pay about ${F('07-box-score-tax')['musd_per_lucky_sack_2026']:.2f}M a year for sacks that pressures say won't repeat.

<p align="center"><img src="assets/at-a-glance.png" alt="Selected studies at a glance" width="100%"></p>

<p><img src="assets/img/strip-helmets.jpg" width="100%" alt="All 32 NFL helmets on one wall"></p>

## The studies

| # | Study | The question | Headline | Methods |
|---|---|---|---|---|
{chr(10).join(rows)}

{gallery}
{snippets_section()}{upcoming}
<a id="what-a-club-gets"></a>
## What a club gets

| Department | Question it answers | Study |
|---|---|---|
| Head coach and game management | Go, kick or punt on this fourth down? | [02 Fourth-Down Bot](reports/02-fourth-down-bot/) |
| Pro personnel and free agency | Are pass rushers and receivers priced for what repeats? Who to target in free agency? | [07 Box-Score Tax](reports/07-box-score-tax/), [08 YAC Tax](reports/08-yac-tax/) |
| Defensive staff | When is a sack worth the most, and who produces those? | [03 Sack Leverage](reports/03-sack-leverage/) |
| Offensive staff | Should we pass more on early downs? | [06 Pass vs Run](reports/06-pass-run/) |
| Special teams | Who creates field position under the new kickoff? | [05 Kickoff Value](reports/05-kickoff-value/) |
| Front office and ownership | How much of our record was luck? | [04 Luck Index](reports/04-luck-index/) |
| Game prep | What does this crew call, and what flags are coachable on the road? | [01 Flag Audit](reports/01-flag-audit/) |

<a id="how-i-work"></a>
## How I work

Every study follows the same [report standard](docs/report-standard.md), modeled on how Big Data Bowl entries, Open Source Football articles and the nflverse model write-ups are built:

1. **A question first,** stated before the data, with prior public work credited.
2. **Stability before value.** A stat has to repeat before it can be called a skill or priced.
3. **Validation in the open:** out-of-sample tests, calibration, bootstraps, clustered standard errors and robustness tables.
4. **Results under headings that state the finding,** each with its figure.
5. **What a club does with it,** limitations and next steps on every page.
6. **Reproducible:** one command rebuilds every number, chart and page; `pytest` (run by GitHub Actions on every change, Python 3.10 and 3.12) checks that published numbers stay football-sane and every page meets the standard.

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
    D --> G[pytest<br>sanity checks on<br>every published number]
```

```
nflan/          tested library: data loading, win-probability model, 4th-down bot, penalty and stats helpers
projects/       one script per study (python -m projects.<name>)
reports/        each study's write-up, figures, CSV outputs and findings.json
sql/            DuckDB queries answering the same questions straight from the parquet files
scripts/        update.py (weekly refresh), build_readmes.py, build_figures.py, report_meta.py
tests/          unit tests and sanity checks on published numbers
docs/           report standard, glossary, data dictionary, inspiration notes
assets/         banner and at-a-glance figure
```

### Reproduce

```bash
pip install -r requirements.txt
python scripts/update.py          # downloads nflverse data (about 400 MB), runs every study, figures, tests and READMEs
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

Full history: [LOG.md](LOG.md). Data refreshes weekly in season (last: {date.today():%B %d, %Y}, through the latest completed week of {ys[-1]}).

## License and citation

© 2026 Dylan Fanelli. All rights reserved. The code, reports and figures may be viewed here; they may not be copied, modified or used without written permission. See [LICENSE](LICENSE). To cite this work, use the **Cite this repository** button (from [CITATION.cff](CITATION.cff)).

<a id="about"></a>
## About

<table>
<tr>
<td width="32%" valign="top"><img src="assets/img/about-nfl.jpg" width="100%" alt="Dylan Fanelli at the NFL offices in New York City"><br><sub>At the NFL offices in New York City</sub></td>
<td valign="top">

Dylan Fanelli, M.S. Sport Management candidate at UMass Amherst (Mark H. McCormack Department). I am building this portfolio to show proficiency in NFL statistics and sabermetrics-style analysis, with the goal of a job in an NFL club front office.

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
    out += ["", "> **TL;DR**"]
    for t in (m["tldr"](f) if "tldr" in m else [lead for _, lead, _ in items[:5]]):
        out.append(f"> - {t}")
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
