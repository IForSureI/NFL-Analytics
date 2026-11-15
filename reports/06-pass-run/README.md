<sub>[← Portfolio](../../README.md) &nbsp;|&nbsp; [← 05 Kickoff Value](../05-kickoff-value/) &nbsp;|&nbsp; [07 The Box-Score Tax →](../07-box-score-tax/)</sub>

# 06 Pass vs Run
### Passing is better, so why run?

![status: published](https://img.shields.io/badge/status-published-0b6e4f) ![seasons: 2006-2026](https://img.shields.io/badge/seasons-2006--2026-1d2433) ![method: EPA](https://img.shields.io/badge/method-EPA-c2410c) ![method: pass rate over expected](https://img.shields.io/badge/method-pass%20rate%20over%20expected-c2410c) ![method: team bootstrap](https://img.shields.io/badge/method-team%20bootstrap-c2410c)

**TL;DR**

- Passing beat running on neutral early downs in 21 of 21 seasons.
- Teams moved slowly: early-down pass rate 48% to 52%.
- At team level, passing more than expected goes with better efficiency at r = 0.28 (95% interval 0.18 to 0.38, 640 team-seasons). It is a correlation, not proof a team should pass more.

<p align="center"><img src="epa_pass_vs_run.png" width="720" alt="EPA per play on neutral early downs: dropbacks vs designed runs, by season."></p>
<p align="center"><sub>EPA per play on neutral early downs: dropbacks vs designed runs, by season.</sub></p>

## Key numbers

| Measure | Value |
|---|---|
| Seasons passing beat running (neutral early downs) | **21 of 21** |
| EPA per play gap, last full season | **0.14** |
| Pass rate, first to last full season | **48% to 52%** |
| Team pass rate over expected vs EPA, all team-seasons (r) | **0.28 (0.18 to 0.38)** |
| Same team, change vs change (r) | **0.21 (0.10 to 0.33)** |
| Last full season alone (r) | **0.20 (-0.16 to 0.51)** |

## Why it matters for a club

- **Offensive tendencies:** the league-wide edge for passing on early downs shows up in every season.
- **Team-specific calls:** teams that pass more than expected are a little more efficient, but good passing teams choose to pass, so the answer for one team is a personnel question, not a league average.
- **Opponent scouting:** pass rate over expected is a clean tendency number for the weekly packet.

## The question

**Passing has been more efficient for years. So why do teams still run, and does passing more make a team better?**

**Inspired by:** Michael MacKelvie, [Passing is better...so, why run?](https://www.youtube.com/watch?v=pPXZlK9puqw) and Brett Kollmann, [Does "establishing the run" even work?](https://www.youtube.com/watch?v=-W6orkJ_-Qg).  

## Data

nflverse play-by-play, regular seasons 2006-2026.

## Results

### 1. Passing beat running on neutral early downs in 21 of 21 seasons.

The gap's 95% interval sits above zero in 21 of them. The gap in expected points per play ranged from 0.11 to 0.24; 2025 was 0.14. Success rate favored passing by 9.4 points in 2025.

### 2. Teams barely moved.

Neutral early-down pass rate went from 48% in 2006 to 52% in 2025.

### 3. Teams that pass more than expected are a little more efficient.

Across 640 team-seasons, pass rate over expected and EPA per play correlate at r = 0.28 (95% interval 0.18 to 0.38). The sign is positive in 18 of 20 full seasons, and single seasons run from -0.08 to 0.54. One season is too few teams to read: 2025 alone is r = 0.20 (95% interval -0.16 to 0.51).

<p align="center"><img src="proe_vs_epa.png" width="720" alt="Team pass rate over expected vs EPA per play, every team-season, last full season labeled."></p>
<p align="center"><sub>Team pass rate over expected vs EPA per play, every team-season, last full season labeled.</sub></p>

### 4. The same team gets a little better when it passes more.

A team's year-to-year change in pass rate over expected tracks its change in EPA per play at r = 0.21 (95% interval 0.10 to 0.33) (608 back-to-back team seasons). That is about 0.004 EPA per play for each extra point of pass rate. It is still not cause and effect. A team that upgrades at quarterback passes more and scores more for the same reason.

## Method

- Neutral early downs: 1st and 2nd down, win probability 20-80%, more than 2 minutes left in the half; kneels, spikes and two-point tries removed.
- Dropbacks include sacks and scrambles (the true cost of calling a pass).
- Pass rate over expected uses nflfastR's `xpass` model.
- Team-level intervals are 95%, from resampling teams with all their seasons 2,000 times. Season gaps use play-level standard errors, which treat plays as independent.

**In equations**

- Pass rate over expected (PROE) $`=`$ actual dropback rate $`- \overline{\text{xpass}}`$, where xpass is nflfastR's dropback probability given the situation.

## Validation

- The pass edge holds in 21 of 21 seasons, and its 95% interval is above zero in 21.
- The team-level link is tested on 640 team-seasons and within teams, not on one season of 32 teams.
- Dropbacks include sacks and scrambles, so passing is charged its true cost.

## Limitations

- EPA per play ignores sequencing (does a run set up play action later?). Kollmann's 2nd-down tendency idea is the next test.
- The team-level link is a correlation. Good passing teams choose to pass more, so it does not show that any team would gain by passing more.
- The league gap is an average over plays teams chose. It does not say the next extra pass is worth that much, because defenses adjust.
- The season in progress is left out of the team-level numbers.

## Next steps

- Sequencing: does an early run set up play action later (FTN charting, 2022 on)?
- Second-down run tendencies by personnel.

## Reproduce

```bash
pip install -r requirements.txt
python -m projects.pass_run
```
Code: [`projects/pass_run.py`](../../projects/pass_run.py)

## Files in this folder

| File | What it holds |
|---|---|
| [`neutral_early_downs_by_season.csv`](neutral_early_downs_by_season.csv) | Plays, EPA, success rate and pass rate by season |
| [`team_proe_vs_epa.csv`](team_proe_vs_epa.csv) | Team PROE and EPA per play, every team-season |
| [`findings.json`](findings.json) | Every number quoted on this page, machine-readable |

---
<sub>[← Portfolio](../../README.md) &nbsp;|&nbsp; [← 05 Kickoff Value](../05-kickoff-value/) &nbsp;|&nbsp; [07 The Box-Score Tax →](../07-box-score-tax/)</sub>

<sub>© 2026 Dylan Fanelli. All rights reserved. To cite: Fanelli, D. (2026). *Pass vs Run*. NFL Analytics. https://github.com/IForSureI/NFL-Analytics/tree/main/reports/06-pass-run</sub>
