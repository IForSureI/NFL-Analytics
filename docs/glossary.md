# Glossary

Terms used across the studies, in plain language first and the formal version second.

| Term | Plain language | Formal |
|---|---|---|
| **EPA** (expected points added) | How much a play changed the expected value of the next score, from the offense's side | $`\text{EPA} = EP_{\text{after}} - EP_{\text{before}}`$, using nflfastR's expected-points model |
| **EP** (expected points) | The average next score from this down, distance and field position | nflfastR multinomial model of the next scoring event |
| **WP** (win probability) | Chance the team with the ball wins from here | Study 02 builds its own gradient-boosted model; nflfastR's is the benchmark |
| **Brier score** | How far probability forecasts are from what happened; lower is better | $`\frac{1}{N}\sum_i (p_i - y_i)^2`$ |
| **Calibration** | When the model says 70%, does the team win about 70% of the time? | Predicted vs observed win rate by probability bin |
| **Success rate** | Share of plays with positive EPA | $`\Pr(\text{EPA} > 0)`$ |
| **Neutral situation** | Plays where the score does not force the play call | Win probability 20-80%, outside the last 2 minutes of a half |
| **PROE** (pass rate over expected) | How much more a team passes than the situation calls for | Actual dropback rate minus mean nflfastR `xpass` |
| **Pythagorean wins** | Wins a team "should" have from points scored and allowed | $`\frac{PF^{2.37}}{PF^{2.37} + PA^{2.37}}`$ times games |
| **Year-to-year r** | How much a stat repeats from one season to the next; 1 = perfectly, 0 = not at all | Pearson correlation between season $`t`$ and $`t+1`$ for the same player or team |
| **Split-half reliability** | Same idea within a season | Correlation between odd-week and even-week averages |
| **Empirical Bayes shrinkage** | Pull small samples toward the league average so noise is not ranked | Beta-binomial posterior mean |
| **Wilson interval** | A 95% range for a rate that behaves well with small samples | Wilson score interval |
| **Clustered standard errors** | Honest uncertainty when the same player or team appears many times | Cluster-robust covariance by player or team |
| **Bootstrap** | Re-run the analysis on resampled data many times to see how much the answer moves | 1,000 resamples by player |
| **APY % of cap** | A contract's average annual value as a share of that year's salary cap, so 2019 and 2026 deals compare | APY divided by the league cap in the signing year |
| **Platform season** | The season right before a contract is signed | |
| **Pressure** (PFR) | Sacks plus hurries plus QB knockdowns | Pro Football Reference charting |
| **Sack luck** | Sacks beyond what a player's pressures predict | Sacks minus 0.264 times pressures |
| **YAC over expected** (YACOE) | Yards after the catch beyond what a typical receiver gets on the same catches | NFL Next Gen Stats |
| **Rush yards over expected** (RYOE) | A back's rushing yards beyond what a typical back gains on the same carries, given blockers, defenders and box count at the handoff; expected yards are the rest | NFL Next Gen Stats |
| **Touchback spot** | Where a kickoff touchback puts the ball (own 25 through 2023, 30 in 2024, 35 from 2025) | |
