"""Portfolio-level figures: the README banner and the at-a-glance results panel.

Every number is read from reports/<slug>/findings.json or the study CSVs, so a weekly refresh
(scripts/update.py) redraws them with the new data.

    python scripts/build_figures.py
"""
from __future__ import annotations

import json
import textwrap
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflan import plot  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

R = ROOT / "reports"
A = ROOT / "assets"
PAPER = plot.PAPER
FIELD = plot.ACCENT  # violet: the main series
ORANGE = plot.ACCENT2  # red: the highlighted series
DISPLAY, TEXT = plot.DISPLAY, plot.TEXT
INK = plot.INK
MUTED = plot.MUTED


def F(slug):
    return json.loads((R / slug / "findings.json").read_text())


def banner():
    """A catalogue title page: the title set left and the go-rate trend as the one figure."""
    f = F("02-fourth-down-bot")
    g = {int(k): v for k, v in f["go_rate_clear_spots"].items()}
    ys = sorted(g)
    full = [y for y in ys if y < max(ys)] or ys
    fig = plt.figure(figsize=(16, 4.2), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100); ax.set_ylim(0, 42); ax.axis("off")
    # crop marks in the corners and a rule under the title block
    for x, y, dx, dy in ((1.2, 40.8, 1, -1), (98.8, 40.8, -1, -1), (1.2, 1.2, 1, 1), (98.8, 1.2, -1, 1)):
        ax.plot([x, x + dx * 1.6], [y, y], color=plot.SOFT, lw=0.9); ax.plot([x, x], [y, y + dy * 3.0], color=plot.SOFT, lw=0.9)
    ax.plot([3.2, 50], [11.2, 11.2], color=INK, lw=1.4)
    # title block
    ax.text(3, 31, "NFL Analytics", fontsize=46, fontweight="bold", color=INK, fontfamily=DISPLAY, va="center")
    ax.text(3.2, 22.0, "Decision models, market inefficiencies and the stats that repeat.", fontsize=17, color=INK, fontfamily=TEXT, style="italic", va="center")
    ax.text(3.2, 7.0, "Dylan Fanelli. Python, SQL, nflverse %d-%d" % (min(ys) if min(ys) < 2010 else 2006, max(ys)), fontsize=13, color=MUTED, fontfamily=TEXT, va="center")
    # the go-rate trend, with ruler ticks for the seasons
    x0, x1 = 62, 96
    span = max(full) - min(full) or 1
    xs = [x0 + (y - min(full)) / span * (x1 - x0) for y in full]
    lo, hi = 0.25, 0.6
    yv = [9 + (g[y] - lo) / (hi - lo) * 24 for y in full]
    ax.plot([x0, x1], [5.2, 5.2], color=plot.SOFT, lw=0.9)
    for x, y in zip(xs, full):
        ax.plot([x, x], [5.2, 6.4 if y % 5 else 7.2], color=plot.SOFT, lw=0.9)
        if y % 5 == 0:
            ax.text(x, 3.2, str(y), ha="center", va="center", fontsize=10, color=MUTED, fontfamily=TEXT)
    ax.plot(xs, yv, color=FIELD, lw=3.0, solid_capstyle="round", zorder=3)
    ax.scatter(xs, yv, s=22, color=FIELD, zorder=4)
    ax.scatter([xs[-1]], [yv[-1]], s=120, facecolor=PAPER, edgecolor=FIELD, lw=2.6, zorder=5)
    ax.text(xs[0] - 0.6, yv[0] - 3.2, f"{g[full[0]]:.0%} in {full[0]}", ha="left", va="top", fontsize=11.5, color=INK, fontfamily=TEXT, fontweight="semibold")
    ax.text(xs[-1] - 1.2, yv[-1] + 3.0, f"{g[full[-1]]:.0%} in {full[-1]}", ha="right", va="bottom", fontsize=11.5, color=INK, fontfamily=TEXT, fontweight="semibold")
    ax.text(x0, 38.4, "How often coaches go for it when the math says go", fontsize=11, color=MUTED, fontfamily=TEXT, style="italic", va="center")
    A.mkdir(exist_ok=True)
    fig.savefig(A / "banner.png", facecolor=PAPER)
    plt.close(fig)


