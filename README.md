<p align="center"><img src="assets/banner.png" alt="NFL Analytics by Dylan Fanelli" width="100%"></p>

<p align="center"><a href="https://github.com/IForSureI/NFL-Analytics/actions/workflows/tests.yml"><img src="https://github.com/IForSureI/NFL-Analytics/actions/workflows/tests.yml/badge.svg" alt="tests"></a> <img src="https://img.shields.io/badge/python-3.10%2B-1d2433" alt="python: 3.10+"> <img src="https://img.shields.io/badge/data-nflverse%202006--2026-1d2433" alt="data: nflverse 2006-2026"> <img src="https://img.shields.io/badge/studies-13-c2410c" alt="studies: 13"> <img src="https://img.shields.io/badge/refreshed-Nov%2017%202026-6b7280" alt="refreshed: Nov 17 2026"> <img src="https://img.shields.io/badge/license-all%20rights%20reserved-6b7280" alt="license: all rights reserved"></p>

<p align="center"><b><a href="#the-studies">Studies</a> &nbsp;|&nbsp; <a href="#what-a-club-gets">What a club gets</a> &nbsp;|&nbsp; <a href="#how-i-work">How I work</a> &nbsp;|&nbsp; <a href="#under-the-hood">Under the hood</a> &nbsp;|&nbsp; <a href="docs/glossary.md">Glossary</a> &nbsp;|&nbsp; <a href="#about">About</a></b></p>

I'm Dylan Fanelli, and this is the NFL analytics portfolio I am building toward a job in a club front office. Each study starts from a question a coach, scout or general manager actually argues about, answers it with public data and a model I built, and ends with what a club would do with the answer. I test each model out of sample or with a bootstrap where the data allows and say so where it does not, I say what the data can't show, and the numbers on the study pages are written by code from each study's `findings.json`, not typed by hand.

**Headline work:** a [fourth-down decision bot](reports/02-fourth-down-bot/) on my own win-probability model, which comes close to nflfastR out of sample without beating it (Brier 0.1495 vs 0.1488 on 80,613 plays), and a [test of whether teams overpay for sacks](reports/07-box-score-tax/): a sack beyond what pressures predict adds about \$0.57M a year to a contract, and against a pressure it is priced 2.1 times what it predicts (90% interval 1.0 to 8.8).

<p align="center"><img src="assets/at-a-glance.png" alt="Selected studies at a glance" width="100%"></p>

<p><img src="assets/img/strip-helmets.jpg" width="100%" alt="All 32 NFL helmets on one wall"></p>

## The studies

