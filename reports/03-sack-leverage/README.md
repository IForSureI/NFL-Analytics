# 03 Sack Leverage: not all sacks are created equal

**Inspired by:** Brett Kollmann, [Not all sacks are created equal.](https://www.youtube.com/watch?v=o6q1dd0mI8Q). He used PFF data; this rebuilds his argument with public play-by-play and turns it into a player board.
**Data:** nflverse play-by-play, regular seasons 2016 to now.
**Code:** [`projects/sack_leverage.py`](../../projects/sack_leverage.py)

## What I found
1. **His 3rd-down table replicates.** 3rd-down conversion, 2022-2025: 1-2 yards 63.9%, 3-6 45.9%, 7-10 32.1%, 11+ 15.9% (Kollmann: 62.8, 46.8, 34.4, 16.3).
2. **Which sacks are worth most.** Expected points taken per sack: 3rd-and-1-2 2.46, 3rd-and-3-6 2.18, 2nd-and-3-6 1.83, 2nd-and-7-10 1.7, 3rd-and-11+ only 1.53. Every 2nd-down bucket (1.57-1.83) is worth more than a 3rd-and-11+ sack.
3. **Why: a 2nd-down sack kills the series.** 82% of 2nd-down sacks leave 3rd-and-11 or longer. The offense extends the series 21% of the time after a 2nd-down sack, vs 46% after other 2nd-down dropbacks that also failed to convert.
4. **2025 pass rushers by value, not count.** Top five by expected points taken: M.Garrett (23 sacks, 35.8 EPA), W.Anderson (12 sacks, 31.9 EPA), J.Sweat (12 sacks, 30.7 EPA), A.Hutchinson (14.5 sacks, 30.1 EPA), D.Hunter (15 sacks, 29.7 EPA). Biggest risers vs the sack list: T.Watt (#35 in sacks, #15 in value), D.Turner (#25 in sacks, #12 in value), A.Van Ginkel (#35 in sacks, #23 in value).

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
