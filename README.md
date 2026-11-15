<p align="center"><img src="assets/banner.png" alt="NFL Analytics by Dylan Fanelli" width="100%"></p>

<p align="center"><a href="https://github.com/IForSureI/NFL-Analytics/actions/workflows/tests.yml"><img src="https://github.com/IForSureI/NFL-Analytics/actions/workflows/tests.yml/badge.svg" alt="tests"></a> <img src="https://img.shields.io/badge/python-3.10%2B-1d2433" alt="python: 3.10+"> <img src="https://img.shields.io/badge/data-nflverse%202006--2026-1d2433" alt="data: nflverse 2006-2026"> <img src="https://img.shields.io/badge/studies-9-c2410c" alt="studies: 9"> <img src="https://img.shields.io/badge/refreshed-Nov%2010%202026-6b7280" alt="refreshed: Nov 10 2026"> <img src="https://img.shields.io/badge/license-all%20rights%20reserved-6b7280" alt="license: all rights reserved"></p>

<p align="center"><b><a href="#the-studies">Studies</a> &nbsp;|&nbsp; <a href="#what-a-club-gets">What a club gets</a> &nbsp;|&nbsp; <a href="#how-i-work">How I work</a> &nbsp;|&nbsp; <a href="#under-the-hood">Under the hood</a> &nbsp;|&nbsp; <a href="docs/glossary.md">Glossary</a> &nbsp;|&nbsp; <a href="#about">About</a></b></p>

I'm Dylan Fanelli, and this is the NFL analytics portfolio I am building toward a job in a club front office. Each study starts from a question a coach, scout or general manager actually argues about, answers it with public data and a model I built, and ends with what a club would do with the answer. I test each model out of sample or with a bootstrap where the data allows and say so where it does not, I say what the data can't show, and the numbers on the study pages are written by code from each study's `findings.json`, not typed by hand.

**Headline work:** a [fourth-down decision bot](reports/02-fourth-down-bot/) on my own win-probability model, which comes close to nflfastR out of sample without beating it (Brier 0.1495 vs 0.1488 on 80,613 plays), and a [test of whether teams overpay for sacks](reports/07-box-score-tax/): a sack beyond what pressures predict adds about \$0.57M a year to a contract, and against a pressure it is priced 2.1 times what it predicts (90% interval 1.0 to 8.8).

<p align="center"><img src="assets/at-a-glance.png" alt="Selected studies at a glance" width="100%"></p>

<p><img src="assets/img/strip-helmets.jpg" width="100%" alt="All 32 NFL helmets on one wall"></p>

## The studies

| # | Study | The question | Headline | Methods |
|---|---|---|---|---|
| 01 | [**Flag Audit**](reports/01-flag-audit/) | Do NFL flags really even out, or do some teams, quarterbacks and crews get a different game? | Road teams drew 0.27 more judgment-call flags a game than home teams in 2016-22; since 2023 the gap has averaged 0.00. The drop is real per snap (95% interval 0.02 to 0.29 per 100 snaps) but not yet in close games only, and I picked 2023 from the chart. | empirical Bayes, Wilson intervals, split-half reliability |
| 02 | [**Fourth-Down Bot**](reports/02-fourth-down-bot/) | When the math says go for it on fourth down, how often do coaches go, and can the cost be pinned on a team? | I built a win-probability model that comes close to nflfastR out of sample (Brier 0.1495 vs 0.1488 on 80,613 plays) and a fourth-down bot on top of it. | gradient boosting, win probability, decision analysis, game bootstrap |
| 03 | [**Sack Leverage**](reports/03-sack-leverage/) | Are all sacks equal, or does the down and distance decide how much a sack is worth? | Distance decides a sack's worth: 3rd-and-1-2 takes 2.46 expected points, 3rd-and-11+ only 1.53. At the same distance a third-down sack costs more than a second-down sack except at 11+ yards (-0.04, interval -0.15 to +0.07). | expected points, replication, game bootstrap, stability test |
| 04 | [**Luck Index**](reports/04-luck-index/) | How many wins does chance hand out, and do lucky wins carry over to the next year? | Fumble, field-goal and close-game luck do not repeat (year-to-year r = 0.04, 0.07, 0.06). | Pythagorean expectation, regression to the mean, year-to-year stability |
| 05 | [**Kickoff Value**](reports/05-kickoff-value/) | What did the new kickoff rule do to field position, and can kickers and returners be told apart under it? | The new kickoff brought returns back: 21% of kickoffs returned in 2023, 75% in 2025, and drives start 5.2 yards further up. | rule-change analysis, special teams, empirical Bayes, split-half reliability |
| 06 | [**Pass vs Run**](reports/06-pass-run/) | Passing has been more efficient for years. So why do teams still run, and does passing more make a team better? | Passing beat running on neutral early downs in 21 of 21 seasons. | EPA, pass rate over expected, team bootstrap |
| 07 | [**The Box-Score Tax**](reports/07-box-score-tax/) | Do NFL teams pay pass rushers more for sacks than sacks predict, when pressures predict future sacks better? | A sack beyond what pressures predict adds about \$0.57M a year to a veteran contract (775 contracts, 95% CI \$0.30-0.84M) and predicts 0.13 extra sacks the next year. | clustered OLS, player bootstrap, contract valuation, market pricing |
| 08 | [**The YAC Tax**](reports/08-yac-tax/) | Do teams pay receivers for yards after the catch that won't come back? | No YAC tax detected: \$4.71M per 100 future yards bought through YAC over expected vs \$4.55M through air yards (371 veteran WR/TE contracts). | Next Gen Stats, clustered OLS, player bootstrap, null result |
| 09 | [**Run Game Value**](reports/09-run-game-value/) | How much of a running back's production is his, and do contracts pay for that part? | Inconclusive on 160 contracts: I expected teams to pay blocked yards like the back's own, and the data neither shows that nor rules it out. Holding carries fixed, +1 yard over expected per carry adds \$3.06M a year vs \$2.21M for +1 expected yard per carry (160 contracts); per yard the gap is 2.54x but fades to 1.23x with workload controlled. | Next Gen Stats, clustered OLS, bootstrap, contract valuation, null result |