| # | Study | The question | Headline | Methods |
|---|---|---|---|---|
| 01 | [**Flag Audit**](reports/01-flag-audit/) | Do NFL flags really even out, or do some teams, quarterbacks and crews get a different game? | Road teams drew 0.27 more judgment-call flags a game than home teams in 2016-22; since 2023 the gap has averaged 0.00. The drop is real per snap (95% interval 0.02 to 0.29 per 100 snaps) but not yet in close games only, and I picked 2023 from the chart. | empirical Bayes, Wilson intervals, split-half reliability |
| 02 | [**Fourth-Down Bot**](reports/02-fourth-down-bot/) | When the math says go for it on fourth down, how often do coaches go, and can the cost be pinned on a team? | I built a win-probability model that comes close to nflfastR out of sample (Brier 0.1495 vs 0.1488 on 80,613 plays) and a fourth-down bot on top of it. Its conversion, field-goal and punt models, fit on 2016-2023, all beat the league average on 2024-2026, and a bot fit on those seasons alone changes 3.5% of the recommendations and leaves the go rate and every team on the card inside their intervals. | gradient boosting, win probability, decision analysis, game bootstrap |
| 03 | [**Sack Leverage**](reports/03-sack-leverage/) | Are all sacks equal, or does the down and distance decide how much a sack is worth? | Distance decides a sack's worth: 3rd-and-1-2 takes 2.46 expected points, 3rd-and-11+ only 1.53. At the same distance a third-down sack costs more than a second-down sack except at 11+ yards (-0.04, interval -0.15 to +0.07). | expected points, replication, game bootstrap, stability test |
| 04 | [**Luck Index**](reports/04-luck-index/) | How many wins does chance hand out, and do lucky wins carry over to the next year? | Fumble, field-goal and close-game luck do not repeat (year-to-year r = 0.04, 0.07, 0.06). | Pythagorean expectation, regression to the mean, year-to-year stability |
| 05 | [**Kickoff Value**](reports/05-kickoff-value/) | What did the new kickoff rule do to field position, and can kickers and returners be told apart under it? | The new kickoff brought returns back: 21% of kickoffs returned in 2023, 75% in 2025, and drives start 5.2 yards further up. | rule-change analysis, special teams, empirical Bayes, split-half reliability |
| 06 | [**Pass vs Run**](reports/06-pass-run/) | Passing has been more efficient for years. So why do teams still run, and does passing more make a team better? | Passing beat running on neutral early downs in 21 of 21 seasons. | EPA, pass rate over expected, team bootstrap |
| 07 | [**The Box-Score Tax**](reports/07-box-score-tax/) | Do NFL teams pay pass rushers more for sacks than sacks predict, when pressures predict future sacks better? | A sack beyond what pressures predict adds about \$0.57M a year to a veteran contract (775 contracts, 95% CI \$0.30-0.84M) and predicts 0.13 extra sacks the next year. | clustered OLS, player bootstrap, contract valuation, market pricing |
| 08 | [**The YAC Tax**](reports/08-yac-tax/) | Do teams pay receivers for yards after the catch that won't come back? | No YAC tax detected: \$4.71M per 100 future yards bought through YAC over expected vs \$4.55M through air yards (371 veteran WR/TE contracts). | Next Gen Stats, clustered OLS, player bootstrap, null result |
| 09 | [**Run Game Value**](reports/09-run-game-value/) | How much of a running back's production is his, and do contracts pay for that part? | Inconclusive on 160 contracts: I expected teams to pay blocked yards like the back's own, and the data neither shows that nor rules it out. Holding carries fixed, +1 yard over expected per carry adds \$3.06M a year vs \$2.21M for +1 expected yard per carry (160 contracts); per yard the gap is 2.54x but fades to 1.23x with workload controlled. | Next Gen Stats, clustered OLS, bootstrap, contract valuation, null result |
| 10 | [**Draft Value**](reports/10-draft-value/) | In rounds 3-7, which positions return the most value per pick, and are some positions drafted too late? | In rounds 3-7, linemen beat their slot in career AV (OT +29%, IOL +26%, IDL +21%, intervals clear of zero) but second-contract money does not clearly confirm it; the only clear money gap is running backs (-0.36 points of cap a year, -28% vs slot), and the two measures disagree most on quarterbacks and tight ends (rank r across 11 positions 0.18, 0.58 without quarterbacks). | pick-value curve, kernel smoothing, bootstrap, cross-validation, contract valuation |
| 11 | [**Turnovers Forced**](reports/11-turnovers-forced/) | Do defenses that force turnovers keep doing it, and does a takeaway-heavy year fool people? | Top-5 takeaway defenses keep 10% of their takeaway edge next year, but whether a takeaway year fools people is inconclusive: against same-points defenses their points allowed move -0.05 per game (95% interval -1.27 to +1.11), and my hypothesis predicts +0.47. | play-by-play, franchise bootstrap, clustered OLS, out-of-sample, inconclusive test |
| 12 | [**Backup QB Value**](reports/12-backup-qb-value/) | How many wins does a backup quarterback start cost, and what is a good backup worth in cap dollars? | A \$10M backup over a \$2M one saves about 0.05 wins a season (95% interval -0.007 to +0.087), worth \$0.4M to \$2.3M depending on the price per win: my bet that a good backup is underpriced insurance failed. | play-by-play, fixed effects, clustered OLS, franchise bootstrap, contract valuation, hypothesis failed |
| 13 | [**Metric Stability Atlas**](reports/13-metric-stability-atlas/) | Which team and player numbers can a club trust, and after how many games? | Offense numbers settle faster than defense numbers: offense EPA per play is half signal after 5.3 games (95% interval 4.5 to 6.5), defense EPA per play after 14.2 (11.7 to 18.0), and 16 of 36 team numbers are still less than half signal after a full season. | split-half reliability, regression to the mean, year-to-year stability, out-of-sample test, team bootstrap |

