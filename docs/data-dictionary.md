# Data dictionary

All data is public and loaded by `nflan/data.py` from the [nflverse data releases](https://github.com/nflverse/nflverse-data) (CC-BY 4.0). Raw files cache to `data/raw/` (not committed; about 400 MB).

## Sources

| Source | nflverse release | Seasons used | Used in |
|---|---|---|---|
| Play-by-play (with nflfastR EPA, WP, xpass) | `pbp` | 2006-present | 01-06 |
| Officials | `officials` | 2016-present | 01 |
| Pro Football Reference advanced defense | `pfr_advstats` (def) | 2018-present | 07 |
| NFL Next Gen Stats receiving | `nextgen_stats` (receiving) | 2016-2025 | 08 |
| Snap counts | `snap_counts` | 2018-present | 07 |
| Over The Cap contracts | `contracts` | deals signed 2019-2026 | 07, 08 |
| Players (ID crosswalk) | `players` | | 07, 08 |

## Key play-by-play columns

| Column | Meaning |
|---|---|
| `epa` | Expected points added on the play |
| `wp`, `vegas_wp` | nflfastR win probability without and with the point spread |
| `xpass` | Probability the play is a dropback given the situation |
| `pass`, `rush`, `qb_dropback`, `sack` | Play-type flags (dropbacks include sacks and scrambles) |
| `down`, `ydstogo`, `yardline_100` | Down, distance, yards from the opponent's end zone |
| `series_success` | The series earned a first down or touchdown |
| `penalty_type`, `penalty_team` | Accepted penalty and the team flagged |
| `fourth_down_converted`, `field_goal_result`, `punt_attempt` | Fourth-down outcomes |

## Output conventions

- Every study writes `reports/NN-slug/findings.json`: every number quoted in that study's README.
- CSVs use one row per player-season, team-season or season, with the season as an integer column.
- Dollars are millions in 2026 cap terms (cap $301.2M) unless the column says otherwise.
- Player names follow the source (nflverse abbreviations in play-by-play, full names from PFR and Over The Cap).