<table>
<tr><td width="25%" valign="top"><a href="reports/01-flag-audit/"><img src="reports/01-flag-audit/home_edge.png" width="100%"></a><br><sub><b>01 Flag Audit</b></sub></td><td width="25%" valign="top"><a href="reports/02-fourth-down-bot/"><img src="reports/02-fourth-down-bot/go_rate_trend.png" width="100%"></a><br><sub><b>02 Fourth-Down Bot</b></sub></td><td width="25%" valign="top"><a href="reports/03-sack-leverage/"><img src="reports/03-sack-leverage/epa_per_sack.png" width="100%"></a><br><sub><b>03 Sack Leverage</b></sub></td><td width="25%" valign="top"><a href="reports/04-luck-index/"><img src="reports/04-luck-index/luck_regression.png" width="100%"></a><br><sub><b>04 Luck Index</b></sub></td></tr>
<tr><td width="25%" valign="top"><a href="reports/05-kickoff-value/"><img src="reports/05-kickoff-value/kickoff_era.png" width="100%"></a><br><sub><b>05 Kickoff Value</b></sub></td><td width="25%" valign="top"><a href="reports/06-pass-run/"><img src="reports/06-pass-run/epa_pass_vs_run.png" width="100%"></a><br><sub><b>06 Pass vs Run</b></sub></td><td width="25%" valign="top"><a href="reports/07-box-score-tax/"><img src="reports/07-box-score-tax/sack_tax.png" width="100%"></a><br><sub><b>07 The Box-Score Tax</b></sub></td><td width="25%" valign="top"><a href="reports/08-yac-tax/"><img src="reports/08-yac-tax/yac_tax.png" width="100%"></a><br><sub><b>08 The YAC Tax</b></sub></td></tr>
<tr><td width="25%" valign="top"><a href="reports/09-run-game-value/"><img src="reports/09-run-game-value/rb_price.png" width="100%"></a><br><sub><b>09 Run Game Value</b></sub></td></tr>
</table>

## 2026 in-season snippets

