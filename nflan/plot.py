"""One house style for every chart: plain, readable, labeled, sourced."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK = "#1d2433"
MUTED = "#6b7280"
ACCENT = "#0b6e4f"   # green
ACCENT2 = "#c2410c"  # orange
GRID = "#e5e7eb"


def style():
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 150, "figure.figsize": (9, 5.2),
        "font.size": 10.5, "axes.titlesize": 14, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.labelcolor": INK, "axes.edgecolor": MUTED,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "xtick.color": INK, "ytick.color": INK, "text.color": INK,
        "legend.frameon": False,
    })


def finish(fig, ax, title: str, subtitle: str, path, source: str = "Data: nflverse play-by-play. Chart: Dylan Fanelli"):
    ax.set_title(title, pad=26)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=MUTED, fontsize=10, va="bottom")
    fig.text(0.01, 0.005, source, color=MUTED, fontsize=8, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
