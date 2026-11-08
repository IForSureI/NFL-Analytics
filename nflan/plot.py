"""One house style for every chart: plain, readable, labeled, sourced.

The look matches the interactive snippets page: a plate on carbon-copy paper, the title set left in Unbounded,
text in Literata (both in assets/fonts, OFL), violet and red as the two series colours (checked for colour-blind
separation and contrast), words in ink, the study number printed in the plate's corner.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
for _f in ("Unbounded-Medium", "Unbounded-Bold", "Literata-Regular", "Literata-SemiBold", "Literata-Italic"):
    font_manager.fontManager.addfont(str(FONTS / f"{_f}.ttf"))
DISPLAY, TEXT = "Unbounded", "Literata"

PAPER = "#f2f0f5"
PLATE = "#fbfaff"
INK = "#221532"
MUTED = "#5f5672"
SOFT = "#8a829a"
ACCENT = "#6a3ac8"   # violet: the first series (validated with ACCENT2: CVD and normal-vision separation, contrast)
ACCENT2 = "#b8202c"  # red: the second series, and reference lines
GRID = "#e4dfeb"


def style():
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 150, "figure.figsize": (9, 5.2),
        "figure.facecolor": PAPER, "savefig.facecolor": PAPER, "axes.facecolor": PLATE,
        "font.family": TEXT, "font.size": 10.5,
        "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelcolor": INK, "axes.labelweight": "semibold", "axes.edgecolor": SOFT,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
        "legend.frameon": False,
    })


def finish(fig, ax, title: str, subtitle: str, path, source: str = "Data: nflverse play-by-play. Chart: Dylan Fanelli"):
    """Title in the display face, subtitle in italic, the study number on the plate, a plain source line."""
    ax.set_title(title, pad=26, fontfamily=DISPLAY, fontweight="bold", fontsize=12, color=INK)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=MUTED, fontsize=10, va="bottom", style="italic")
    fig.text(0.01, 0.005, source, color=MUTED, fontsize=8, ha="left", va="bottom")
    study = Path(path).parent.name.split("-")[0]
    if study.isdigit():  # the study number sits on the plate's bottom corner, clear of any title length
        fig.text(0.99, 0.005, study, color=ACCENT, fontsize=13, ha="right", va="bottom", fontfamily=DISPLAY, fontweight="bold")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
