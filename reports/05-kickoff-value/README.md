# 05 Kickoff Value: the new kickoff, kickers and returners

**Inspired by:** Brett Kollmann, [Kick Returners are in Absolute Hell.](https://www.youtube.com/watch?v=ELjLAp4eyic) and [Kickers are taking over the NFL.](https://www.youtube.com/watch?v=UufAB2UcVMw).
**Data:** nflverse play-by-play, regular seasons 2016-2026. The NFL adopted the dynamic kickoff in 2024 (touchback to the 30) and moved the touchback to the 35 in 2025.
**Code:** [`projects/kickoff_value.py`](../../projects/kickoff_value.py)

## What I found
1. **Returns came back.** Return rate: 21% in 2023, 33% in 2024, 75% in 2025, 81% in 2026 so far.
2. **Drives start about five yards further up.** Average start: own 25.3 in 2023, 29.8 in 2024, 30.5 in 2025. Expected points at the first snap rose from 1.11 to 1.38.
3. **Returners are in hell, as Kollmann said.** Since 2025 the average return starts 5.6 yards behind where a touchback would have put the ball. Even the best returners (min. 20 returns) average behind it: I.Williams (NYJ, -1.4), Br.Robinson (ATL, -1.6), R.Davis (BUF, -1.7).
4. **Kickers now create value.** With returns forced, the kicker decides field position. Best since 2025 (opponent start vs the touchback, 40+ kicks): J.Karty (-10.2 yards, 41 kicks), R.Fitzgerald (-6.8 yards, 104 kicks), J.Myers (-6.4 yards, 141 kicks).

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
