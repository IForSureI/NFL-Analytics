# 2026 In-Season Snippets

Twelve quick charts on the season in progress, across positions, the kind a staff looks at on a Monday. Same data and code standard as the studies; lighter write-ups. Through **Weeks 1-10 of 2026** (regular season, completed weeks only; 26,246 plays). Rebuilt on every weekly refresh.

**Interactive version:** [every chart on one page](https://iforsurei.github.io/NFL-Analytics/snippets.html), where hovering (or tapping) any player or team opens the breakdown: a quarterback's efficiency by down and by throw depth, a back's success by down, a receiver's role and value by depth, a team's offense and defense split into run and pass, a pass rusher's and every team's week by week, a kicker's makes by distance.

| | |
|---|---|
| <img src="qb_epa_cpoe.png" width="100%"> | <img src="rb_success.png" width="100%"> |
| <img src="team_tiers.png" width="100%"> | <img src="early_down_proe.png" width="100%"> |
| <img src="receiver_share.png" width="100%"> | <img src="defense_pressure.png" width="100%"> |
| <img src="qb_adot_yac.png" width="100%"> | <img src="receiver_epa_adot.png" width="100%"> |
| <img src="yac_over_expected.png" width="100%"> | <img src="defense_run_pass.png" width="100%"> |
| <img src="pass_rush_leaders.png" width="100%"> | <img src="kicker_fgoe.png" width="100%"> |

## What each one says

1. **QB Efficiency: EPA vs. CPOE** ([chart](qb_epa_cpoe.png)). B.Purdy (SF) leads in EPA per dropback (+0.311), ahead of T.Lawrence (JAX) (+0.286). Accuracy and efficiency move together this year (r = 0.74, 95% interval 0.60 to 0.84, across 31 QBs with 150+ dropbacks).
2. **Running Back Success Rate** ([chart](rb_success.png)). B.Corum (LA) leads the 41 backs with 60+ carries at 57.3% of runs gaining positive EPA, ahead of J.Gibbs (DET, 48.7%) and C.McCaffrey (SF, 47.8%). The RB average is 39.7%. On 103 carries the leader's 95% interval runs 48% to 66%, and only 2 of the top 30 are clearly above average, so the order inside the list is mostly noise this early. Success rate mixes a back's work with his blocking; [study 09](../09-run-game-value/) splits the two.
3. **2026 Team Tiers** ([chart](team_tiers.png)). Best net EPA per play: JAX (+0.234), SF (+0.213), KC (+0.211).
4. **Early-Down Pass Rate Over Expected** ([chart](early_down_proe.png)). CIN throws +13.7 points over expectation in neutral early downs; TB sits at -13.3. Teams that throw more than expected also have the better offenses so far (r = 0.50 with offensive EPA per play, 95% interval 0.13 to 0.74 on 32 teams). [Study 06](../06-pass-run/) finds the same direction across 640 team-seasons, at a smaller r = 0.28. It is a correlation: good passing teams choose to pass.
5. **Receiver Roles: Targets vs. Air Yards** ([chart](receiver_share.png)). J.Smith-Njigba (SEA) carries the league's biggest role: 37% of targets and 53% of air yards (WOPR 0.93). Points above the dashed line are used downfield; points below it are volume options on shorter throws.
6. **Pass Defense: Pressure vs. Results** ([chart](defense_pressure.png)). So far there is no clear link between hitting the QB and EPA allowed per dropback (r = -0.24, 95% interval -0.59 to 0.24 on 32 teams). The proxy counts only sacks and hits, so this says little about pressure itself.

7. **Where QB Yards Come From** ([chart](qb_adot_yac.png)). P.Mahomes (KC) gets 65% of his passing yards after the catch on a 6.0-yard average depth of target. The shorter the throws, the bigger the YAC share (r = -0.65, 95% interval -0.83 to -0.33), so a high YAC share is a style, not a skill by itself.
8. **Receivers: Role vs. Value** ([chart](receiver_epa_adot.png)). Among the 45 most-targeted receivers, T.Higgins (CIN) adds the most per target (+0.72 EPA on a 12.8-yard depth). Deeper roles earn somewhat more per target (r = 0.41, 95% interval 0.14 to 0.62), so compare a receiver with others at his depth.
9. **YAC Over Expected per Catch** ([chart](yac_over_expected.png)). T.Kelce (KC) gains +4.42 yards after the catch beyond what the nflverse xYAC model expects per reception, then J.Warren (PIT, +4.22). The minimum is 25 catches, which is thin: the leader's 95% interval is +0.87 to +7.97, and 1 of the top 30 is clearly above the league mean. [Study 08](../08-yac-tax/) uses full seasons for this reason.
10. **Defense: Run Stopping vs. Pass Defense** ([chart](defense_run_pass.png)). Best run defense by EPA per run allowed: LA, JAX, SF; best pass defense: MIN, TB, LA. The two go together loosely (r = 0.55, 95% interval 0.26 to 0.76).
11. **Pass Rush Leaders** ([chart](pass_rush_leaders.png)). G.Rousseau (BUF) has a sack or QB hit on 27 plays, ahead of D.Turner (MIN) with 23 each. [Study 07](../07-box-score-tax/) showed hits and pressures predict future sacks better than sacks do, which is why this counts both.
12. **Kickers: FG Points Over Expected** ([chart](kicker_fgoe.png)). S.Shrader (IND, 23-25) is +10.9 points above what an average kicker makes from the same distances; the expected rate comes from a distance-and-roof model fit on 4,325 kicks from 2022-25. An average kicker would land within about 11.7 points of zero on those same kicks 95% of the time, and 3 of the 33 kickers with 8+ attempts sit outside their own band. Read this as who has made their kicks, not who is the better kicker.

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
