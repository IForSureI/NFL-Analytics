# 02 Fourth-Down Bot: who leaves wins on the table?

**Inspired by:** Brett Kollmann, [Are analytics ruining football?](https://www.youtube.com/watch?v=FOnQFk5qy-4) (judge the decision apart from the play), and Michael MacKelvie, [Passing is better...so, why run?](https://www.youtube.com/watch?v=pPXZlK9puqw) (coaches lag the math). Method follows the public idea of Ben Baldwin's [nfl4th](https://github.com/nflverse/nfl4th), rebuilt from scratch in Python.
**Data:** nflverse play-by-play 2006-2026.
**Code:** [`nflan/wp.py`](../../nflan/wp.py), [`nflan/fourth.py`](../../nflan/fourth.py), [`projects/fourth_down_bot.py`](../../projects/fourth_down_bot.py)

## What I found
1. **The win-probability model holds up out of sample.** Trained on 2006-2023 and tested on 80,613 plays from 2024-25: Brier score 0.1495, against 0.1488 for nflfastR's spread-adjusted model on the same plays (lower is better). The two agree at r = 0.993. Calibration sits close to the 45-degree line (most bins within 2 points).
2. **Coaches go for it far more than they used to, and still not enough.** In clear "go" spots (going adds 2+ win-probability points, score within 16, outside the last 5 minutes), teams went 33% of the time in 2018 and 53% in 2025. 2026 so far: 48%.
3. **2026 report card (regular season).** Most win probability lost per game on clear 4th-down calls: HOU (6.0 points), ARI (5.8), PIT (5.8). Least: BUF (0.8), TB (1.1), MIA (1.4). Totals add up small misses, so read them as a ranking, not an exact count of lost wins.
4. **Sanity checks pass.** 4th-and-1 at midfield, tied, early, even teams: going adds 2.8 WP points. 4th-and-10 at your own 20: going costs 11.6.

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
- Seasons through 2025 are scored with a model trained on them (in sample); 2026 is out of sample.
- No clock management beyond fixed play lengths, and fake punts count as "go".

## Files
`fourth_downs_scored.parquet` (every 4th down with WP by option), `team_scorecard.csv`, `go_rate_when_math_says_go.csv`, `costliest_calls_current_season.csv`, `wp_calibration_2024_2025.csv`, `findings.json`
