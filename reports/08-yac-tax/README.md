# 08 The YAC Tax: do teams pay receivers for yards after the catch that won't come back?

**The question:** study 07 found teams pay for sacks beyond what pressures predict. Receivers have the same shape of problem. A receiver's yards split three ways, using NFL Next Gen Stats tracking: air yards on his catches, the yards after the catch a typical receiver would get on those same catches (expected YAC), and **YAC above expected**, where broken tackles, missed angles and luck live. If YAC above expected repeats less than the rest but is paid like the rest, it is a tax.
**Data:** NFL Next Gen Stats receiving (2016-2025, qualified receivers, 1,251 player-seasons) and 397 veteran WR/TE contracts from Over The Cap (216 players, signed 2019-2026), via [nflverse](https://github.com/nflverse/nflverse-data). Dollars in 2026 cap terms ($301.2M).
**Code:** [`projects/yac_tax.py`](../../projects/yac_tax.py)

## What I found
1. **Where the catch happens repeats; what happens after is shakier.** Year to year: depth of target r = 0.77, separation r = 0.59, catch rate r = 0.48, YAC per catch r = 0.47, **YAC above expected per catch r = 0.36** (760 back-to-back receiver seasons).
2. **But the YAC tax mostly isn't there.** Per catch, YAC above expected is noisy. Over a season of catches it adds up to something real: each yard of it predicts 0.66 yards the next season (95% interval 0.35-0.97), about the same as an air yard (0.55). Season-long YAC over expected carries over much more than the per-catch number suggests.
3. **The market prices it about right.** Contracts pay $3.24M a year per 100 yards of YAC above expected, $2.43M per 100 air yards and $1.87M per 100 expected-YAC yards. Per future yard, that works out to $4.89M (YAC above expected), $4.44M (air yards) and $5.62M (expected YAC) per 100. Those are close, and the intervals overlap. Unlike sacks in study 07, I can't find a premium for the lucky part of receiving production. The robustness table (WR only, TE only, multi-year deals, deals over 1% of the cap, 2023-2026 deals) tells the same story.
4. **What that means for a front office.** The data says not to discount a receiver's YAC as luck by default. The most stable traits are target depth and separation, and the market already pays for production built on them. The receiver market looks efficient where the pass-rush market (study 07) does not.
5. **The 2027 free-agent receivers.** Contracts ending after 2026 (Over The Cap, extensions counted), still active: most 2025 yards came from Puka Nacua (WR, 1,715 yds, +170 YAC over expected), George Pickens (WR, 1,429 yds, +200 YAC over expected), Stefon Diggs (WR, 1,013 yds, +46 YAC over expected), Travis Kelce (TE, 851 yds, +33 YAC over expected). Leaned most on YAC above expected (100+ yards): Puka Nacua (WR, 1,715 yds, +170 YAC over expected), George Pickens (WR, 1,429 yds, +200 YAC over expected), Parker Washington (WR, 847 yds, +101 YAC over expected). Given finding 2, that is a reason to look closer, not to pass.

![Stability](receiver_stability.png)
![Price vs prediction](yac_tax.png)

## Method
- **Yards split:** air yards on catches = yards - catches x YAC per catch; expected YAC = catches x NGS expected YAC per catch; YAC above expected = catches x NGS YAC above expectation per catch. The three add up to total receiving yards.
- **Prediction:** next season's yards on this season's three parts plus targets; **price:** APY as % of the cap on the platform season's three parts plus targets. Both cluster standard errors by player. Output in `models.txt`.
- **Contracts:** veteran WR/TE deals (rookie deals and duplicates dropped), at least 0.4% of the cap, platform season = the season before signing.
- **Free agents:** end year from each player's Over The Cap contract history, with extensions added after the deal they extend; first-round rookie deals (fifth-year option) left out; must have played offense this season.

## Limits
- NGS season tables only include qualified receivers, so part-time players and many tight ends are missing.
- Expected YAC is the NFL's model; the split is only as good as it is.
- Contract status can lag a new extension. Puka Nacua and George Pickens (franchise tag) were both in the final year of their deals as of this writing; check before acting.

## Files
`receivers_2025.csv`, `free_agents_2027_receivers.csv`, `robustness_price_per_100_yards.csv`, `models.txt`, `findings.json`
