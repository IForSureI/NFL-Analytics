"""01 Flag Audit: do NFL flags really 'even out'?

Inspired by Michael MacKelvie, "We looked at 92,255 flags - NFL refs are biased" (2026).
Questions:
  1. Is there a home-field edge in flags, and is it in judgment calls or rule-book calls?
  2. Do referee crews differ, and is that difference stable year to year (a real tendency)?
  3. Is a team's flag luck stable (a skill) or noise (luck) within a season?
  4. Which QBs draw roughing-the-passer flags most often per dropback?
  5. How much win probability do 'big calls' move, and do they predict anything?
Run: python -m projects.flag_audit
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot
from nflan.penalties import accepted_flags
from nflan.stats import wilson, split_half_r, shrink_rate

OUT = Path("reports/01-flag-audit")
SEASONS = range(2016, data.latest_season_available() + 1)
COLS = ["game_id", "old_game_id", "season", "season_type", "week", "posteam", "defteam", "home_team",
        "away_team", "posteam_type", "play_type", "penalty", "penalty_type", "penalty_team", "desc",
        "epa", "wpa", "qb_dropback", "passer_player_id", "passer_player_name", "down", "result", "qtr"]


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pbp = data.load_pbp(SEASONS, columns=COLS)
    flags = accepted_flags(pbp)
    snaps = pbp[pbp["play_type"].isin(["run", "pass", "no_play"]) & pbp["down"].notna()]
    n_games = pbp.game_id.nunique()
    flags["against_home"] = flags["penalty_team"] == flags["home_team"]
    findings = {"games": n_games, "flags": len(flags), "seasons": f"{min(SEASONS)}-{max(SEASONS)}"}

    # 1. Home edge by kind and season
    g = flags.groupby(["season", "flag_kind", "against_home"]).size().unstack("against_home").fillna(0)
    g.columns = ["vs_away", "vs_home"]
    g["away_minus_home_per_game"] = (g.vs_away - g.vs_home) / pbp.groupby("season").game_id.nunique().reindex(g.index.get_level_values(0)).values
    g = g.reset_index()
    g.to_csv(OUT / "home_edge_by_season.csv", index=False)
    tot = flags.groupby(["flag_kind", "against_home"]).size().unstack()
    for k in ["objective", "subjective"]:
        findings[f"away_share_{k}"] = tot.loc[k, False] / tot.loc[k].sum()
    flags["era"] = np.where(flags.season <= 2022, "2016-22", f"2023-{max(SEASONS) % 100:02d}")
    games_era = pbp.assign(era=np.where(pbp.season <= 2022, "2016-22", f"2023-{max(SEASONS) % 100:02d}")).groupby("era").game_id.nunique()
    et = flags.assign(away=~flags.against_home).groupby(["era", "flag_kind"]).away.agg(["mean", "sum", "size"])
    et["extra_on_road_per_game"] = (2 * et["sum"] - et["size"]) / games_era.reindex(et.index.get_level_values(0)).values
    et.to_csv(OUT / "home_edge_by_era.csv")
    findings["home_edge_by_era"] = et["extra_on_road_per_game"].round(3).to_dict()
    ot = flags[flags.flag_kind == "objective"].assign(away=~flags.against_home).groupby("penalty_type").away.agg(["mean", "size"])
    ot["extra_on_road"] = (2 * ot["mean"] - 1) * ot["size"]
    ot = ot[ot["size"] >= 80].sort_values("extra_on_road", ascending=False)
    ot.to_csv(OUT / "objective_road_skew_by_type.csv")
    findings["objective_road_skew_top"] = ot.head(4)["mean"].round(3).to_dict()
    findings["false_start_road_share"] = float(ot.loc["False Start", "mean"])
    fig, ax = plt.subplots()
    for k, c in [("subjective", plot.ACCENT2), ("objective", plot.ACCENT)]:
        s = g[g.flag_kind == k]
        ax.plot(s.season, s.away_minus_home_per_game, marker="o", color=c, lw=2.2, label=f"{k} flags")
    ax.axhline(0, color=plot.MUTED, lw=1)
    ax.set_ylabel("Extra flags on the road team, per game"); ax.legend(loc="upper right")
    ax.set_xticks(list(SEASONS))
    plot.finish(fig, ax, "The road team's extra judgment-call flags have disappeared",
                "Accepted flags on the away team minus the home team, per game. 2020 had few or no fans; 2026 is partial.", OUT / "home_edge.png")

    # 2. Referee crews (referee name = crew), flags per game, year-to-year stability
    off = data.load_officials()
    refs = off[off.position == "Referee"][["game_id", "official_name"]].rename(columns={"game_id": "old_game_id", "official_name": "referee"})
    fpg = flags.groupby("old_game_id").size().rename("n_flags")
    gm = pbp[["old_game_id", "season", "season_type"]].drop_duplicates().merge(fpg, on="old_game_id", how="left").fillna({"n_flags": 0})
    gm = gm.merge(refs, on="old_game_id", how="inner")
    gm = gm[gm.season_type == "REG"]
    crew = gm.groupby(["referee", "season"]).agg(games=("n_flags", "size"), n_flags=("n_flags", "sum")).reset_index()
    crew["fpg"] = crew["n_flags"] / crew["games"]
    lg = gm.groupby("season")["n_flags"].mean().rename("league_fpg")
    crew = crew.merge(lg, on="season")
    crew["vs_league"] = crew.fpg - crew.league_fpg
    crew = crew[crew.games >= 10]
    pairs = crew.merge(crew.assign(season=crew.season - 1), on=["referee", "season"], suffixes=("", "_next"))
    r_crew = pairs[["vs_league", "vs_league_next"]].corr().iloc[0, 1]
    findings["crew_yoy_r"] = r_crew; findings["crew_pairs"] = len(pairs)
    crew.sort_values(["season", "vs_league"]).to_csv(OUT / "crew_flags_per_game.csv", index=False)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(pairs.vs_league, pairs.vs_league_next, s=28, color=plot.ACCENT, alpha=0.75)
    b = np.polyfit(pairs.vs_league, pairs.vs_league_next, 1); xs = np.linspace(pairs.vs_league.min(), pairs.vs_league.max(), 50)
    ax.plot(xs, np.polyval(b, xs), color=plot.ACCENT2, lw=2)
    ax.axhline(0, color=plot.MUTED, lw=.8); ax.axvline(0, color=plot.MUTED, lw=.8)
    ax.set_xlabel("Crew flags per game vs league, season N"); ax.set_ylabel("Same crew, season N+1")
    plot.finish(fig, ax, f"Referee crews have a real style (r = {r_crew:.2f} year to year)",
                f"Each dot is one referee's crew in back-to-back regular seasons ({len(pairs)} pairs, 10+ games each)", OUT / "crew_stability.png")
    latest = crew[crew.season == crew.season.max() - (1 if crew[crew.season == crew.season.max()].games.max() < 10 else 0)]
    findings["crew_latest_season"] = int(latest.season.max())
    findings["crew_spread_latest"] = (latest.fpg.max(), latest.loc[latest.fpg.idxmax(), "referee"], latest.fpg.min(), latest.loc[latest.fpg.idxmin(), "referee"])

    # 3. Team flag 'luck' (subjective flags drawn minus committed) split-half within season
    sub = flags[(flags.flag_kind == "subjective") & (flags.season_type == "REG")]
    sub = sub.assign(beneficiary=np.where(sub.penalty_team == sub.posteam, sub.defteam, sub.posteam))
    gw = pbp[pbp.season_type == "REG"][["game_id", "season", "week", "home_team", "away_team"]].drop_duplicates("game_id")
    tg = pd.concat([gw.rename(columns={"home_team": "team"})[["game_id", "season", "week", "team"]],
                    gw.rename(columns={"away_team": "team"})[["game_id", "season", "week", "team"]]])
    drawn = sub.groupby(["game_id", "beneficiary"]).size().rename("drawn").rename_axis(["game_id", "team"])
    comm = sub.groupby(["game_id", "penalty_team"]).size().rename("committed").rename_axis(["game_id", "team"])
    tg = tg.set_index(["game_id", "team"]).join(drawn).join(comm).fillna(0).reset_index()
    tg["net"] = tg.drawn - tg.committed
    tg["odd"] = tg.week % 2
    r_net = split_half_r(tg, "net"); r_comm = split_half_r(tg, "committed"); r_drawn = split_half_r(tg, "drawn")
    findings.update(split_r_net=r_net, split_r_committed=r_comm, split_r_drawn=r_drawn)

    # 4. Roughing the passer per 100 dropbacks, QBs with 1,500+ dropbacks since 2018
    db = pbp[(pbp.season >= 2018) & (pbp.qb_dropback == 1) & pbp.passer_player_id.notna()]
    rtp = flags[(flags.season >= 2018) & (flags.penalty_type == "Roughing the Passer")]
    qb = db.groupby(["passer_player_id"]).agg(name=("passer_player_name", "last"), dropbacks=("qb_dropback", "size"))
    rq = rtp.groupby("passer_player_id").size().rename("rtp")
    qb = qb.join(rq).fillna({"rtp": 0})
    qb = qb[qb.dropbacks >= 1500].copy()
    lg_rate = qb.rtp.sum() / qb.dropbacks.sum()
    qb["per100"] = 100 * qb.rtp / qb.dropbacks
    qb[["lo", "hi"]] = qb.apply(lambda r: pd.Series(wilson(r.rtp, r.dropbacks)), axis=1) * 100
    qb["shrunk_per100"] = 100 * shrink_rate(qb.rtp, qb.dropbacks)
    qb = qb.sort_values("shrunk_per100", ascending=False)
    qb.to_csv(OUT / "qb_roughing_drawn.csv")
    findings["rtp_league_per100"] = 100 * lg_rate
    findings["rtp_top"] = qb.head(5)[["name", "rtp", "dropbacks", "per100", "lo", "hi"]].round(2).values.tolist()
    findings["rtp_above_league"] = qb[qb.lo > 100 * lg_rate].name.tolist()
    qb["rank"] = range(1, len(qb) + 1)
    mah = qb[qb.name == "P.Mahomes"]
    if len(mah):
        findings["rtp_mahomes"] = [float(mah.per100.iloc[0]), int(mah["rank"].iloc[0]), len(qb)]
    top = pd.concat([qb.head(14), mah]).drop_duplicates().iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 6.4))
    ax.hlines(range(len(top)), top.lo, top.hi, color=plot.GRID, lw=6)
    ax.scatter(top.shrunk_per100, range(len(top)), color=[plot.ACCENT if n == "P.Mahomes" else plot.ACCENT2 for n in top.name], zorder=3, s=40)
    ax.axvline(100 * lg_rate, color=plot.MUTED, ls="--", lw=1)
    ax.set_yticks(range(len(top))); ax.set_yticklabels([f"{n}  (#{r})" for n, r in zip(top.name, top["rank"])]); ax.grid(axis="y", visible=False)
    ax.set_xlabel("Roughing flags drawn per 100 dropbacks (dot = shrunk rate, bar = 95% interval of the raw rate)")
    plot.finish(fig, ax, "Mahomes is not the roughing-flag king",
                f"Roughing flags drawn, QBs with 1,500+ dropbacks, 2018-{max(SEASONS)}. Rank by shrunk rate of {len(qb)}. Dashed = league", OUT / "qb_roughing.png")

    # 5. Big calls: accepted flags that moved win probability by 10+ points
    big = flags[flags.wpa.abs() >= 0.10].copy()
    big["beneficiary"] = np.where(big.wpa > 0, big.posteam, big.defteam)
    big["victim"] = np.where(big.wpa > 0, big.defteam, big.posteam)
    findings["big_calls"] = len(big); findings["big_calls_reg"] = int((big.season_type == "REG").sum())
    full_reg = big[(big.season_type == "REG") & (big.season < max(SEASONS))]
    findings["big_calls_per_full_season_reg"] = len(full_reg) / full_reg.season.nunique()
    findings["big_call_top_types"] = big.penalty_type.value_counts().head(5).to_dict()
    ts = big[big.season_type == "REG"].groupby(["season", "beneficiary"]).size().rename("for")
    ta = big[big.season_type == "REG"].groupby(["season", "victim"]).size().rename("against")
    net = pd.concat([ts.rename_axis(["season", "team"]), ta.rename_axis(["season", "team"])], axis=1).fillna(0)
    net["net"] = net["for"] - net["against"]
    nn = net.reset_index()
    pr = nn.merge(nn.assign(season=nn.season - 1), on=["season", "team"], suffixes=("", "_next"))
    findings["big_call_net_yoy_r"] = pr[["net", "net_next"]].corr().iloc[0, 1]
    net.reset_index().to_csv(OUT / "big_calls_team_season.csv", index=False)

    pd.Series(findings, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k, v in findings.items():
        print(k, v)


if __name__ == "__main__":
    main()
