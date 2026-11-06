# Report standard

Every study in this portfolio is written to the same standard. It borrows its structure from the work NFL analysts publish in the open: Big Data Bowl write-ups, Open Source Football articles, and the model documentation behind nflfastR and nfl4th. The aim is for a club analyst, a coach or a general manager to find the answer in under a minute and the evidence in under five.

## Page structure (in this order)

| Section | What it holds | Rule |
|---|---|---|
| Navigation | Back to the portfolio, previous and next study | Top and bottom of every page |
| Title and subtitle | Study number, name, the question in a few words | |
| Badges | Status, seasons covered, methods | Generated |
| TL;DR | Three sentences, with the number behind each claim | Numbers come from `findings.json` |
| Hero figure | The one chart that carries the result | Captioned |
| Key numbers | Measure and value table | Generated from `findings.json` |
| Why it matters for a club | Who in a building uses this and how | Name the department |
| The question | The question, why it matters, prior work credited | Credit the video or paper that started it |
| Data | Sources, seasons, sample sizes | Every source named |
| Results | One heading per finding, stated as the finding, each followed by its figure | Headings say what was found, not the topic |
| Method | Definitions, filters, models; equations where they help | Enough to reproduce by hand |
| Validation | Out-of-sample tests, calibration, stability, bootstraps, robustness | Weak versions are reported, not hidden |
| Limitations | What the data cannot show | Specific, not generic |
| Next steps | What the next version would add | |
| Reproduce | The command that rebuilds the page | |
| Files | Every output file and what it holds | Generated |

## Analysis rules

1. **State the question before looking at results.** If the hypothesis fails, the title and TL;DR say so (study 08 is the model).
2. **Stability before value.** A stat must repeat year to year (or split-half) before it is called a skill, ranked, or priced.
3. **Intervals, not just point estimates.** Cluster standard errors by player or team when they repeat; bootstrap by player when a ratio is compared.
4. **Out-of-sample whenever a model predicts.** Name the training and test seasons.
5. **Robustness tables** for any dollar figure: at least four alternative samples or controls.
6. **Names are checked.** Any player or team list is checked against current news (extensions, tags, retirements, injuries) before it is published.
7. **No coach names from play-by-play coach fields;** they lag.
8. **Every number on a page comes from `findings.json`,** so a refresh can never leave a stale number in the text.

## How a new study plugs in

1. `projects/<name>.py` writes `reports/NN-slug/` (figures, CSVs, `findings.json`).
2. A README function in `scripts/build_readmes.py` writes the findings with internal headings (`## What I found` as a numbered list with a bold lead sentence, then `## Method`, `## Limits`, `## Files`), and the study is added to `REPORTS`. The presentation layer (`wrap()` in the same file) turns those into the published Results, Method, Limitations and Files sections.
3. An entry in `scripts/report_meta.py` adds the presentation layer: `short`, `tldr`, `question`, `seasons`, `tags`, `hero`, `figs`, `key`, `why`, `method_eq`, `validation`, `next`, `files`.
4. Add the study to `STUDIES` in `scripts/update.py`, add tests, run `python scripts/update.py --no-download`. The portfolio table, gallery and at-a-glance panel update from these entries; `tests/test_readme_standard.py` fails if any section is missing.