<table>
<tr><td width="25%" valign="top"><a href="reports/01-flag-audit/"><img src="reports/01-flag-audit/home_edge.png" width="100%"></a><br><sub><b>01 Flag Audit</b></sub></td><td width="25%" valign="top"><a href="reports/02-fourth-down-bot/"><img src="reports/02-fourth-down-bot/go_rate_trend.png" width="100%"></a><br><sub><b>02 Fourth-Down Bot</b></sub></td><td width="25%" valign="top"><a href="reports/03-sack-leverage/"><img src="reports/03-sack-leverage/epa_per_sack.png" width="100%"></a><br><sub><b>03 Sack Leverage</b></sub></td><td width="25%" valign="top"><a href="reports/04-luck-index/"><img src="reports/04-luck-index/luck_regression.png" width="100%"></a><br><sub><b>04 Luck Index</b></sub></td></tr>
<tr><td width="25%" valign="top"><a href="reports/05-kickoff-value/"><img src="reports/05-kickoff-value/kickoff_era.png" width="100%"></a><br><sub><b>05 Kickoff Value</b></sub></td><td width="25%" valign="top"><a href="reports/06-pass-run/"><img src="reports/06-pass-run/epa_pass_vs_run.png" width="100%"></a><br><sub><b>06 Pass vs Run</b></sub></td><td width="25%" valign="top"><a href="reports/07-box-score-tax/"><img src="reports/07-box-score-tax/sack_tax.png" width="100%"></a><br><sub><b>07 The Box-Score Tax</b></sub></td><td width="25%" valign="top"><a href="reports/08-yac-tax/"><img src="reports/08-yac-tax/yac_tax.png" width="100%"></a><br><sub><b>08 The YAC Tax</b></sub></td></tr>
<tr><td width="25%" valign="top"><a href="reports/09-run-game-value/"><img src="reports/09-run-game-value/rb_price.png" width="100%"></a><br><sub><b>09 Run Game Value</b></sub></td><td width="25%" valign="top"><a href="reports/10-draft-value/"><img src="reports/10-draft-value/gm_one_page.png" width="100%"></a><br><sub><b>10 Draft Value</b></sub></td><td width="25%" valign="top"><a href="reports/11-turnovers-forced/"><img src="reports/11-turnovers-forced/stability.png" width="100%"></a><br><sub><b>11 Turnovers Forced</b></sub></td><td width="25%" valign="top"><a href="reports/12-backup-qb-value/"><img src="reports/12-backup-qb-value/two_vs_ten.png" width="100%"></a><br><sub><b>12 Backup QB Value</b></sub></td></tr>
<tr><td width="25%" valign="top"><a href="reports/13-metric-stability-atlas/"><img src="reports/13-metric-stability-atlas/team_atlas.png" width="100%"></a><br><sub><b>13 Metric Stability Atlas</b></sub></td></tr>
</table>

## 2026 in-season snippets

