# NFL Analytics

A portfolio I am building to show proficiency in NFL statistics and sabermetrics-style analysis, aimed at a job in an NFL club front office. By **Dylan Fanelli** (M.S. Sport Management candidate, UMass Amherst McCormack). Studies on public NFL data, each one starting from a question a coach, scout or fan argues about, then testing it with data. Python, SQL-ready parquet, tested code, and charts a coach can read.

Built on [nflverse](https://github.com/nflverse) data. Inspired by two of the best football explainers working: **Michael MacKelvie** (data storytelling) and **Brett Kollmann** (film plus numbers). Each report links the video that started it. See [`docs/inspiration.md`](docs/inspiration.md).

**Last refreshed:** November 06, 2026 (through the latest completed week of the 2026 season).

## The studies

| # | Study | The question | Headline |
|---|---|---|---|
| 01 | [Flag Audit](reports/01-flag-audit/) | Do flags even out? | Road teams' extra judgment-call flags (0.27 a game in 2016-22) are gone since 2023; Mahomes ranks #22 of 41 QBs in roughing flags drawn |
| 02 | [Fourth-Down Bot](reports/02-fourth-down-bot/) | Who leaves wins on the table? | Own WP model (Brier 0.1495 vs nflfastR 0.1488); coaches go in 53% of clear go spots, up from 33% in 2018 |
| 03 | [Sack Leverage](reports/03-sack-leverage/) | Are all sacks equal? | An average 2nd-down sack (1.7 EPA) is worth more than a 3rd-and-11+ sack (1.53); 82% of them leave 3rd-and-11+ |
| 04 | [Luck Index](reports/04-luck-index/) | How much is luck? | Fumble, kick and close-game luck repeat at r < 0.1; teams 2+ wins over their points drop 2.9 wins the next year |
| 05 | [Kickoff Value](reports/05-kickoff-value/) | What did the new kickoff do? | Returns went from 21% (2023) to 75% (2025); the average return still lands 5.6 yards behind a touchback |
| 06 | [Pass vs Run](reports/06-pass-run/) | Passing is better, so why run? | Passing won on neutral early downs in 21 of 21 seasons, but team pass rate over expected tracks efficiency only at r = 0.20 |
| 07 | [The Box-Score Tax](reports/07-box-score-tax/) | Where is value hiding? | Teams pay about $0.62M a year per "lucky" sack (sacks beyond what pressures predict) though sack luck repeats at r = 0.10; pressures repeat at r = 0.71 vs sacks 0.46. Includes a 2027 free-agent target list |
| 08 | [The YAC Tax](reports/08-yac-tax/) | Do teams pay receivers for lucky YAC? | No clear tax: YAC above expected is noisy per catch (r = 0.36) but a season of it predicts next year like air yards do (0.66 vs 0.55 yards per yard), and the market prices it about right. Includes the 2027 free-agent receivers |

## What is in here
```
nflan/          small tested library: data loading, win-probability model, 4th-down bot, penalty and stats helpers
projects/       one script per study (python -m projects.<name>)
reports/        each study's write-up, charts, CSV outputs and findings.json
sql/            DuckDB queries that answer the same questions straight from the parquet files
scripts/        update.py (refresh the season in progress and rebuild everything), build_readmes.py
tests/          unit tests and sanity checks on every published number
docs/           inspiration notes from the MacKelvie and Kollmann videos
```

## Run it
```bash
pip install -r requirements.txt
python scripts/update.py          # downloads nflverse data (about 400 MB), runs every study, tests, READMEs
pytest -q
```
Each study also runs alone, for example `python -m projects.fourth_down_bot`.

## Data and credit
- Play-by-play and officials data: [nflverse](https://github.com/nflverse/nflverse-data) (CC-BY 4.0), with nflfastR's EPA and win-probability models.
- Fourth-down method: the public idea behind [nfl4th](https://github.com/nflverse/nfl4th) by Ben Baldwin, rebuilt from scratch.
- Ideas: Michael MacKelvie and Brett Kollmann (YouTube). Contracts: Over The Cap via nflverse; advanced defense: Pro Football Reference via nflverse. All analysis and any mistakes are mine.

## License
© 2026 Dylan Fanelli. All rights reserved. The code, reports and figures may be viewed here; they may not be copied, modified or used without written permission. See [LICENSE](LICENSE). To cite this work, use the **Cite this repository** button (from [CITATION.cff](CITATION.cff)).

## About
Dylan Fanelli, M.S. Sport Management candidate at UMass Amherst (Mark H. McCormack Department). I am building this portfolio to show proficiency in NFL statistics and sabermetrics-style analysis, with the goal of a job in an NFL club front office. New studies are added through November 2026 and the data refreshes weekly in season. [LinkedIn](https://www.linkedin.com/in/dylanfanelli/)
