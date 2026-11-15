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
        "kickoff_out_of_bounds", "kickoff_fair_catch", "touchdown", "td_team", "fumble_lost", "kick_distance", "epa", "return_touchdown"]
# yardline_100 of a touchback, by rule year: own 25 through 2023, own 30 in 2024, own 35 in 2025 and 2026.
# Every season must be listed. A season that is missing raises, so a rule change cannot slip through on a default.
TB_SPOT = {2016: 75, 2017: 75, 2018: 75, 2019: 75, 2020: 75, 2021: 75, 2022: 75, 2023: 75, 2024: 70, 2025: 65, 2026: 65}
ERA_START = 2025        # first season of the current rule (touchback to the 35)
MIN_RETURNS, MIN_KICKS = 20, 40


def tb_spot(season: int) -> int:
    if int(season) not in TB_SPOT:
        raise KeyError(f"No touchback spot set for {season}: check the kickoff rule and add it to TB_SPOT")
    return TB_SPOT[int(season)]


def is_onside_or_squib(desc: pd.Series) -> pd.Series:
    return desc.fillna("").str.contains("onside|squib", case=False, regex=True)


def eb_normal(sums: pd.Series, n: pd.Series, sd_play: float):
    """Empirical-Bayes estimate of a per-play mean around zero: shrink each mean by var_true / (var_true + sd^2 / n).
    Returns the shrunk mean, its 90% half-width, and the share of the raw spread that is signal."""
    mean = sums / n
    noise = sd_play ** 2 / n
    var_true = max(float(np.average(mean ** 2 - noise, weights=n)), 0.0)
    w = var_true / (var_true + noise)
    return w * mean, 1.645 * np.sqrt(w * noise), var_true