Twelve quick charts on the season in progress, through Weeks 1-10: QB, running back, receiver, pass rusher, defense, kicker and team views. [See them all](reports/2026-in-season-snippets/). **Hover for the breakdown:** the [interactive version](https://iforsurei.github.io/NFL-Analytics/snippets.html) opens every player's and team's numbers by down, by depth and week by week.

<table><tr><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/qb_epa_cpoe.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/team_tiers.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/early_down_proe.png" width="100%"></a></td></tr><tr><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/receiver_share.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/rb_success.png" width="100%"></a></td><td width="33%"><a href="reports/2026-in-season-snippets/"><img src="reports/2026-in-season-snippets/defense_pressure.png" width="100%"></a></td></tr></table>

## Draft board: 2027 quarterbacks

[**Drew Mestemaker, QB, Oklahoma State: is he QB1?**](reports/draft-2027-drew-mestemaker/) NFL scouts have him first. Through 10 games he has 3,239 yards and 30 touchdowns, but against what his opponents allow he is +24.3 rating points over expected, #5 of 7 in the class and below the first-round median (+42.4). The evaluation uses ten-game comparisons with every first-round quarterback since 2021, an opponent adjustment, base rates (6 of 17 quarterbacks with a rating like his went in round 1) and a test of which numbers repeat.

<p align="center"><a href="reports/draft-2027-drew-mestemaker/"><img src="reports/draft-2027-drew-mestemaker/opponent_adjusted.png" width="720"></a></p>

<a id="what-a-club-gets"></a>
## What a club gets

| Department | Question it answers | Study |
|---|---|---|
| Head coach and game management | Go, kick or punt on this fourth down? | [02 Fourth-Down Bot](reports/02-fourth-down-bot/) |
| Pro personnel and free agency | Are pass rushers, receivers and running backs priced for what repeats? Who to target in free agency? | [07 Box-Score Tax](reports/07-box-score-tax/), [08 YAC Tax](reports/08-yac-tax/), [09 Run Game Value](reports/09-run-game-value/) |
| Defensive staff | When is a sack worth the most? Are our takeaways a skill or a hot streak? | [03 Sack Leverage](reports/03-sack-leverage/), [11 Turnovers Forced](reports/11-turnovers-forced/) |
| Offensive staff | Should we pass more on early downs? | [06 Pass vs Run](reports/06-pass-run/) |
| Special teams | What is a kickoff worth under the new rule, and can returners or kickers be told apart yet? | [05 Kickoff Value](reports/05-kickoff-value/) |
| Front office and ownership | How much of our record will carry over, and how much was the bounces? | [04 Luck Index](reports/04-luck-index/) |
| Pro personnel and cap planning | What is a backup quarterback worth, and which teams are most exposed if the starter goes down? | [12 Backup QB Value](reports/12-backup-qb-value/) |
| Game prep | What does this crew call, and where does the road flag gap sit? | [01 Flag Audit](reports/01-flag-audit/) |
| College scouting and the draft room | In rounds 3-7, which positions return more than their slot, and on which measure? | [10 Draft Value](reports/10-draft-value/) |
| Every department | Which of this week's numbers can we trust, and how far should we regress the rest? | [13 Metric Stability Atlas](reports/13-metric-stability-atlas/) |

<a id="how-i-work"></a>
## How I work

Every study follows the same [report standard](docs/report-standard.md), modeled on how Big Data Bowl entries, Open Source Football articles and the nflverse model write-ups are built:

1. **A question first,** stated before the data, with prior public work credited.
2. **Stability before value.** A stat has to repeat before it can be called a skill or priced.
3. **Validation in the open:** out-of-sample tests, calibration, bootstraps, clustered standard errors and robustness tables.
4. **Results under headings that state the finding,** each with its figure.
5. **What a club does with it,** limitations and next steps on every page.
6. **Reproducible:** one command re-downloads the data and rebuilds the studies, charts and pages; `pytest` (run by GitHub Actions on every change, Python 3.10 and 3.12) tests the model and study logic on small made-up tables, checks that saved results are internally consistent, and checks that every page meets the standard. The tests do not prove a finding is right.

**Techniques used here:** gradient-boosted win probability with monotone constraints; decision analysis; expected points (EPA); empirical-Bayes shrinkage and Wilson intervals; split-half and year-to-year reliability with regression constants (Spearman-Brown); OLS with player-clustered standard errors; bootstrap resampling; Pythagorean expectation; contract valuation in cap-share terms; DuckDB SQL.

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

- 2026-11-17: Weekly refresh through Week 10, snippets and the interactive page only (26,246 regular-season plays in the snippets, weeks 1-10; nflverse play-by-play pulled 2026-11-17, all 14 Week 10 games through LAC-BAL on Monday night). B.Purdy still leads EPA per dropback (+0.311), JAX net EPA per play (+0.234), B.Corum RB success rate (57.3%), S.Shrader FG points over expected (+10.9) and G.Rousseau sacks plus QB hits (27). Run and pass defense now line up more closely (r = 0.55, 0.26 to 0.76; it was 0.41). The twelve charts, docs/snippets.html and the READMEs are rebuilt; I did not rerun the eleven studies this week, so their numbers stay as last built.
- 2026-11-18: Draft report on Drew Mestemaker refreshed through 10 games, adding the Texas Tech game of Nov. 14 (27-of-42, 277 yards, 1 TD, 2 INT in a 27-52 loss). His 2026 line is now 233-of-351, 3,239 yards, 30 TD, 10 INT, a 166.4 rating. Against schedule he goes from +28.3 (#4 of 7) to +24.3 (#5 of 7: Carr and Leavitt are now ahead of him as well as Mensah and Sayin); through 10 games his rating is ahead of 4 of 18 first-round quarterbacks at the same point, down from 6; against FBS opponents his change moving to the Big 12 is now -8.8 (the other 19 movers average -6.0). Julian Sayin has not played since Oct. 17 and dropped off the cfbstats national list (75% of team games), so he stays in the class comparison from his own cfbstats pages but is out of the national ranks; passers who drop off the list still count as in college for the base rates. Sentences that assumed nine games now read from the data. Data: cfbstats.com season, situational, game-log, split and team defense tables pulled 2026-11-18 (games through Nov. 17).
- 2026-11-26: Study 12 The Backup Quarterback: a start costs a tenth of a win, but a \$10M backup does not pay for itself (my bet that a good backup is underpriced insurance failed). Against the same team's starter games in the same season (1,695 backup starts, 2006-2025, team-season fixed effects, opponent and home controls, errors clustered by franchise), a backup start costs 4.0 points of margin (95% interval 3.0 to 5.0), 0.11 wins at 0.0279 wins per point; teams average 2.8 backup starts a season. A \$10M backup over a \$2M one saves 0.051 wins a season (-0.007 to +0.087), worth \$0.36M at the quarterback-market price (\$7.1M a win) or \$2.28M at a league-wide \$45M a win, against an \$8M cost; the backup's record predicts the drop better than his contract does. 2026, rest of the season, teams with their starter in place: no team above 0.27 expected wins lost; starters with an injury history most exposed: CLE, DAL, TB, CHI, JAX, every name news-checked 2026-11-26. Data: nflverse play-by-play (pulled 2026-11-26, through Week 11), Over The Cap contracts, injury reports and the 2026-11-25 depth chart; the raw copy on the My Passport drive is updated (injury reports, depth charts and weekly rosters added; play-by-play, contracts and players refreshed). Independent review corrections applied (partial games no longer read as missed games, depth-chart starters, the rest-of-season rate, contract extensions, the pay effect's interval). New code: projects/backup_qb_value.py; tests added.

Full history: [LOG.md](LOG.md). Data refreshes weekly in season (last: November 17, 2026, through the latest completed week of 2026).

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
