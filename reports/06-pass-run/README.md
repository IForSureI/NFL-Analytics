# 06 Pass vs Run: passing is better, so why run?

**Inspired by:** Michael MacKelvie, [Passing is better...so, why run?](https://www.youtube.com/watch?v=pPXZlK9puqw) and Brett Kollmann, [Does "establishing the run" even work?](https://www.youtube.com/watch?v=-W6orkJ_-Qg).
**Data:** nflverse play-by-play, regular seasons 2006-2026.
**Code:** [`projects/pass_run.py`](../../projects/pass_run.py)

## What I found
1. **Passing beat running on neutral early downs in 21 of 21 seasons.** The gap in expected points per play ranged from 0.11 to 0.24; 2025 was 0.14. Success rate favored passing by 9.4 points in 2025.
2. **Teams barely moved.** Neutral early-down pass rate went from 48% in 2006 to 52% in 2025.
3. **But passing more is not a free lunch at team level.** In 2025, a team's pass rate over expected correlated only r = 0.20 with its EPA per play. The league edge is real; whether a given team can cash it depends on its QB and line. That is consistent with MacKelvie's game-theory point (the run keeps defenses honest), though this data cannot prove it.

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
