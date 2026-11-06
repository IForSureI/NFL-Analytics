# 01 Flag Audit: do NFL flags really even out?

**Inspired by:** Michael MacKelvie, [We looked at 92,255 flags - NFL refs are biased](https://www.youtube.com/watch?v=LH3Ck59I8V0).
**Data:** nflverse play-by-play and officials, 2016-2026 (2,882 games, 35,094 accepted flags). Declined and offsetting flags removed.
**Code:** [`projects/flag_audit.py`](../../projects/flag_audit.py)

## What I found
1. **The road team's extra judgment-call flags are gone.** In 2016-22, road teams drew 0.27 more subjective flags per game than home teams (holding, pass interference, roughing). Since 2023 the gap is 0.00.
2. **The road gap that remains is noise and communication, not referees' judgment.** Road teams still take about 0.17 extra rule-book flags a game. Neutral zone infractions go against the road defense 60% of the time, and delay of game against the road offense 56%. False starts, the flag fans blame on crowd noise, split almost evenly (49.6% on the road team).
3. **Referee crews have a real, modest style.** A crew's flags per game this season predicts next season at r = 0.24 (141 back-to-back crew seasons). In 2025, Alex Moore's crew averaged 16.0 flags a game and Brad Allen's averaged 9.9.
4. **A team's flag luck does not carry over.** Within a season, a team's net subjective flags (drawn minus committed) in odd weeks predicts even weeks at only r = 0.08. Committing flags is a bit more stable (r = 0.28) than drawing them (r = 0.17): discipline is partly real, getting calls is mostly not.
5. **Mahomes is not the roughing-flag king.** Among 41 QBs with 1,500+ dropbacks since 2018, he ranks #22 (by shrunk rate) at 0.22 roughing flags per 100 dropbacks, about the league rate of 0.23. The top of the list is J.Goff (0.35 raw), A.Dalton (0.45) and M.Ryan (0.39). Only J.Goff and A.Dalton sit clearly above the league rate (95% interval); everyone else overlaps it.
6. **Big calls are real but random.** 923 accepted flags (888 in the regular season) moved win probability by 10+ points, about 84 per full regular season. Pass interference leads. A team's net big calls this year predicts next year at r = 0.03: no team is owed them.

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
