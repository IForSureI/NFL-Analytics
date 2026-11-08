# 2026 In-Season Snippets

Six quick charts on the season in progress, the kind a staff looks at on a Monday. Same data and code standard as the studies; lighter write-ups. Through **Weeks 1-8 of 2026** (regular season, completed weeks only; 21,191 plays). Rebuilt on every weekly refresh.

| | |
|---|---|
| <img src="qb_epa_cpoe.png" width="100%"> | <img src="rb_success.png" width="100%"> |
| <img src="team_tiers.png" width="100%"> | <img src="early_down_proe.png" width="100%"> |
| <img src="receiver_share.png" width="100%"> | <img src="defense_pressure.png" width="100%"> |

## What each one says

1. **QB Efficiency: EPA vs. CPOE** ([chart](qb_epa_cpoe.png)). J.Allen (BUF) leads in EPA per dropback (+0.303), ahead of B.Purdy (SF) and C.Williams (CHI). Accuracy and efficiency move together this year (r = 0.75 across 30 QBs with 150+ dropbacks).
2. **Running Back Success Rate** ([chart](rb_success.png)). C.McCaffrey (SF) leads the 33 backs with 60+ carries at 53.6% of runs gaining positive EPA, ahead of B.Corum (LA, 52.0%) and J.Cook (BUF, 50.7%). The RB average is 39.8%. Success rate shows how often a back keeps the offense on schedule; it mixes his work with his blocking, which study 09 (Run Game Value, coming next) will separate.
3. **2026 Team Tiers** ([chart](team_tiers.png)). Best net EPA per play: JAX (+0.263), SF (+0.220), KC (+0.167).
4. **Early-Down Pass Rate Over Expected** ([chart](early_down_proe.png)). CIN throws +11.3 points over expectation in neutral early downs; TB sits at -13.4. Teams that throw more than expected also have the better offenses so far (r = 0.49 with offensive EPA per play), the same pattern as [study 06](../06-pass-run/).
5. **Receiver Roles: Targets vs. Air Yards** ([chart](receiver_share.png)). J.Smith-Njigba (SEA) carries the league's biggest role: 36% of targets and 52% of air yards (WOPR 0.90). Points above the dashed line are used downfield; points below it are volume options on shorter throws.
6. **Pass Defense: Pressure vs. Results** ([chart](defense_pressure.png)). Defenses that hit the QB more allow less per dropback (r = -0.31), but the spread around the line is wide: teams far above it win in coverage, teams far below it get home and still leak.

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
