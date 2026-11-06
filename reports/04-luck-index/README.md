# 04 Luck Index: how many wins does chance hand out?

**Inspired by:** Michael MacKelvie, [We Measured "Luck" in the NFL. It's a BIG deal.](https://www.youtube.com/watch?v=Zfin10hS0YM), which builds on the NFL's own luck work (Tom Bliss).
**Data:** nflverse play-by-play, regular seasons 2006 to now.
**Code:** [`projects/luck_index.py`](../../projects/luck_index.py)

## What I found
1. **Luck does not repeat.** Year-to-year correlation: fumble-recovery luck r = 0.04, opponent field-goal luck r = 0.07, one-score-game record r = 0.06, wins above Pythagorean r = 0.03.
2. **Points predict next year better than wins do.** Next season's win % correlates r = 0.39 with this season's Pythagorean win % and r = 0.35 with actual win %.
3. **The lucky fall back, the unlucky bounce.** Teams that won 2+ games more than their points said (44 of them) changed by -2.9 wins the next year (per 17 games). Teams 2+ games below (34) changed by +3.5.
4. **This season so far.** Above their points: CLE (5 wins, 3.0 expected), DEN (6 wins, 4.2 expected), BUF (6 wins, 4.5 expected). Below: TB (3 wins, 4.8 expected), TEN (1 win, 2.5 expected), NYJ (2 wins, 3.5 expected).

![Regression](luck_regression.png)
![This season](luck_2026.png)

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