Twelve quick charts on the season in progress, through Weeks 1-9: QB, running back, receiver, pass rusher, defense, kicker and team views. [See them all](reports/2026-in-season-snippets/). **Hover for the breakdown:** the [interactive version](https://iforsurei.github.io/NFL-Analytics/snippets.html) opens every player's and team's numbers by down, by depth and week by week.

<table><tr><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/qb_epa_cpoe.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/team_tiers.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/early_down_proe.png" width="100%"></a></td></tr><tr><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/receiver_share.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/rb_success.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/defense_pressure.png" width="100%"></a></td></tr></table>

## Draft board: 2027 quarterbacks

[**Drew Mestemaker, QB, Oklahoma State: is he QB1?**](reports/draft-2027-drew-mestemaker/) NFL scouts have him first. Through 9 games he has 2,962 yards and 29 touchdowns, but against what his opponents allow he is +28.3 rating points over expected, #4 of 7 in the class and below the first-round median (+42.4). The evaluation uses nine-game comparisons with every first-round quarterback since 2021, an opponent adjustment, base rates (6 of 17 quarterbacks with a rating like his went in round 1) and a test of which numbers repeat.

<p align="center"><a href="reports/draft-2027-drew-mestemaker/"><img src="reports/draft-2027-drew-mestemaker/opponent_adjusted.png" width="720"></a></p>

## Coming next

New studies are on the way; each follows the same [report standard](docs/report-standard.md).

| # | Study | The question |
|---|---|---|
| 10 | Draft Value | In rounds 3-7, which positions return the most value per pick? |
| 11 | Turnovers Forced | Do defenses that force turnovers keep doing it, and does a takeaway-heavy year fool people? |
| 12 | Backup QB Value | What is a good backup quarterback worth, in expected wins and in cap dollars? |

<a id="what-a-club-gets"></a>
## What a club gets

| Department | Question it answers | Study |
|---|---|---|
| Head coach and game management | Go, kick or punt on this fourth down? | [02 Fourth-Down Bot](reports/02-fourth-down-bot/) |
| Pro personnel and free agency | Are pass rushers, receivers and running backs priced for what repeats? Who to target in free agency? | [07 Box-Score Tax](reports/07-box-score-tax/), [08 YAC Tax](reports/08-yac-tax/), [09 Run Game Value](reports/09-run-game-value/) |
| Defensive staff | When is a sack worth the most? | [03 Sack Leverage](reports/03-sack-leverage/) |
| Offensive staff | Should we pass more on early downs? | [06 Pass vs Run](reports/06-pass-run/) |
| Special teams | What is a kickoff worth under the new rule, and can returners or kickers be told apart yet? | [05 Kickoff Value](reports/05-kickoff-value/) |
| Front office and ownership | How much of our record will carry over, and how much was the bounces? | [04 Luck Index](reports/04-luck-index/) |
| Game prep | What does this crew call, and where does the road flag gap sit? | [01 Flag Audit](reports/01-flag-audit/) |

<a id="how-i-work"></a>
## How I work

Every study follows the same [report standard](docs/report-standard.md), modeled on how Big Data Bowl entries, Open Source Football articles and the nflverse model write-ups are built:

1. **A question first,** stated before the data, with prior public work credited.
2. **Stability before value.** A stat has to repeat before it can be called a skill or priced.
3. **Validation in the open:** out-of-sample tests, calibration, bootstraps, clustered standard errors and robustness tables.
4. **Results under headings that state the finding,** each with its figure.
5. **What a club does with it,** limitations and next steps on every page.
6. **Reproducible:** one command re-downloads the data and rebuilds the studies, charts and pages; `pytest` (run by GitHub Actions on every change, Python 3.10 and 3.12) tests the model and study logic on small made-up tables, checks that saved results are internally consistent, and checks that every page meets the standard. The tests do not prove a finding is right.

**Techniques used here:** gradient-boosted win probability with monotone constraints; decision analysis; expected points (EPA); empirical-Bayes shrinkage and Wilson intervals; split-half and year-to-year reliability; OLS with player-clustered standard errors; bootstrap resampling; Pythagorean expectation; contract valuation in cap-share terms; DuckDB SQL.

<a id="under-the-hood"></a>
## Under the hood

```mermaid
flowchart LR
    A[nflverse data<br>play-by-play, NGS, PFR,<br>Over The Cap, snaps] --> B[nflan library<br>loaders, WP model,<br>4th-down bot, stats]
    B --> C[projects/<br>one script per study]
    C --> D[reports/<br>findings.json, CSVs, charts]
    D --> E[scripts/build_readmes.py<br>scripts/build_figures.py]
    E --> F[README pages]
    B --> G[pytest<br>logic tests on made-up data,<br>consistency and page checks]
    D --> G
```

```
nflan/          library: data loading, win-probability model, 4th-down bot, penalty and stats helpers (unit-tested in tests/)
projects/       one script per study (python -m projects.<name>)
reports/        each study's write-up, figures, CSV outputs and findings.json
sql/            DuckDB queries answering the same questions straight from the parquet files
scripts/        update.py (weekly refresh), build_readmes.py, build_figures.py, report_meta.py
tests/          logic tests on made-up data, consistency checks on saved results, page-standard checks
docs/           report standard, glossary, data dictionary, inspiration notes
assets/         banner and at-a-glance figure
```

### Reproduce

```bash
pip install -r requirements.txt
python scripts/update.py          # downloads nflverse data (about 400 MB), runs every study, figures, tests and READMEs (the fourth-down bootstrap takes a while)
pytest -q
```

Each study also runs alone, for example `python -m projects.fourth_down_bot`.

## Data, glossary and credit

- Data: [nflverse](https://github.com/nflverse/nflverse-data) (CC-BY 4.0): play-by-play with nflfastR's EPA and win-probability models, officials, NFL Next Gen Stats, Pro Football Reference advanced stats, snap counts and Over The Cap contracts. See the [data dictionary](docs/data-dictionary.md).
- Terms used on these pages (EPA, WP, Brier score, PROE, clustered standard errors and more): [glossary](docs/glossary.md).
- Fourth-down method: the public idea behind [nfl4th](https://github.com/nflverse/nfl4th) by Ben Baldwin, rebuilt from scratch in Python.
- Inspiration: **Michael MacKelvie** (data storytelling) and **Brett Kollmann** (film plus numbers); each report links the video that started it. Notes in [`docs/inspiration.md`](docs/inspiration.md).
- All analysis, and any mistakes, are mine.

## Changelog

- 2026-11-14: 04: lucky teams compared with same-record teams, so regression to the mean is not counted as luck (a win above Pythagorean is worth -0.02 wins next year, 95% interval -0.18 to 0.15; a Pythagorean win 0.49). 06: the team-level link is tested on 640 team-seasons, not one season of 32 (r = 0.28, 95% interval 0.19 to 0.38), and within teams. 01: the road-flag drop is reported per snap, in close games and for every break year; it is 0.16 per 100 snaps (0.02 to 0.29) on all snaps and not clear of zero in close games, and 2023 was picked from the chart. No quarterback stays above the league roughing rate after correcting for 42 tests. 09: verdict changed from "hypothesis failed" to inconclusive, with the smallest detectable price gap (\$2.9M per yard per carry) stated; rerun on Next Gen Stats through Week 10.
- 2026-11-14: Snippets: 95% intervals on every correlation, sample warnings on the ranked lists, and the pressure chart no longer claims a link the interval does not support (r = -0.24, -0.58 to 0.23). Tests: checks that asserted a study's conclusion are replaced by logic tests on made-up data (win-probability model, fourth-down arithmetic, field-goal range, contract dedupe, sack luck, kickoff helpers, the matched luck comparison, bootstraps) plus consistency checks on saved results; 59 tests. `scripts/update.py` now refreshes contracts, PFR charting, players, snap counts, draft picks and Next Gen Stats, not only play-by-play and officials. README claims about validation and tests reworded to what the code does.
- 2026-11-15: Draft report rebuilt as an evaluation after an independent review found the first version read as advocacy (reports/draft-2027-drew-mestemaker). The title is now a question, and the grade is first-round candidate, not QB1 on the numbers. Added: an opponent adjustment (FBS games only, rating over what each defense allows everyone else: he is +28.3, #4 of 7 in the class, first-round median +42.4); nine-game comparisons with each first-round quarterback's first nine games; comps from all 600 prior qualifying seasons with draft outcomes; base rates (6 of 17 quarterbacks with a last-season rating like his went in round 1); Wilson intervals on the 25+ rate and interception rate; the North Texas baseline before and after him. Corrected: the Group of Five to Power Four comparison is now FBS games only (his rating went 166.9 to 164.0, -2.9; the earlier +4.3 came from the FCS game), with the other 19 movers' spread (SD 20.1) and his rank on change (#9 of 20). Still through nine games: cfbstats had not posted the Nov. 14 Texas Tech game when this was built. Tests added for the interval, the opponent adjustment and the draft-outcome match.

Full history: [LOG.md](LOG.md). Data refreshes weekly in season (last: November 10, 2026, through the latest completed week of 2026).

## License and citation

© 2026 Dylan Fanelli. All rights reserved. The code, reports and figures may be viewed here; they may not be copied, modified or used without written permission. See [LICENSE](LICENSE). To cite this work, use the **Cite this repository** button (from [CITATION.cff](CITATION.cff)).

<a id="about"></a>
## About

<table>
<tr>
<td width="32%" valign="top"><img src="assets/img/about-nfl.jpg" width="100%" alt="Dylan Fanelli at the NFL offices in New York City"><br><sub>At the NFL offices in New York City</sub></td>
<td valign="top">

Dylan Fanelli, M.S. Sport Management candidate at UMass Amherst (Mark H. McCormack Department). I am building this portfolio to show proficiency in NFL statistics and sabermetrics-style analysis.

I also keep a [baseball analytics portfolio](https://github.com/IForSureI/Dylan-Fanelli-Baseball-Analytics-Portfolio). [LinkedIn](https://www.linkedin.com/in/dylanfanelli/)

<sub>Photos are my own.</sub>

</td>
</tr>
</table>
