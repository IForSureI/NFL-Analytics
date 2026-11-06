"""06 Pass vs Run: passing is better, so why run?

Inspired by Michael MacKelvie, "Passing is better...so, why run?" and Brett Kollmann,
"Does 'establishing the run' even work?". In neutral early-down situations we compare
expected points per dropback and per designed run every season since 2006, then look at
whether teams that pass more than expected (nflfastR's xpass model) score more efficiently.
Run: python -m projects.pass_run
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from nflan import data, plot

OUT = Path("reports/06-pass-run")
LAST = data.latest_season_available()
COLS = ["game_id", "season", "season_type", "posteam", "down", "ydstogo", "qtr", "wp", "half_seconds_remaining",
        "play_type", "qb_dropback", "epa", "success", "pass_oe", "xpass", "qb_kneel", "qb_spike", "two_point_attempt"]


def neutral(pbp: pd.DataFrame) -> pd.DataFrame:
    m = (pbp.down.isin([1, 2]) & pbp.wp.between(0.2, 0.8) & (pbp.half_seconds_remaining > 120) & (pbp.qtr <= 4)
         & pbp.play_type.isin(["run", "pass"]) & pbp.epa.notna() & (pbp.qb_kneel != 1) & (pbp.qb_spike != 1) & (pbp.two_point_attempt != 1))
    return pbp.loc[m]


def main():
    plot.style(); OUT.mkdir(parents=True, exist_ok=True)
    pbp = data.load_pbp(range(2006, LAST + 1), columns=COLS)
    pbp = pbp[pbp.season_type == "REG"]
    n = neutral(pbp).copy()
    n["kind"] = np.where(n.qb_dropback == 1, "dropback", "designed run")
    find = {}
    s = n.groupby(["season", "kind"]).agg(plays=("epa", "size"), epa=("epa", "mean"), success=("success", "mean")).unstack("kind")
    s.columns = [f"{a}_{b.replace(' ', '_')}" for a, b in s.columns]
    s["pass_rate"] = s.plays_dropback / (s.plays_dropback + s.plays_designed_run)
    s["epa_gap"] = s.epa_dropback - s.epa_designed_run
    s.round(4).to_csv(OUT / "neutral_early_downs_by_season.csv")
    find["epa_gap_by_season"] = s.epa_gap.round(3).to_dict()
    find["pass_rate_by_season"] = s.pass_rate.round(3).to_dict()
    find["seasons_pass_better"] = int((s.epa_gap > 0).sum()); find["seasons_total"] = len(s)
    find["corr_pass_rate_vs_gap"] = round(float(s.pass_rate.corr(s.epa_gap)), 3)
    find["success_rate_gap_by_season"] = (s.success_dropback - s.success_designed_run).round(3).to_dict()

    fig, ax = plt.subplots()
    ax.plot(s.index, s.epa_dropback, marker="o", color=plot.ACCENT, lw=2.4, label="Dropbacks")
    ax.plot(s.index, s.epa_designed_run, marker="o", color=plot.ACCENT2, lw=2.4, label="Designed runs")
    ax.axhline(0, color=plot.MUTED, lw=.8); ax.legend(loc="upper left"); ax.set_ylabel("Expected points added per play")
    ax.set_xticks(list(s.index)[::2])
    plot.finish(fig, ax, f"Passing has beaten running on early downs in {find['seasons_pass_better']} of {find['seasons_total']} seasons",
                "Neutral early downs: 1st and 2nd down, win probability 20-80%, outside the last 2 minutes of each half", OUT / "epa_pass_vs_run.png")

    # Team level: pass rate over expected vs offensive EPA/play, last full season and current
    rows = []
    for season in [LAST - 1, LAST]:
        t = n[n.season == season].groupby("posteam").agg(proe=("pass_oe", "mean"), epa=("epa", "mean"), plays=("epa", "size"))
        t["season"] = season
        rows.append(t.reset_index())
    t = pd.concat(rows)
    t.round(4).to_csv(OUT / "team_proe_vs_epa.csv", index=False)
    lf = t[t.season == LAST - 1]
    find["team_corr_proe_epa_last_full"] = round(float(lf.proe.corr(lf.epa)), 3)
    fig, ax = plt.subplots(figsize=(8, 6.5))
    ax.scatter(lf.proe, lf.epa, color=plot.ACCENT, s=36)
    for r in lf.itertuples():
        ax.annotate(r.posteam, (r.proe, r.epa), textcoords="offset points", xytext=(4, 3), fontsize=8.5)
    ax.axhline(lf.epa.mean(), color=plot.MUTED, lw=.8); ax.axvline(0, color=plot.MUTED, lw=.8)
    ax.set_xlabel("Pass rate over expected (percentage points, nflfastR xpass)"); ax.set_ylabel("EPA per play")
    plot.finish(fig, ax, f"{LAST - 1}: passing more than expected barely predicts efficiency (r = {find['team_corr_proe_epa_last_full']:.2f})",
                "Neutral early downs, regular season. The league edge is real; the team-level link is weak, so who passes matters as much as how often.", OUT / "proe_vs_epa.png")

    pd.Series(find, dtype=object).to_json(OUT / "findings.json", indent=2, default_handler=str)
    for k, v in find.items():
        print(k, v)


if __name__ == "__main__":
    main()
