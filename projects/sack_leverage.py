"""03 Sack Leverage: not all sacks are created equal.

Inspired by Brett Kollmann, "Not all sacks are created equal." (2025).
He argues (with PFF data) that 3rd-down defense is really early-down defense, and that a
2nd-down sack, which usually makes 3rd-and-long, can be worth more than a 3rd-down sack.
We re-test his numbers with public play-by-play and build a pass-rusher board that weighs
each sack by the expected points it took away.
Run: python -m projects.sack_leverage
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot

OUT = Path("reports/03-sack-leverage")
LAST = data.latest_season_available()
COLS = ["game_id", "play_id", "season", "season_type", "week", "posteam", "defteam", "down", "ydstogo", "yardline_100",
        "play_type", "sack", "epa", "wpa", "yards_gained", "first_down", "touchdown", "fixed_drive", "series", "series_success",
        "sack_player_id", "sack_player_name", "half_sack_1_player_id", "half_sack_1_player_name",
        "half_sack_2_player_id", "half_sack_2_player_name", "qb_dropback", "penalty"]
BUCKETS = [0, 2, 6, 10, 99]
LABELS = ["1-2", "3-6", "7-10", "11+"]


def sack_credits(s: pd.DataFrame) -> pd.DataFrame:
    full = s[s.sack_player_id.notna()][["sack_player_id", "sack_player_name", "season", "epa", "wpa", "down", "defteam"]].rename(
        columns={"sack_player_id": "pid", "sack_player_name": "name"}).assign(credit=1.0)
    h1 = s[s.half_sack_1_player_id.notna()][["half_sack_1_player_id", "half_sack_1_player_name", "season", "epa", "wpa", "down", "defteam"]].rename(
        columns={"half_sack_1_player_id": "pid", "half_sack_1_player_name": "name"}).assign(credit=0.5)
    h2 = s[s.half_sack_2_player_id.notna()][["half_sack_2_player_id", "half_sack_2_player_name", "season", "epa", "wpa", "down", "defteam"]].rename(
        columns={"half_sack_2_player_id": "pid", "half_sack_2_player_name": "name"}).assign(credit=0.5)
    c = pd.concat([full, h1, h2], ignore_index=True)
    c["epa_saved"] = -c["epa"] * c["credit"]
    return c


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pbp = data.load_pbp(range(2016, LAST + 1), columns=COLS)
    pbp = pbp[pbp.season_type == "REG"]
    find = {}
    db = pbp[(pbp.qb_dropback == 1) & pbp.down.notna() & pbp.epa.notna()].copy()
    db["bucket"] = pd.cut(db.ydstogo, BUCKETS, labels=LABELS)
    hist = db[db.season <= LAST - 1]

    # 1. Kollmann's 3rd-down table, rebuilt: conversion allowed and sack rate by distance
    third = pbp[(pbp.down == 3) & pbp.play_type.isin(["run", "pass"]) & (pbp.season >= LAST - 4) & (pbp.season <= LAST - 1)].copy()
    third["bucket"] = pd.cut(third.ydstogo, BUCKETS, labels=LABELS)
    t3 = third.groupby("bucket", observed=True).agg(plays=("first_down", "size"),
                                                    conv=("first_down", lambda x: (x == 1).mean()),
                                                    sack_rate=("sack", "mean"))
    t3["conv"] = (t3.conv + 0).round(3)
    t3.to_csv(OUT / "third_down_by_distance.csv")
    find["third_down_conversion_by_distance"] = (100 * third.assign(c=(third.first_down == 1) | (third.touchdown == 1)).groupby("bucket", observed=True).c.mean()).round(1).to_dict()
    find["third_down_sack_rate_by_distance"] = (100 * t3.sack_rate).round(1).to_dict()
    find["third_down_window"] = f"{LAST - 4}-{LAST - 1}"

    # 2. EPA lost per sack, by down and distance
    sk = hist[hist.sack == 1]
    tab = sk.groupby(["down", "bucket"], observed=True).agg(sacks=("epa", "size"), epa_lost=("epa", lambda e: -e.mean())).reset_index()
    tab = tab[(tab.sacks >= 40) & tab.down.isin([1, 2, 3])]
    tab.to_csv(OUT / "epa_lost_per_sack.csv", index=False)
    find["epa_lost_per_sack"] = {f"{int(r.down)}&{r.bucket}": round(r.epa_lost, 2) for r in tab.itertuples()}
    fig, ax = plt.subplots()
    xlab = [f"{['1st', '2nd', '3rd'][int(d) - 1]} & {b}" for d, b in zip(tab.down, tab.bucket)]
    cols = [plot.ACCENT2 if d == 2 else (plot.ACCENT if d == 3 else plot.MUTED) for d in tab.down]
    ax.bar(xlab, tab.epa_lost, color=cols)
    for i, v in enumerate(tab.epa_lost):
        ax.text(i, v + 0.03, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_ylabel("Expected points taken away per sack"); ax.grid(axis="x", visible=False)
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    plot.finish(fig, ax, "3rd-and-short sacks are worth most; a 2nd-down sack beats a 3rd-and-11+ sack",
                f"Mean EPA taken from the offense per sack, regular seasons 2016-{LAST - 1}. Orange = 2nd down, green = 3rd down", OUT / "epa_per_sack.png")

    # 3. What happens after a 2nd-down sack?
    hist2 = pbp[(pbp.season <= LAST - 1)].sort_values(["game_id", "play_id"])
    sc = hist2[hist2.play_type.isin(["run", "pass"]) & hist2.down.notna()].copy()
    sc["next_down"] = sc.groupby(["game_id", "fixed_drive"]).down.shift(-1)
    sc["next_dist"] = sc.groupby(["game_id", "fixed_drive"]).ydstogo.shift(-1)
    second = sc[(sc.down == 2)]
    after_sack = second[(second.sack == 1) & (second.next_down == 3)]
    find["share_2nd_down_sacks_to_3rd_and_11plus"] = round(float((after_sack.next_dist >= 11).mean()), 3)
    find["series_success_after_2nd_down_sack"] = round(float(second[second.sack == 1].series_success.mean()), 3)
    other = second[(second.sack == 0) & (second.qb_dropback == 1) & (second.first_down != 1) & (second.touchdown != 1)]
    find["series_success_after_other_2nd_down_dropbacks_no_conversion"] = round(float(other.series_success.mean()), 3)
    find["epa_lost_2nd_down_sack_avg"] = round(float(-sk[sk.down == 2].epa.mean()), 2)

    # 4. Pass-rusher board: sacks vs expected points taken, latest full season and season to date
    cred = sack_credits(pbp[pbp.sack == 1])
    for season in [LAST - 1, LAST]:
        c = cred[cred.season == season]
        b = c.groupby("pid").agg(name=("name", "last"), team=("defteam", "last"), sacks=("credit", "sum"),
                                  epa_taken=("epa_saved", "sum"), early_down_sacks=("credit", lambda x: x[c.loc[x.index, "down"] <= 2].sum()))
        b = b[b.sacks >= (6 if season < LAST else 3)].copy()
        b["epa_per_sack"] = b.epa_taken / b.sacks
        b["rank_sacks"] = b.sacks.rank(ascending=False, method="min").astype(int)
        b["rank_epa"] = b.epa_taken.rank(ascending=False, method="min").astype(int)
        b = b.sort_values("epa_taken", ascending=False)
        b.to_csv(OUT / f"pass_rusher_board_{season}.csv")
        if season == LAST - 1:
            find["board_season"] = season
            find["board_top5"] = b.head(5)[["name", "team", "sacks", "epa_taken", "rank_sacks"]].round(1).values.tolist()
            mover = b.assign(jump=b.rank_sacks - b.rank_epa).sort_values("jump", ascending=False).head(3)
            find["board_biggest_risers"] = mover[["name", "sacks", "rank_sacks", "rank_epa"]].values.tolist()
            top = b.head(20).iloc[::-1]
            fig, ax = plt.subplots(figsize=(8, 7.5))
            ax.barh(top.name + " (" + top.team + ")", top.epa_taken, color=plot.ACCENT)
            for i, (e, s_) in enumerate(zip(top.epa_taken, top.sacks)):
                ax.text(e + 0.3, i, f"{s_:g} sacks", va="center", fontsize=8.5, color=plot.MUTED)
            ax.set_xlabel("Expected points taken away by his sacks"); ax.grid(axis="y", visible=False)
            plot.finish(fig, ax, f"{season} pass rushers ranked by what their sacks were worth",
                        "Half sacks get half credit. Regular season.", OUT / "pass_rusher_board.png")

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k, v in find.items():
        print(k, v)


if __name__ == "__main__":
    main()
