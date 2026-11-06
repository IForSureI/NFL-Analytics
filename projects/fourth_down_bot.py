"""02 Fourth-Down Bot: who leaves wins on the table?

Inspired by Brett Kollmann, "Are analytics ruining football?" (decision vs execution), and
Michael MacKelvie, "Passing is better...so, why run?" (coaches lag the math).
Steps:
  1. Train a win-probability model (2006-2023), test it on 2024-2025 against nflfastR's WP.
  2. Fit conversion, field-goal and punt models.
  3. Score every 4th down 2018-present: WP if you go vs the best kick.
  4. Track how often coaches go when the math says go, and grade each team's 4th-down calls.
Run: python -m projects.fourth_down_bot
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot
from nflan.wp import WPModel, training_frame, add_features, brier, calibration_table, PBP_COLUMNS, FEATURES
from nflan.fourth import FourthDownBot

OUT = Path("reports/02-fourth-down-bot")
LAST = data.latest_season_available()
COLS = sorted(set(PBP_COLUMNS + ["play_id", "week", "yards_gained", "touchdown", "td_team", "field_goal_attempt",
                                 "field_goal_result", "kick_distance", "roof", "punt_attempt", "home_coach", "away_coach",
                                 "desc", "penalty", "qb_kneel", "qb_spike"]))


def kickoff_starts(pbp: pd.DataFrame) -> pd.Series:
    """Average yardline_100 of the receiving team's first snap after a kickoff, by season."""
    k = pbp[pbp["play_type"] == "kickoff"][["game_id", "play_id", "season", "posteam"]]
    s = pbp[pbp["play_type"].isin(["run", "pass"]) & pbp["down"].eq(1)][["game_id", "play_id", "posteam", "yardline_100"]]
    m = pd.merge_asof(k.sort_values("play_id"), s.sort_values("play_id").rename(columns={"posteam": "t2"}),
                      on="play_id", by="game_id", direction="forward", allow_exact_matches=False)
    m = m[m["t2"] == m["posteam"]]
    return m.groupby("season")["yardline_100"].mean()


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pbp = data.load_pbp(range(2006, LAST + 1), columns=COLS)
    find = {}

    # 1. WP model: train 2006-2023, test 2024-2025
    tf = training_frame(pbp)
    train, test = tf[tf.season <= 2023], tf[tf.season.isin([2024, 2025])]
    m = WPModel.fit(train)
    p = m.predict(test)
    find["wp_test_plays"] = len(test)
    find["brier_ours"] = brier(p, test.y)
    ok = test.vegas_wp.notna()
    find["brier_nflfastR_vegas_wp"] = brier(test.vegas_wp[ok], test.y[ok])
    find["brier_ours_same_rows"] = brier(p[ok.values], test.y[ok])
    find["corr_with_nflfastR"] = float(np.corrcoef(p[ok.values], test.vegas_wp[ok])[0, 1])
    cal = calibration_table(p, test.y)
    cal.to_csv(OUT / "wp_calibration_2024_2025.csv", index=False)
    fig, ax = plt.subplots(figsize=(6.4, 6))
    ax.plot([0, 1], [0, 1], color=plot.MUTED, ls="--", lw=1)
    ax.scatter(cal.pred, cal.actual, s=np.sqrt(cal.n) / 2, color=plot.ACCENT)
    ax.set_xlabel("Predicted win probability"); ax.set_ylabel("Share of those teams that won")
    plot.finish(fig, ax, "The win-probability model is honest",
                f"Out of sample: {len(test):,} plays from 2024-25. Brier {find['brier_ours']:.3f} vs nflfastR {find['brier_nflfastR_vegas_wp']:.3f}",
                OUT / "wp_calibration.png")

    # production model on everything through the last full season
    full = WPModel.fit(tf[tf.season <= LAST - 1] if LAST >= 2026 else tf)

    # 2. components (2016+ so rules and kicking are modern)
    modern = pbp[pbp.season >= 2016]
    conv, gain = FourthDownBot.fit_convert(modern)
    fg = FourthDownBot.fit_fg(modern)
    punt = FourthDownBot.fit_punt(modern, pbp[pbp.season >= 2016])
    ko = kickoff_starts(pbp[pbp.season >= 2016])
    ko.to_csv(OUT / "kickoff_start_by_season.csv")
    bot = FourthDownBot(full, conv, fg, punt, gain, float(ko.iloc[-1]))
    with open(OUT / "model_summary.txt", "w") as f:
        f.write(f"Conversion extra-yards table:\n{gain}\n\nKickoff start yardline_100 by season:\n{ko.round(1)}\n")

    # sanity states (also used by tests): 4th-and-1 at midfield, tied, first quarter, even teams
    sanity = pd.DataFrame([dict(score_differential=0, game_seconds_remaining=3000, half_seconds_remaining=1200,
                                yardline_100=50, down=4, ydstogo=1, posteam_timeouts_remaining=3,
                                defteam_timeouts_remaining=3, receive_2h_ko=1, posteam_spread=0, is_second_half=0,
                                roof_indoor=0, season=LAST),
                           dict(score_differential=0, game_seconds_remaining=3000, half_seconds_remaining=1200,
                                yardline_100=80, down=4, ydstogo=10, posteam_timeouts_remaining=3,
                                defteam_timeouts_remaining=3, receive_2h_ko=1, posteam_spread=0, is_second_half=0,
                                roof_indoor=0, season=LAST)])
    sv = bot.evaluate(sanity)
    find["sanity_4th1_midfield_go_boost"] = float(sv.go_boost[0])
    find["sanity_4th10_own20_go_boost"] = float(sv.go_boost[1])

    # 3. every 4th down since 2018
    df = add_features(pbp[(pbp.season >= 2018) & (pbp.down == 4) & (pbp.qtr <= 4)])
    df = df[df.play_type.isin(["run", "pass", "punt", "field_goal"]) & (df.qb_kneel != 1) & (df.qb_spike != 1)]
    df = df.dropna(subset=FEATURES)
    df["roof_indoor"] = df.roof.isin(["dome", "closed"]).astype(int)
    df["choice"] = np.select([df.play_type.isin(["run", "pass"]), df.play_type.eq("field_goal")], ["go", "fg"], "punt")
    parts = []
    for season, g in df.groupby("season"):
        bot.kickoff_start = float(ko.get(season, ko.iloc[-1]))
        bot.wp = full  # in-sample for 2018-2025, out of sample for the season in progress
        parts.append(pd.concat([g.reset_index(drop=True), bot.evaluate(g)], axis=1))
    ev = pd.concat(parts, ignore_index=True)
    ev["coach"] = np.where(ev.posteam == ev.home_team, ev.home_coach, ev.away_coach)
    chosen = np.select([ev.choice.eq("go"), ev.choice.eq("fg")], [ev.wp_go, ev.wp_fg], ev.wp_punt)
    best = ev[["wp_go", "wp_fg", "wp_punt"]].max(axis=1)
    ev["gap"] = 100 * (best - chosen)
    # Count only clear calls: small gaps are inside the model's error, so they are not charged.
    ev["wp_lost"] = np.where(ev["gap"] >= 1.0, ev["gap"], 0.0)
    ev["close"] = ev.score_differential.abs() <= 16
    ev.to_parquet(OUT / "fourth_downs_scored.parquet", index=False)

    # 4a. compliance trend: in clear go spots (go_boost >= 2 WP points), how often did coaches go?
    clear = ev[(ev.go_boost >= 2) & ev.close & (ev.game_seconds_remaining > 300)]
    tr = clear.groupby("season").agg(spots=("choice", "size"), went=("choice", lambda c: (c == "go").mean()))
    tr.to_csv(OUT / "go_rate_when_math_says_go.csv")
    find["go_rate_clear_spots"] = tr.went.round(3).to_dict()
    fig, ax = plt.subplots()
    ax.plot(tr.index, 100 * tr.went, marker="o", lw=2.4, color=plot.ACCENT)
    for x, y, n in zip(tr.index, 100 * tr.went, tr.spots):
        ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
    ax.set_ylim(0, 100); ax.set_ylabel("Went for it (%)"); ax.set_xticks(tr.index)
    plot.finish(fig, ax, "Coaches go for it more, but still not as often as the math says",
                "4th downs where going adds 2+ WP points, score within 16, outside the last 5 minutes. 2026 is partial.",
                OUT / "go_rate_trend.png")

    # 4b. team scorecard, latest two seasons: WP points lost per game on 4th-down calls
    rows = []
    for season in sorted(ev.season.unique())[-2:]:
        e = ev[(ev.season == season) & ev.close & (ev.season_type == "REG")]
        gpt = pbp[(pbp.season == season) & (pbp.season_type == "REG")].groupby("posteam").game_id.nunique()
        t = e.groupby("posteam").agg(fourth_downs=("choice", "size"), wp_lost=("wp_lost", "sum"),
                                     clear_go_spots=("go_boost", lambda b: (b >= 2).sum()),
                                     went_in_clear=("choice", lambda c: 0)).reset_index()
        cg = e[e.go_boost >= 2].groupby("posteam").choice.apply(lambda c: (c == "go").sum())
        t["went_in_clear"] = t.posteam.map(cg).fillna(0).astype(int)
        t["games"] = t.posteam.map(gpt)
        t["wp_lost_per_game"] = t.wp_lost / t.games
        t["season"] = season
        rows.append(t.sort_values("wp_lost_per_game"))
    sc = pd.concat(rows)
    sc.to_csv(OUT / "team_scorecard.csv", index=False)
    cur = sc[sc.season == sc.season.max()].sort_values("wp_lost_per_game", ascending=False)
    find["scorecard_season"] = int(sc.season.max())
    find["most_costly"] = cur.head(3)[["posteam", "wp_lost_per_game"]].round(2).values.tolist()
    find["least_costly"] = cur.tail(3)[["posteam", "wp_lost_per_game"]].round(2).values.tolist()
    fig, ax = plt.subplots(figsize=(8, 8.5))
    c = cur.iloc[::-1]
    ax.barh(c.posteam, c.wp_lost_per_game, color=plot.ACCENT2)
    ax.set_xlabel("Win-probability points lost per game on 4th-down decisions"); ax.grid(axis="y", visible=False)
    plot.finish(fig, ax, f"{int(sc.season.max())} fourth-down report card",
                "WP points lost on calls that missed the best option by 1+ point, games within 16. Lower is better.",
                OUT / "team_scorecard.png")

    # 4c. costliest single decisions this season
    worst = ev[ev.season == ev.season.max()].sort_values("wp_lost", ascending=False).head(10)
    worst[["week", "posteam", "defteam", "qtr", "game_seconds_remaining", "score_differential", "yardline_100",
           "ydstogo", "choice", "rec", "go_boost", "wp_lost", "desc"]].to_csv(OUT / "costliest_calls_current_season.csv", index=False)

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k, v in find.items():
        print(k, v)


if __name__ == "__main__":
    main()