def _card(ax, num, name, big, label):
    ax.set_facecolor(plot.PLATE)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(False)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    ax.text(0.0, 1.42, num, transform=ax.transAxes, fontsize=11, color=FIELD, fontweight="bold", fontfamily=DISPLAY)
    ax.text(0.16, 1.42, name, transform=ax.transAxes, fontsize=10.5, color=MUTED, fontfamily=TEXT, style="italic")
    ax.text(0.0, 1.13, big, transform=ax.transAxes, fontsize=22, color=INK, fontweight="bold", fontfamily=DISPLAY, va="center")
    ax.text(0.0, -0.08, textwrap.fill(label, 46), transform=ax.transAxes, fontsize=9.6, color=INK, va="top", fontfamily=TEXT, linespacing=1.35)


def at_a_glance():
    plot.style()
    fig, axes = plt.subplots(2, 4, figsize=(16, 9.0), dpi=150)
    fig.patch.set_facecolor(PAPER)
    plt.subplots_adjust(left=0.03, right=0.98, top=0.74, bottom=0.13, wspace=0.22, hspace=1.15)
    axs = axes.ravel()

    # 01 flags: road team's extra subjective flags per game by season
    he = pd.read_csv(R / "01-flag-audit/home_edge_by_season.csv")
    s = he[he.flag_kind == "subjective"].sort_values("season")
    ax = axs[0]
    ax.bar(s.season, s.away_minus_home_per_game, color=[ORANGE if y < 2023 else FIELD for y in s.season], width=0.75)
    ax.axhline(0, color=MUTED, lw=0.8)
    f1 = F("01-flag-audit")
    era = {k.strip("()").replace("'", "").replace(" ", ""): v for k, v in f1["home_edge_by_era"].items()}
    new = sorted({k.split(",")[0] for k in era})[-1]
    old = sorted({k.split(",")[0] for k in era})[0]
    _card(ax, "01", "Flag Audit", f"{era[old + ',subjective']:.2f} to {abs(era[new + ',subjective']):.2f}", f"Road teams' extra judgment-call flags per game, {old} (red) vs since 2023 (violet)")

    # 02 go rate
    f2 = F("02-fourth-down-bot")
    g = {int(k): v for k, v in f2["go_rate_clear_spots"].items()}
    ys = sorted(g)
    ax = axs[1]
    ax.plot(ys, [g[y] for y in ys], color=ORANGE, lw=2.4, marker="o", ms=3.5)
    ax.set_ylim(0.2, 0.65)
    last_full = ys[-2]
    _card(ax, "02", "Fourth-Down Bot", f"{g[last_full]:.0%}", f"Go rate in clear go spots, {last_full} (up from {g[ys[0]]:.0%} in {ys[0]}). WP model Brier {f2['brier_ours']:.4f}")

    # 03 sacks: EPA per sack by situation
    f3 = F("03-sack-leverage")
    e = f3["epa_lost_per_sack"]
    keys = [k for k in ["2&1-2", "2&3-6", "2&7-10", "2&11+", "3&1-2", "3&3-6", "3&7-10", "3&11+"] if k in e]
    ax = axs[2]
    ax.bar(range(len(keys)), [e[k] for k in keys], color=[FIELD if k.startswith("2") else MUTED for k in keys], width=0.7)
    ax.bar([keys.index("3&11+")], [e["3&11+"]], color=ORANGE, width=0.7)
    ax.set_ylim(0, max(e[k] for k in keys) * 1.15)
    _card(ax, "03", "Sack Leverage", f"{f3['epa_lost_2nd_down_sack_avg']:.2f} EPA", f"Average 2nd-down sack. Bars: 2nd down (violet), 3rd-and-1 to 10 (grey), 3rd-and-11+ (red, {e['3&11+']:.2f})")

    # 04 luck
    f4 = F("04-luck-index")
    ax = axs[3]
    ax.bar([0, 1], [f4["lucky_change_wins_per17"], f4["unlucky_change_wins_per17"]], color=[ORANGE, FIELD], width=0.55)
    ax.axhline(0, color=MUTED, lw=0.8)
    _card(ax, "04", "Luck Index", f"{f4['lucky_change_wins_per17']:+.1f} wins", "Next-year change for teams 2+ wins over their points (red) vs 2+ under (violet)")

    # 05 kickoffs
    k = pd.read_csv(R / "05-kickoff-value/kickoffs_by_season.csv").sort_values("season")
    ax = axs[4]
    ax.plot(k.season, k.return_rate, color=FIELD, lw=2.4, marker="o", ms=3.5)
    ax.set_ylim(0, 1)
    f5 = F("05-kickoff-value")
    _card(ax, "05", "Kickoff Value", f"{f5['by_season']['2025']['return_rate']:.0%}", f"Kickoffs returned in 2025, from {f5['by_season']['2023']['return_rate']:.0%} in 2023; returns land {abs(f5['returned_vs_tb_league']):.1f} yds behind a touchback")

    # 06 pass vs run
    p = pd.read_csv(R / "06-pass-run/neutral_early_downs_by_season.csv").sort_values("season")
    f6 = F("06-pass-run")
    ax = axs[5]
    ax.bar(p.season, p.epa_gap, color=FIELD, width=0.75)
    ax.axhline(0, color=MUTED, lw=0.8)
    _card(ax, "06", "Pass vs Run", f"{f6['seasons_pass_better']} of {f6['seasons_total']}", "Seasons where passing beat running on neutral early downs (EPA per play gap)")

    # 07 box-score tax
    f7 = F("07-box-score-tax")
    ax = axs[6]
    ax.bar([0, 1], [f7["market_ratio_sack_to_pressure"], f7["predict_count_ratio"]], color=[ORANGE, FIELD], width=0.55)
    ax.set_ylim(0, f7["market_ratio_sack_to_pressure"] * 1.2)
    _card(ax, "07", "Box-Score Tax", f"{f7['market_ratio_sack_to_pressure']:.2f}x vs {f7['predict_count_ratio']:.2f}x", f"A sack is priced like {f7['market_ratio_sack_to_pressure']:.2f} non-sack pressures (red) but predicts like {f7['predict_count_ratio']:.2f} (violet)")

    # 08 YAC tax
    f8 = F("08-yac-tax")
    fut = f8["musd_per_100_future_yards"]
    ax = axs[7]
    ax.bar([0, 1, 2], [fut["air_yds"], fut["xyac_yds"], fut["yacoe_yds"]], color=[FIELD, FIELD, ORANGE], width=0.6)
    ax.set_ylim(0, max(fut.values()) * 1.25)
    _card(ax, "08", "YAC Tax", "No tax", "Price per 100 future yards: air yards, expected YAC, YAC over expected (red) all close")

    fig.text(0.03, 0.955, "Selected studies at a glance", fontsize=20, fontweight="bold", color=INK, fontfamily=DISPLAY)
    fig.text(0.03, 0.915, "Headline number and the evidence behind it. Every figure is rebuilt from the data on each refresh.", fontsize=11, color=MUTED, fontfamily=TEXT, style="italic")
    fig.text(0.03, 0.02, "Data: nflverse (play-by-play, NGS, PFR, Over The Cap). Chart: Dylan Fanelli", fontsize=8.5, color=MUTED)
    A.mkdir(exist_ok=True)
    fig.savefig(A / "at-a-glance.png", facecolor=PAPER)
    plt.close(fig)


def main():
    banner()
    at_a_glance()
    print("assets written")


if __name__ == "__main__":
    main()