def split_half(df: pd.DataFrame, pid: str, val: str, min_half: int) -> tuple[float, int]:
    """Odd plays vs even plays for each player (in game order)."""
    d = df.sort_values(["game_id", "play_id"]).copy()
    d["h"] = d.groupby(pid).cumcount() % 2
    t = d.groupby([pid, "h"])[val].agg(["mean", "size"]).unstack("h")
    t = t[(t[("size", 0)] >= min_half) & (t[("size", 1)] >= min_half)]
    return float(t[("mean", 0)].corr(t[("mean", 1)])), int(len(t))


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

    # ---- kickers and returners under the current rule ----
    # Every kickoff from the 35 that was not an onside kick or a squib, INCLUDING return touchdowns and fumbles.
    # Value is nflfastR EPA on the kickoff, from the receiving team's side.
    era = pbp[(pbp.season >= ERA_START) & (pbp.kickoff_attempt == 1) & (pbp.play_type == "kickoff") & (pbp.yardline_100 == 35)
              & pbp.epa.notna() & pbp.kick_distance.notna()].copy()
    drop = is_onside_or_squib(era.desc) | (era.own_kickoff_recovery == 1)
    find["era"] = f"{ERA_START}-{LAST}"; find["era_kickoffs"] = int(len(era)); find["onside_squib_dropped"] = int(drop.sum())
    era = era[~drop]
    era["land"] = 65 - era.kick_distance              # receiving team's yard line where the ball came down (0 or less = end zone)
    era["returned"] = (era.touchback != 1) & (era.kickoff_fair_catch != 1) & era.kickoff_returner_player_id.notna()
    rt = era[era.returned].copy()
    # what a typical return is worth from each landing spot
    from sklearn.ensemble import HistGradientBoostingRegressor
    exp = HistGradientBoostingRegressor(max_iter=80, min_samples_leaf=150, max_depth=3, random_state=7).fit(rt[["land"]], rt.epa)
    rt["epa_exp"] = exp.predict(rt[["land"]]); rt["epa_oe"] = rt.epa - rt.epa_exp
    find["returns"] = int(len(rt)); find["return_tds_kept"] = int((rt.return_touchdown == 1).sum()); find["return_fumbles_lost_kept"] = int((rt.fumble_lost == 1).sum())
    by_land = rt.assign(spot=pd.cut(rt.land, [-10, 0, 5, 10, 15, 20, 40], labels=["end zone", "1-5", "6-10", "11-15", "16-20", "21+"])).groupby("spot", observed=True).agg(
        returns=("epa", "size"), epa=("epa", "mean"), start_own=("return_yards", lambda x: 0)).drop(columns="start_own")
    by_land.round(3).to_csv(OUT / "return_value_by_landing_spot.csv")
    find["return_epa_by_landing_spot"] = by_land.epa.round(2).to_dict()
    tb = era[era.touchback == 1]
    find["touchback_epa"] = round(float(tb.epa.mean()), 2); find["returned_epa"] = round(float(rt.epa.mean()), 2)
    find["returned_vs_tb_league"] = round(float(m[(m.season >= ERA_START) & m.returned].yards_vs_tb.mean()), 2)

    sd_r = float(rt.epa_oe.std())
    g = rt.groupby("kickoff_returner_player_id")
    ret = g.agg(name=("kickoff_returner_player_name", "last"), team=("posteam", "last"), returns=("epa", "size"),
                epa_oe_sum=("epa_oe", "sum"), tds=("return_touchdown", "sum"), fumbles_lost=("fumble_lost", "sum"))
    ret["epa_oe_per_return"] = ret.epa_oe_sum / ret.returns
    ret["shrunk"], ret["half_width_90"], vt = eb_normal(ret.epa_oe_sum, ret.returns, sd_r)
    ret["raw_half_width_90"] = 1.645 * sd_r / np.sqrt(ret.returns)
    ret = ret[ret.returns >= MIN_RETURNS].sort_values("epa_oe_per_return", ascending=False)
    ret["raw_interval_excludes_zero"] = (ret.epa_oe_per_return.abs() > ret.raw_half_width_90)
    ret.round(3).to_csv(OUT / "returners_2025_on.csv")
    r_ret, n_ret = split_half(rt, "kickoff_returner_player_id", "epa_oe", MIN_RETURNS // 2)
    find["returner_split_half_r"] = round(r_ret, 2); find["returner_split_half_n"] = n_ret
    find["returners_rated"] = int(len(ret)); find["returners_clear"] = int(ret.raw_interval_excludes_zero.sum())
    find["returners_clear_expected_by_chance"] = round(0.10 * len(ret), 1)
    find["returner_signal_sd"] = round(float(np.sqrt(vt)), 3)
    find["best_returners"] = ret.head(3)[["name", "team", "returns", "epa_oe_per_return", "raw_half_width_90"]].round(2).values.tolist()

    # kickers: EPA allowed per kickoff (all outcomes: touchbacks, returns, out of bounds), lower is better
    era["epa_vs_avg"] = era.epa - era.epa.mean()
    sd_k = float(era.epa_vs_avg.std())
    kg = era.groupby("kicker_player_id")
    kick = kg.agg(name=("kicker_player_name", "last"), team=("defteam", "last"), kicks=("epa", "size"), tb_rate=("touchback", "mean"),
                  avg_land=("land", "mean"), epa_sum=("epa_vs_avg", "sum"))
    kick["epa_allowed_vs_avg"] = kick.epa_sum / kick.kicks
    kick["shrunk"], kick["half_width_90"], vk = eb_normal(kick.epa_sum, kick.kicks, sd_k)
    kick["raw_half_width_90"] = 1.645 * sd_k / np.sqrt(kick.kicks)
    kick = kick[kick.kicks >= MIN_KICKS].sort_values("shrunk")
    kick["shrunk_interval_excludes_zero"] = kick.shrunk.abs() > kick.half_width_90
    kick.round(3).to_csv(OUT / "kickers_2025_on.csv")
    r_k, n_k = split_half(era, "kicker_player_id", "epa_vs_avg", MIN_KICKS // 2)
    find["kicker_split_half_r"] = round(r_k, 2); find["kicker_split_half_n"] = n_k
    find["kickers_rated"] = int(len(kick)); find["kickers_clear"] = int(kick.shrunk_interval_excludes_zero.sum())
    find["kicker_signal_sd"] = round(float(np.sqrt(vk)), 3)
    find["best_kickers"] = kick.head(3)[["name", "kicks", "shrunk", "half_width_90"]].round(3).values.tolist()
    find["worst_kickers"] = kick.tail(3)[["name", "kicks", "shrunk", "half_width_90"]].round(3).values.tolist()

    top = pd.concat([ret.head(8), ret.tail(7)]).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 6.5))
    ax.barh(top.name + " (" + top.team + ")", top.epa_oe_per_return, color=[plot.ACCENT if v >= 0 else plot.ACCENT2 for v in top.epa_oe_per_return])
    ax.errorbar(top.epa_oe_per_return, top.name + " (" + top.team + ")", xerr=top.raw_half_width_90, fmt="none", ecolor=plot.INK, lw=1)
    ax.axvline(0, color=plot.MUTED); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Expected points per return above a typical return from the same landing spot (90% interval)")
    plot.finish(fig, ax, "Returners against the right baseline: the data cannot yet tell them apart",
                f"Returned kickoffs {ERA_START}-{LAST}, {MIN_RETURNS}+ returns, touchdowns and fumbles included. Top 8 and bottom 7. Split-half r = {find['returner_split_half_r']:.2f}", OUT / "returners.png")

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k_, v in find.items():
        print(k_, v)


if __name__ == "__main__":
    main()
