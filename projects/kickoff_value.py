"""05 Kickoff Value: what the new kickoff rules did, and which kickers and returners win the hidden yards.

Inspired by Brett Kollmann, "Kick Returners are in Absolute Hell." and "Kickers are taking over
the NFL." The NFL moved to the dynamic kickoff in 2024 (touchback to the 30) and pushed the
touchback to the 35 in 2025. We measure the receiving team's start, the return rate and the
expected points at the first snap, by season, then grade kickers and returners against the
touchback.
Run: python -m projects.kickoff_value
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot

OUT = Path("reports/05-kickoff-value")
LAST = data.latest_season_available()
COLS = ["game_id", "play_id", "season", "season_type", "posteam", "defteam", "play_type", "kickoff_attempt", "touchback",
        "return_yards", "kicker_player_name", "kicker_player_id", "kickoff_returner_player_name",
        "kickoff_returner_player_id", "own_kickoff_recovery", "penalty", "down", "yardline_100", "ep", "desc",
        "kickoff_out_of_bounds", "kickoff_fair_catch", "touchdown", "td_team", "fumble_lost"]
TB_SPOT = {2016: 75, 2017: 75, 2018: 75, 2019: 75, 2020: 75, 2021: 75, 2022: 75, 2023: 75, 2024: 70}  # yardline_100 of a touchback; 2025+ = 65


def tb_spot(season: int) -> int:
    return TB_SPOT.get(season, 65)


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pbp = data.load_pbp(range(2016, LAST + 1), columns=COLS)
    pbp = pbp[pbp.season_type == "REG"]
    find = {}
    k = pbp[(pbp.kickoff_attempt == 1) & (pbp.play_type == "kickoff") & (pbp.own_kickoff_recovery != 1)][
        ["game_id", "play_id", "season", "posteam", "defteam", "touchback", "return_yards", "kicker_player_name", "kicker_player_id",
         "kickoff_returner_player_name", "kickoff_returner_player_id", "desc", "touchdown", "td_team", "kickoff_fair_catch"]].copy()
    snaps = pbp[pbp.play_type.isin(["run", "pass"]) & pbp.down.eq(1) & pbp.ep.notna()][["game_id", "play_id", "posteam", "yardline_100", "ep"]]
    m = pd.merge_asof(k.sort_values("play_id"), snaps.sort_values("play_id").rename(columns={"posteam": "t2", "yardline_100": "start", "play_id": "pid2"}).assign(play_id=lambda d: d.pid2),
                      on="play_id", by="game_id", direction="forward", allow_exact_matches=False)
    m = m[(m.t2 == m.posteam) & m.start.notna()]  # receiving team's first snap (drops return TDs and turnovers)
    m["tb_spot"] = m.season.map(tb_spot)
    m["yards_vs_tb"] = m.tb_spot - m.start  # + = receiving team started better than a touchback
    m["returned"] = (m.touchback != 1) & (m.kickoff_fair_catch != 1) & m.kickoff_returner_player_id.notna()

    s = m.groupby("season").agg(kickoffs=("start", "size"), touchback_rate=("touchback", "mean"), return_rate=("returned", "mean"),
                                avg_start_own=("start", lambda x: (100 - x).mean()), ep_first_snap=("ep", "mean"))
    s.round(3).to_csv(OUT / "kickoffs_by_season.csv")
    find["by_season"] = s.round(3).to_dict(orient="index")

    fig, ax = plt.subplots()
    ax.bar(s.index, 100 * s.return_rate, color=plot.ACCENT, label="Kickoffs returned (%)")
    ax2 = ax.twinx(); ax2.plot(s.index, s.avg_start_own, color=plot.ACCENT2, marker="o", lw=2.4, label="Average start (own yard line)")
    ax2.set_ylim(15, 40); ax2.spines["right"].set_visible(True); ax2.grid(False)
    ax.set_ylabel("Kickoffs returned (%)"); ax2.set_ylabel("Receiving team's average start (own yard line)", color=plot.ACCENT2)
    ax.set_xticks(s.index); ax.set_ylim(0, 100)
    ax.axvline(2023.5, color=plot.MUTED, ls="--", lw=1); ax.text(2023.6, 92, "dynamic kickoff", color=plot.MUTED, fontsize=9)
    plot.finish(fig, ax, "The new kickoff brought returns back and moved the start line up",
                f"Regular-season kickoffs, 2016-{LAST}. Bars = return rate; line = average drive start. {LAST} is partial.", OUT / "kickoff_era.png")

    # kickers and returners under the current rule (2025+): yards vs a touchback
    era = m[m.season >= 2025]
    kick = era.groupby("kicker_player_id").agg(name=("kicker_player_name", "last"), team=("defteam", "last"), kicks=("start", "size"),
                                               tb_rate=("touchback", "mean"), opp_start_vs_tb=("yards_vs_tb", "mean"),
                                               opp_ep=("ep", "mean")).query("kicks >= 40").sort_values("opp_start_vs_tb")
    kick.round(3).to_csv(OUT / "kickers_2025_on.csv")
    find["best_kickers"] = kick.head(3)[["name", "kicks", "opp_start_vs_tb"]].round(2).values.tolist()
    find["worst_kickers"] = kick.tail(3)[["name", "kicks", "opp_start_vs_tb"]].round(2).values.tolist()
    ret = era[era.returned].groupby("kickoff_returner_player_id").agg(name=("kickoff_returner_player_name", "last"), team=("posteam", "last"),
                                                                      returns=("start", "size"), yards_vs_tb=("yards_vs_tb", "mean"),
                                                                      start_own=("start", lambda x: (100 - x).mean())).query("returns >= 20").sort_values("yards_vs_tb", ascending=False)
    ret.round(2).to_csv(OUT / "returners_2025_on.csv")
    find["best_returners"] = ret.head(3)[["name", "team", "returns", "yards_vs_tb"]].round(2).values.tolist()
    find["returned_vs_tb_league"] = round(float(era[era.returned].yards_vs_tb.mean()), 2)
    top = ret.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 6.5))
    ax.barh(top.name + " (" + top.team + ")", top.yards_vs_tb, color=plot.ACCENT)
    ax.axvline(0, color=plot.MUTED); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Yards vs a touchback at the 35, per return (negative = worse than a touchback)")
    plot.finish(fig, ax, "Kick returners are in hell: even the best start behind the touchback",
                f"Returned kickoffs, 2025-{LAST}, 20+ returns. Top 15 shown. League average: {find['returned_vs_tb_league']:+.1f} yards.", OUT / "returners.png")

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k_, v in find.items():
        print(k_, v)


if __name__ == "__main__":
    main()
