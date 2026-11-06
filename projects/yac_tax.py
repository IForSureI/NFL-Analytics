"""08 The YAC Tax: do teams pay receivers for yards after the catch that won't come back?

Study 07 found the market pays for sacks beyond what pressures predict. Receivers have the same
shape of problem. A receiver's yards = air yards on his catches + the yards after the catch a typical
receiver would get on those catches (expected YAC, from Next Gen Stats tracking) + YAC above expected.
The first two depend on route, target depth and ball placement. The last one, YAC above expected,
is where broken tackles, blown angles and luck live. If it repeats less but pays the same as other
yards, it is a tax.

Tests:
  1. Stability: separation, depth of target, catch rate, YAC and YAC above expected, year to year.
  2. Prediction: which kind of yard this year predicts yards next year?
  3. Price: in veteran WR/TE contracts (Over The Cap, 2019-2026), what is each kind of yard paid?
  4. Who is mispriced: the 2027 free-agent receivers whose yards leaned on YAC above expected.
Data: NFL Next Gen Stats receiving (via nflverse, 2016+), Over The Cap contracts and snap counts (nflverse).
Run: python -m projects.yac_tax
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot
from projects.box_score_tax import ols, CAP_2026

OUT = Path("reports/08-yac-tax")
SRC = "Data: NFL Next Gen Stats and Over The Cap via nflverse. Chart: Dylan Fanelli"


def seasons() -> tuple[pd.DataFrame, int]:
    n = data.load_ngs_receiving()
    n = n[(n.week == 0) & (n.season_type == "REG")].copy()
    n = n.rename(columns={"player_gsis_id": "gsis_id", "player_display_name": "player", "player_position": "pos", "team_abbr": "tm"})
    n["air_yds"] = n.yards - n.receptions * n.avg_yac          # yards before the catch, on catches
    n["xyac_yds"] = n.receptions * n.avg_expected_yac           # YAC a typical receiver gets on those catches
    n["yacoe_yds"] = n.receptions * n.avg_yac_above_expectation # YAC above expected
    n["ypt"] = n.yards / n.targets
    n["yacoe_share"] = n.yacoe_yds / n.yards
    return n, int(n.season.max())


def nxt(df, cols):
    a = df[["gsis_id", "season"] + cols]
    return a.merge(a.assign(season=a.season - 1), on=["gsis_id", "season"], suffixes=("", "_next"))


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    n, last = seasons()
    full = n[n.season < last]
    find = {"seasons": f"2016-{last - 1}", "player_seasons": len(full)}

    # 1. stability
    stats = {"avg_separation": "Separation at the catch point", "avg_intended_air_yards": "Depth of target",
             "catch_percentage": "Catch rate", "avg_expected_yac": "Expected YAC per catch",
             "avg_yac": "YAC per catch", "avg_yac_above_expectation": "YAC above expected per catch", "ypt": "Yards per target"}
    pairs = nxt(full, list(stats))
    find["pairs"] = len(pairs)
    stab = {k: round(float(pairs[k].corr(pairs[k + "_next"])), 3) for k in stats}
    find["yoy_r"] = stab
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    order = sorted(stab, key=stab.get)
    cols = [plot.ACCENT2 if k == "avg_yac_above_expectation" else plot.ACCENT for k in order]
    ax.barh([stats[k] for k in order], [stab[k] for k in order], color=cols)
    for i, k in enumerate(order):
        ax.text(stab[k] + 0.01, i, f"{stab[k]:.2f}", va="center", fontsize=10)
    ax.set_xlabel("Year-to-year correlation (r)"); ax.grid(axis="y", visible=False); ax.set_xlim(0, 1)
    plot.finish(fig, ax, "Where the catch happens repeats; what happens after is shakier",
                f"Qualified receivers (NGS), back-to-back regular seasons, 2016-{last - 1} ({len(pairs)} pairs)", OUT / "receiver_stability.png", source=SRC)

    # 2. prediction: next-year yards from this year's components (counts), controlling for targets
    comp = ["air_yds", "xyac_yds", "yacoe_yds"]
    p2 = nxt(full, comp + ["targets", "yards"])
    pm = ols(p2.yards_next, p2[comp + ["targets"]], groups=p2.gsis_id)
    find["predict_next_yards_per_yard"] = {c: round(float(pm.params[c]), 3) for c in comp}
    find["predict_ci"] = {c: [round(float(x), 3) for x in pm.conf_int().loc[c]] for c in comp}
    find["yoy_r_yacoe_yards"] = round(float(p2.yacoe_yds.corr(p2.yacoe_yds_next)), 3)

    # 3. price: veteran WR/TE contracts
    c = data.load_contracts()
    c = c[c.position.isin(["WR", "TE"]) & c.gsis_id.notna() & c.apy_cap_pct.notna()]
    rookie = c.draft_year.notna() & (c.year_signed == c.draft_year)
    c = c[~rookie & c.year_signed.between(2019, 2026) & (c.apy_cap_pct >= 0.004)].drop_duplicates(["gsis_id", "year_signed", "apy"])
    plat = n[comp + ["gsis_id", "season", "targets", "yards", "pos"]].rename(columns={"season": "platform"})
    mk = c.merge(plat, on="gsis_id")
    mk = mk[mk.platform == mk.year_signed - 1].copy()
    mk["apy_pct"] = 100 * mk.apy_cap_pct
    mm = ols(mk.apy_pct, mk[comp + ["targets"]], groups=mk.gsis_id)
    find["market_contracts"] = len(mk); find["market_players"] = int(mk.gsis_id.nunique())
    find["musd_per_100_yards"] = {cc: round(float(mm.params[cc]) * 100 / 100 * CAP_2026, 3) for cc in comp}
    find["musd_per_100_yards_ci"] = {cc: [round(float(x) * CAP_2026, 3) for x in mm.conf_int().loc[cc]] for cc in comp}
    # price per FUTURE yard bought through each component
    find["musd_per_100_future_yards"] = {cc: round(find["musd_per_100_yards"][cc] / max(find["predict_next_yards_per_yard"][cc], 1e-6), 2)
                                          for cc in comp}
    rob = []
    for name, d_ in {"all": mk, "WR only": mk[mk.position == "WR"], "TE only": mk[mk.position == "TE"],
                     "deals >= 1% of cap": mk[mk.apy_cap_pct >= 0.01], "multi-year deals": mk[mk.years >= 2],
                     "signed 2023-2026": mk[mk.year_signed >= 2023]}.items():
        if len(d_) < 40:
            continue
        m_ = ols(d_.apy_pct, d_[comp + ["targets"]], groups=d_.gsis_id)
        row = {"sample": name, "contracts": len(d_)}
        for cc in comp:
            row[f"{cc}_musd_per_100"] = round(float(m_.params[cc]) * CAP_2026, 2)
        rob.append(row)
    pd.DataFrame(rob).to_csv(OUT / "robustness_price_per_100_yards.csv", index=False)
    find["robustness"] = rob

    fig, ax = plt.subplots(figsize=(8.5, 5))
    lab = {"air_yds": "Air yards\non catches", "xyac_yds": "Expected YAC", "yacoe_yds": "YAC above\nexpected"}
    x = np.arange(3); w = 0.38
    paid = [find["musd_per_100_yards"][cc] for cc in comp]
    fut = [find["predict_next_yards_per_yard"][cc] for cc in comp]
    ax.bar(x - w / 2, paid, w, color=plot.ACCENT2, label="Paid: $M a year per 100 platform-year yards")
    ax2 = ax.twinx(); ax2.bar(x + w / 2, fut, w, color=plot.ACCENT, label="Predicts: next-year yards per yard")
    ax2.grid(False); ax2.spines["right"].set_visible(True)
    ax.set_xticks(x); ax.set_xticklabels([lab[cc] for cc in comp]); ax.grid(axis="x", visible=False)
    ax.set_ylabel("$M a year per 100 yards (orange)"); ax2.set_ylabel("Next-year yards per yard (green)", color=plot.ACCENT)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", fontsize=8.5)
    ax.set_ylim(0, max(paid) * 1.45); ax2.set_ylim(min(0, min(fut)) * 1.2, max(fut) * 1.45)
    plot.finish(fig, ax, "No YAC tax: what a yard is paid tracks what it predicts",
                f"Veteran WR/TE contracts 2019-2026 ({len(mk)}, {mk.gsis_id.nunique()} players); prediction from 2016-{last - 1}", OUT / "yac_tax.png", source=SRC)

    # 4. boards: last full season, and 2027 free agents
    lf = n[n.season == last - 1].copy()
    lf["yards_wo_yacoe"] = lf.yards - lf.yacoe_yds
    lf[["player", "pos", "tm", "targets", "receptions", "yards", "air_yds", "xyac_yds", "yacoe_yds", "yacoe_share", "avg_separation",
        "avg_intended_air_yards"]].round(2).sort_values("yacoe_yds", ascending=False).to_csv(OUT / f"receivers_{last - 1}.csv", index=False)
    find["most_yacoe_last_full"] = lf.nlargest(5, "yacoe_yds")[["player", "tm", "yards", "yacoe_yds"]].round(0).values.tolist()
    find["least_yacoe_last_full"] = lf.nsmallest(5, "yacoe_yds")[["player", "tm", "yards", "yacoe_yds"]].round(0).values.tolist()

    allc = data.load_contracts()
    allc = allc[allc.position.isin(["WR", "TE"]) & allc.gsis_id.notna()].sort_values("year_signed")
    latest = allc.groupby("gsis_id").tail(1).copy()
    latest["end_year"] = latest.contract_history.map(data.contract_end_year)
    option = (latest.draft_round == 1) & (latest.year_signed == latest.draft_year)
    fa = latest[(latest.end_year == last) & ~option][["gsis_id", "player", "position", "team", "apy"]]
    fa = fa.merge(lf[["gsis_id", "yards", "targets", "air_yds", "xyac_yds", "yacoe_yds", "avg_separation", "avg_intended_air_yards", "ypt"]], on="gsis_id")
    pl = data.load_players()[["pfr_id", "gsis_id"]].dropna().drop_duplicates("gsis_id")
    sc = data.load_snap_counts(last)
    active = set(pl[pl.pfr_id.isin(sc[sc.offense_snaps > 0].pfr_player_id)].gsis_id)
    fa = fa[fa.gsis_id.isin(active)].copy()
    fa["yacoe_share"] = fa.yacoe_yds / fa.yards
    fa["flag"] = np.where(fa.yacoe_yds >= 100, "leaned on YAC above expected (100+ yards)",
                          np.where(fa.yacoe_yds < 0, "YAC below expected", ""))
    fa = fa.sort_values("yards", ascending=False)
    fa.round(2).to_csv(OUT / f"free_agents_{last + 1}_receivers.csv", index=False)
    find["fa_class"] = last + 1; find["fa_n"] = len(fa)
    find["fa_leaned"] = fa[fa.flag.str.startswith("leaned")][["player", "position", "yards", "yacoe_yds"]].round(0).values.tolist()
    find["fa_below"] = fa[fa.flag.str.startswith("YAC below")][["player", "position", "yards", "yacoe_yds", "avg_separation"]].round(1).values.tolist()
    find["fa_top_yards"] = fa.head(8)[["player", "position", "yards", "yacoe_yds"]].round(0).values.tolist()
    find["current_season"] = last

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    with open(OUT / "models.txt", "w") as f:
        f.write(f"=== Next-year yards ~ components (+targets), clustered by player\n{pm.summary()}\n\n=== APY % of cap ~ components (+targets), clustered by player\n{mm.summary()}\n")
    for k, v in find.items():
        print(k, v)


if __name__ == "__main__":
    main()
