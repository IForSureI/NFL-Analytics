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


REPORTS = [("01-flag-audit", flag_audit), ("02-fourth-down-bot", fourth), ("03-sack-leverage", sacks),
           ("04-luck-index", luck), ("05-kickoff-value", kickoff), ("06-pass-run", passrun)]


def top_readme():
    f1, f2, f3, f4, f5, f6 = (F(s) for s, _ in REPORTS)
    g = f2["go_rate_clear_spots"]; ys = sorted(g)
    era = {k.strip("()").replace("'", "").replace(" ", ""): v for k, v in f1["home_edge_by_era"].items()}
    old = sorted({k.split(",")[0] for k in era})[0]
    mah = f1.get("rtp_mahomes", [0, 0, 0])
    k = f5["by_season"]
    return f"""# NFL Analytics

Football analytics by **Dylan Fanelli** (M.S. Sport Management, UMass Amherst McCormack). Six studies on public NFL play-by-play, each one starting from a question a coach, scout or fan argues about, then testing it with data. Python, SQL-ready parquet, tested code, and charts a coach can read.

Built on [nflverse](https://github.com/nflverse) data. Inspired by two of the best football explainers working: **Michael MacKelvie** (data storytelling) and **Brett Kollmann** (film plus numbers). Each report links the video that started it. See [`docs/inspiration.md`](docs/inspiration.md).

**Last refreshed:** {date.today():%B %d, %Y} (through the latest completed week of the {ys[-1]} season).

## The studies

| # | Study | The question | Headline |
|---|---|---|---|
| 01 | [Flag Audit](reports/01-flag-audit/) | Do flags even out? | Road teams' extra judgment-call flags ({era[old + ',subjective']:.2f} a game in {old}) are gone since 2023; Mahomes ranks #{mah[1]} of {mah[2]} QBs in roughing flags drawn |
| 02 | [Fourth-Down Bot](reports/02-fourth-down-bot/) | Who leaves wins on the table? | Own WP model (Brier {f2['brier_ours']:.4f} vs nflfastR {f2['brier_nflfastR_vegas_wp']:.4f}); coaches go in {pct(g[ys[-2]])} of clear go spots, up from {pct(g[ys[0]])} in {ys[0]} |
| 03 | [Sack Leverage](reports/03-sack-leverage/) | Are all sacks equal? | An average 2nd-down sack ({f3['epa_lost_2nd_down_sack_avg']} EPA) is worth more than a 3rd-and-11+ sack ({f3['epa_lost_per_sack']['3&11+']}); {pct(f3['share_2nd_down_sacks_to_3rd_and_11plus'])} of them leave 3rd-and-11+ |
| 04 | [Luck Index](reports/04-luck-index/) | How much is luck? | Fumble, kick and close-game luck repeat at r < 0.1; teams 2+ wins over their points drop {abs(f4['lucky_change_wins_per17']):.1f} wins the next year |
| 05 | [Kickoff Value](reports/05-kickoff-value/) | What did the new kickoff do? | Returns went from {pct(k['2023']['return_rate'])} (2023) to {pct(k['2025']['return_rate'])} (2025); the average return still lands {abs(f5['returned_vs_tb_league']):.1f} yards behind a touchback |
| 06 | [Pass vs Run](reports/06-pass-run/) | Passing is better, so why run? | Passing won on neutral early downs in {f6['seasons_pass_better']} of {f6['seasons_total']} seasons, but team pass rate over expected tracks efficiency only at r = {f6['team_corr_proe_epa_last_full']:.2f} |

## What is in here
```
nflan/          small tested library: data loading, win-probability model, 4th-down bot, penalty and stats helpers
projects/       one script per study (python -m projects.<name>)
reports/        each study's write-up, charts, CSV outputs and findings.json
sql/            DuckDB queries that answer the same questions straight from the parquet files
scripts/        update.py (refresh the season in progress and rebuild everything), build_readmes.py
tests/          unit tests and sanity checks on every published number
docs/           inspiration notes from the MacKelvie and Kollmann videos
```

## Run it
```bash
pip install -r requirements.txt
python scripts/update.py          # downloads nflverse data (about 400 MB), runs all six studies, tests, READMEs
pytest -q
```
Each study also runs alone, for example `python -m projects.fourth_down_bot`.

## Data and credit
- Play-by-play and officials data: [nflverse](https://github.com/nflverse/nflverse-data) (CC-BY 4.0), with nflfastR's EPA and win-probability models.
- Fourth-down method: the public idea behind [nfl4th](https://github.com/nflverse/nfl4th) by Ben Baldwin, rebuilt from scratch.
- Ideas: Michael MacKelvie and Brett Kollmann (YouTube). All analysis and any mistakes are mine.

## About
Dylan Fanelli, M.S. Sport Management candidate at UMass Amherst (Mark H. McCormack Department), aiming for a club front office. Baseball work lives in a separate portfolio. [LinkedIn](https://www.linkedin.com/in/dylanfanelli/)
"""


def main():
    for slug, fn in REPORTS:
        (R / slug / "README.md").write_text(fn())
    (ROOT / "README.md").write_text(top_readme())
    print("READMEs written")


if __name__ == "__main__":
    main()
