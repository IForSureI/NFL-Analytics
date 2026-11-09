"""2026 In-Season Snippets: twelve quick charts on the season in progress.

Question: what does the 2026 season look like so far, through the lens of a few
numbers a coaching staff or front office would actually look at on a Monday?

Charts (all from nflverse play-by-play, regular season, completed weeks only):
  1. qb_epa_cpoe.png         QB efficiency: EPA per dropback vs completion % over expected
  2. rb_success.png          Running backs: rushing success rate, top 30 (ranked bar)
  3. team_tiers.png          Team tiers: offensive EPA/play vs defensive EPA/play allowed
  4. early_down_proe.png     Who throws on early downs: neutral-situation pass rate over expected
  5. receiver_share.png      Receiver roles: target share vs air-yards share (WOPR)
  6. defense_pressure.png    Pass defense: pressure-proxy rate vs EPA per dropback allowed
  7. qb_adot_yac.png         How QBs get their yards: depth of target vs share of yards after the catch
  8. receiver_epa_adot.png   Receivers: role (depth of target) vs value (EPA per target)
  9. yac_over_expected.png   Yards after the catch over expected per reception, top 30 (ranked bar)
 10. defense_run_pass.png    Team defense: EPA per run allowed vs EPA per dropback allowed
 11. pass_rush_leaders.png   Defenders: plays with a sack or QB hit, top 30 (ranked bar)
 12. kicker_fgoe.png         Kickers: field-goal points over expected (distance and roof model, 2022-25)

Data: nflverse play-by-play (CC-BY 4.0) and nflverse teams_colors_logos (team colors).
Teams are drawn as color-coded markers with their abbreviation; no logos are used.

Run:  python -m projects.in_season_snippets            (uses the cached 2026 file)
      python -m projects.in_season_snippets --refresh  (re-downloads the season in progress)
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from nflan import data  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "2026-in-season-snippets"
SEASON = 2026

# Look: the static charts share the interactive page's design (fonts in assets/fonts, OFL-licensed): a numbered
# plate with crop marks, the title set left, the club colour on the marks and every word in ink.
from matplotlib import font_manager as _fm  # noqa: E402
import matplotlib.patheffects as _pe  # noqa: E402

for _f in "Unbounded-Medium Unbounded-Bold Literata-Regular Literata-SemiBold Literata-Italic".split():
    _fm.fontManager.addfont(str(ROOT / "assets" / "fonts" / f"{_f}.ttf"))
DISPLAY, TEXT = "Unbounded", "Literata"
PAPER, PLATE, INK, MUTED, SOFT, GRID = "#f5f4ef", "#fdfdfb", "#151613", "#5b5d57", "#8d8f88", "#e8e7e1"
ACCENT, LOT, LOT2 = "#c2410c", "#1a7f4b", None
HALO = [_pe.withStroke(linewidth=3, foreground=PLATE)]
HANDLE = "Dylan Fanelli, github.com/IForSureI/NFL-Analytics"


# ---------------------------------------------------------------- data

def team_colors(refresh: bool = False) -> pd.DataFrame:
    t = data._release("teams", "teams_colors_logos.parquet", refresh)
    t = t[["team_abbr", "team_name", "team_color", "team_color2"]].drop_duplicates("team_abbr")
    return t.set_index("team_abbr")


def completed_weeks(pbp: pd.DataFrame) -> list[int]:
    """Weeks whose games are all in the file. A week counts only when every game on its schedule
    (nflverse schedules) has play-by-play, so a week in progress is left out."""
    sched = data._release("schedules", "games.parquet", refresh=True)
    sched = sched[(sched.season == SEASON) & (sched.game_type == "REG")]
    want = sched.groupby("week").game_id.nunique()
    have = pbp.groupby("week").game_id.nunique()
    return [int(w) for w in have.index if w in want.index and have[w] == want[w]]

def load(refresh: bool = False):
    cols = ["season", "season_type", "week", "game_id", "posteam", "defteam", "play_type", "down", "ydstogo",
            "epa", "success", "qb_dropback", "pass_attempt", "sack", "qb_hit", "qb_scramble", "cpoe",
            "air_yards", "yards_after_catch", "complete_pass", "passing_yards", "receiving_yards",
            "id", "name", "passer_player_id", "passer_player_name", "receiver_player_id",
            "receiver_player_name", "xyac_mean_yardage", "field_goal_attempt", "field_goal_result", "kick_distance", "kicker_player_id", "kicker_player_name", "roof", "sack_player_id", "sack_player_name", "half_sack_1_player_id", "half_sack_1_player_name", "half_sack_2_player_id", "half_sack_2_player_name", "qb_hit_1_player_id", "qb_hit_1_player_name", "qb_hit_2_player_id", "qb_hit_2_player_name", "rusher_player_id", "rusher_player_name", "yards_gained", "wp", "half_seconds_remaining", "pass_oe", "xpass", "two_point_attempt"]
    p = pd.read_parquet(data.pbp_path(SEASON, refresh=refresh), columns=cols)
    p = p[p.season_type == "REG"]
    weeks = completed_weeks(p)
    p = p[p.week.isin(weeks)]
    return p, weeks


# ---------------------------------------------------------------- drawing helpers

def _lum(hexc: str) -> float:
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _readable(*_):
    """Words wear ink; the club colour lives on the mark (dataviz: text tokens, never the series colour)."""
    return INK


def canvas(figsize=(10, 8.6)):
    plt.rcParams.update({"font.family": TEXT, "axes.edgecolor": SOFT, "axes.linewidth": 0.9,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": INK, "text.color": INK,
                         "axes.labelweight": "semibold"})
    fig = plt.figure(figsize=figsize, dpi=200, facecolor=PAPER)
    ax = fig.add_axes([0.10, 0.12, 0.84, 0.68])
    ax.set_facecolor(PLATE)
    ax.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    return fig, ax


def header_footer(fig, title: str, sub: str):
    plt.rcParams.update({"font.family": TEXT})
    fig._plate_title = fig.text(0.06, 0.925, title, ha="left", va="center", fontsize=19,
                                fontweight="bold", family=DISPLAY, color=INK)
    fig.text(0.06, 0.872, sub.replace(" | ", "; "), ha="left", va="center", fontsize=10, style="italic", color=MUTED)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.052, 0.052], transform=fig.transFigure, color=SOFT, lw=0.7))
    fig.text(0.06, 0.028, HANDLE, ha="left", va="center", fontsize=9, color=MUTED)
    fig.text(0.94, 0.028, "Data: nflverse play-by-play", ha="right", va="center", fontsize=9, color=MUTED)
    for x, y, dx, dy in ((0.02, 0.98, 1, -1), (0.98, 0.98, -1, -1), (0.02, 0.02, 1, 1), (0.98, 0.02, -1, 1)):
        fig.add_artist(plt.Line2D([x, x + dx * 0.022], [y, y], transform=fig.transFigure, color=SOFT, lw=0.8))
        fig.add_artist(plt.Line2D([x, x], [y, y + dy * 0.022], transform=fig.transFigure, color=SOFT, lw=0.8))


def corner(ax, text, where):
    pos = {"tl": (0.02, 0.97, "left", "top"), "tr": (0.98, 0.97, "right", "top"),
           "bl": (0.02, 0.03, "left", "bottom"), "br": (0.98, 0.03, "right", "bottom")}[where]
    ax.text(pos[0], pos[1], text, transform=ax.transAxes, ha=pos[2], va=pos[3], fontsize=10.5, style="italic",
            color=ACCENT, zorder=6, path_effects=HALO)


def pad(ax, frac=0.12):
    """Add head-room so the corner boxes sit in empty space, not on top of points."""
    for get, setter in ((ax.get_xlim, ax.set_xlim), (ax.get_ylim, ax.set_ylim)):
        a, b = get()
        d = (b - a) * frac
        setter(a - d, b + d)


def badge(ax, x, y, abbr, c1, c2, s=760, fs=7.6, z=5, text=True):
    """Team badge: outer ring in the second color, a white gap, the main color, the abbreviation.
    Sizes are in points, so the badge stays round whatever the axes' aspect."""
    import matplotlib.transforms as mt
    ax.scatter([x], [y], s=s, color=c2, lw=0, zorder=z + 0.1, clip_on=False)
    ax.scatter([x], [y], s=s * 0.74, color=PLATE, lw=0, zorder=z + 0.2, clip_on=False)
    ax.scatter([x], [y], s=s * 0.58, color=c1, lw=0, zorder=z + 0.3, clip_on=False)
    if text:
        ax.text(x, y, abbr, ha="center", va="center", fontsize=fs, fontweight="bold", zorder=z + 0.4,
                color="white" if _lum(c1) < 0.55 else INK, clip_on=False)


def cap(ax, x, y, abbr, c1, c2):
    """Bar ends carry no badge: the label already names the club, and the badge-on-bar look is a shared template."""
    return None


def side_text(ax, x, y, txt, right=True, pts=13, **kw):
    """Text placed a fixed number of points beside (x, y), clear of a bar-end badge."""
    ax.annotate(txt, (x, y), xytext=(pts if right else -pts, 0), textcoords="offset points", va="center",
                ha="left" if right else "right", **kw)


def team_dots(ax, t, xcol, ycol, tc, size=360, invert_y=False):
    """Team markers, nudged apart where they would overlap; a thin line marks the true spot."""
    xs, ys = t[xcol].to_numpy(float), t[ycol].to_numpy(float)
    xr, yr = xs.max() - xs.min(), ys.max() - ys.min()
    u, v = (xs - xs.min()) / xr, (ys - ys.min()) / yr          # unit square
    pu, pv = u.copy(), v.copy()
    rad = 0.045
    for _ in range(400):
        moved = False
        for i in range(len(pu)):
            for j in range(i + 1, len(pu)):
                du, dv = pu[j] - pu[i], pv[j] - pv[i]
                d = np.hypot(du, dv)
                if d < rad:
                    if d < 1e-9:
                        du, dv, d = 1e-3, 0.0, 1e-3
                    push = (rad - d) / 2
                    pu[i] -= du / d * push; pv[i] -= dv / d * push
                    pu[j] += du / d * push; pv[j] += dv / d * push
                    moved = True
        if not moved:
            break
    px, py = xs.min() + pu * xr, ys.min() + pv * yr
    for k, abbr in enumerate(t.index):
        c1, c2 = tc.loc[abbr, "team_color"], tc.loc[abbr, "team_color2"]
        if np.hypot(pu[k] - u[k], pv[k] - v[k]) > 0.004:
            ax.plot([xs[k], px[k]], [ys[k], py[k]], color=SOFT, lw=0.8, zorder=4)
            ax.scatter([xs[k]], [ys[k]], s=10, color=c1, zorder=4)
        badge(ax, px[k], py[k], abbr, c1, c2)


def player_points(ax, df, x, y, label, team, tc, size_col=None):
    from adjustText import adjust_text
    ax.scatter(df[x], df[y], s=0)
    ax.margins(0.04)
    pad(ax, 0.10)
    sizes = 70 if size_col is None else 40 + 160 * (df[size_col] - df[size_col].min()) / max(1, df[size_col].max() - df[size_col].min())
    for (_, r), s in zip(df.iterrows(), np.broadcast_to(sizes, len(df))):
        c1, c2 = tc.loc[r[team], "team_color"], tc.loc[r[team], "team_color2"]
        ax.scatter(r[x], r[y], s=s, color=c1, edgecolor=c2, linewidth=1.6, zorder=5)
    texts = []
    for _, r in df.iterrows():
        c1, c2 = tc.loc[r[team], "team_color"], tc.loc[r[team], "team_color2"]
        texts.append(ax.text(r[x], r[y], r[label], fontsize=8.6, fontweight="bold",
                             color=_readable(c1, c2), zorder=7, path_effects=HALO))
    adjust_text(texts, ax=ax, expand=(1.25, 1.5), arrowprops=dict(arrowstyle="-", color=SOFT, lw=0.6))


def mean_lines(ax, xm, ym):
    ax.axvline(xm, color=ACCENT, ls=(0, (2, 3)), lw=1.0, zorder=2)
    ax.axhline(ym, color=ACCENT, ls=(0, (2, 3)), lw=1.0, zorder=2)


def sub_line(weeks, extra):
    return f"{SEASON} season, weeks {min(weeks)}-{max(weeks)}. {extra.replace(' | ', '; ')}"


def save(fig, name):
    """Number the plate, keep the title clear of the number, write it."""
    lots = [w for w in __doc__.split("Charts")[1].split("Data:")[0].split() if w.endswith(".png")]
    no = lots.index(name) + 1 if name in lots else None
    if no:
        txt = f"{no:02d}"
        if LOT2:  # two-ink misregistration on the number (risograph)
            fig.text(0.943, 0.917, txt, ha="right", va="center", fontsize=30, fontweight="heavy", family=DISPLAY, color=LOT2, alpha=0.9)
        lot = fig.text(0.94, 0.92, txt, ha="right", va="center", fontsize=30, fontweight="heavy", family=DISPLAY, color=LOT)
        title = getattr(fig, "_plate_title", None)
        if title is not None:
            r = fig.canvas.get_renderer()
            room = lot.get_window_extent(r).x0 - 24
            while title.get_window_extent(r).x1 > room and title.get_fontsize() > 12:
                title.set_fontsize(title.get_fontsize() - 0.5)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=200, facecolor=PAPER)
    plt.close(fig)


# ---------------------------------------------------------------- the six charts

def qb_table(p):
    db = p[(p.qb_dropback == 1) & p.epa.notna() & (p.two_point_attempt != 1)]
    g = db.groupby(["id", "name"]).agg(team=("posteam", lambda s: s.mode().iat[0]), dropbacks=("epa", "size"),
                                         epa=("epa", "mean"), success=("success", "mean")).reset_index()
    att = p[(p.pass_attempt == 1) & (p.sack != 1) & (p.two_point_attempt != 1)]
    a = att.groupby("passer_player_id").agg(cpoe=("cpoe", "mean"), attempts=("pass_attempt", "size"),
                                              adot=("air_yards", "mean")).reset_index()
    comp = att[att.complete_pass == 1]
    y = comp.groupby("passer_player_id").agg(pass_yds=("passing_yards", "sum"),
                                               yac=("yards_after_catch", "sum")).reset_index()
    g = g.merge(a, left_on="id", right_on="passer_player_id", how="left").merge(y, on="passer_player_id", how="left")
    g["yac_share"] = g.yac / g.pass_yds
    return g


def chart_qb_epa_cpoe(p, weeks, tc, f):
    q = qb_table(p)
    q = q[q.dropbacks >= 150].copy()
    fig, ax = canvas()
    player_points(ax, q, "epa", "cpoe", "name", "team", tc)
    mean_lines(ax, q.epa.mean(), q.cpoe.mean())
    corner(ax, "Efficient & accurate", "tr")
    corner(ax, "Struggling", "bl")
    ax.set_xlabel("EPA per dropback", fontsize=12, fontweight="bold")
    ax.set_ylabel("Completion % over expected (CPOE)", fontsize=12, fontweight="bold")
    header_footer(fig, "QB Efficiency: EPA vs. CPOE",
                  sub_line(weeks, f"Min. dropbacks: 150 | Dropbacks include sacks and scrambles"))
    save(fig, "qb_epa_cpoe.png")
    top = q.sort_values("epa", ascending=False)
    f["qb_epa_cpoe"] = {"n_qbs": int(len(q)), "top3_epa": top.head(3)[["name", "team", "epa", "cpoe"]].round(3).to_dict("records"),
                        "bottom3_epa": top.tail(3)[["name", "team", "epa", "cpoe"]].round(3).to_dict("records"),
                        "corr_epa_cpoe": round(float(q.epa.corr(q.cpoe)), 2)}


def chart_rb_success(p, weeks, tc, f):
    """Running backs ranked by rushing success rate, the X-style ranked bar."""
    qbs = set(p[(p.qb_dropback == 1)].groupby("id").size().loc[lambda x: x >= 50].index)
    r = p[(p.play_type == "run") & p.rusher_player_id.notna() & p.epa.notna() & (p.two_point_attempt != 1)
          & (p.qb_scramble != 1) & ~p.rusher_player_id.isin(qbs)]
    g = r.groupby(["rusher_player_id", "rusher_player_name"]).agg(
        team=("posteam", lambda s: s.mode().iat[0]), carries=("epa", "size"), success=("success", "mean"),
        epa=("epa", "mean"), explosive=("yards_gained", lambda y: (y >= 10).mean())).reset_index()
    league = float(r.success.mean())
    n_q = int((g.carries >= 60).sum())
    q = g[g.carries >= 60].sort_values("success", ascending=False).head(30).reset_index(drop=True)
    fig = plt.figure(figsize=(10, 12.5), dpi=200, facecolor="white")
    ax = fig.add_axes([0.07, 0.10, 0.86, 0.74])
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    y = np.arange(len(q))[::-1]
    lo = max(0.0, q.success.min() - 0.08)
    for yi, (_, row) in zip(y, q.iterrows()):
        c1, c2 = tc.loc[row.team, "team_color"], tc.loc[row.team, "team_color2"]
        ax.barh(yi, row.success - lo, left=lo, color=c1, edgecolor=c2, lw=1.2, height=0.8, zorder=3)
        cap(ax, row.success, yi, row.team, c1, c2)
        side_text(ax, row.success, yi, f"{row.rusher_player_name} ({row.team}, {row.carries})", right=False, pts=12,
                  fontsize=9, fontweight="bold", color="white" if _lum(c1) < 0.55 else INK, zorder=4)
        side_text(ax, row.success, yi, f"{100 * row.success:.1f}%", fontsize=9.5, fontweight="bold", color=INK, zorder=4)
        ax.text(1.005, yi, f"{row.epa:+.2f}", transform=ax.get_yaxis_transform(), va="center", ha="left",
                fontsize=9, color=MUTED)
    ax.text(1.005, len(q) - 0.2, "EPA/\nrush", transform=ax.get_yaxis_transform(), va="bottom", ha="left",
            fontsize=8.5, color=MUTED, fontweight="bold")
    ax.axvline(league, color=ACCENT, ls="--", lw=1.3, zorder=2)
    ax.text(league, len(q) - 0.1, f" RB average {100 * league:.1f}%", color=ACCENT, fontsize=9, fontweight="bold",
            va="bottom", ha="left")
    ax.set_yticks(y)
    ax.set_yticklabels(range(1, len(q) + 1), fontsize=9)
    ax.set_xlim(lo, q.success.max() + 0.05)
    ax.set_ylim(-0.7, len(q) + 0.6)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Rushing success rate (play gains positive EPA)", fontsize=12, fontweight="bold")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    header_footer(fig, "Running Back Success Rate",
                  sub_line(weeks, f"Top 30 of {n_q} RBs with 60+ carries | QB runs and scrambles excluded | (team, carries)"))
    save(fig, "rb_success.png")
    f["rb_success"] = {"rb_average_success": round(league, 3), "n_qualified": n_q,
                       "top5": q.head(5)[["rusher_player_name", "team", "carries", "success", "epa", "explosive"]].round(3).to_dict("records"),
                       "corr_success_epa": round(float(q.success.corr(q.epa)), 2)}


def chart_team_tiers(p, weeks, tc, f):
    sc = data.scrimmage(p)
    sc = sc[sc.two_point_attempt != 1]
    o = sc.groupby("posteam").epa.mean().rename("off")
    d = sc.groupby("defteam").epa.mean().rename("def")
    t = pd.concat([o, d], axis=1).dropna()
    fig, ax = canvas()
    team_dots(ax, t, "off", "def", tc)
    pad(ax)
    ax.invert_yaxis()
    mean_lines(ax, t.off.mean(), t["def"].mean())
    lo, hi = ax.get_xlim()
    xs = np.linspace(lo, hi, 50)
    for k in (-0.2, -0.1, 0.0, 0.1, 0.2):  # net EPA iso-lines: off - def = k
        ax.plot(xs, xs - k, color="#cbd5e1", lw=0.8, ls="--", zorder=1)
    ax.set_xlim(lo, hi)
    corner(ax, "Good offense, good defense", "tr")
    corner(ax, "Bad offense, bad defense", "bl")
    ax.set_xlabel("Offense: EPA per play", fontsize=12, fontweight="bold")
    ax.set_ylabel("Defense: EPA per play allowed (better is up)", fontsize=12, fontweight="bold")
    header_footer(fig, "2026 Team Tiers",
                  sub_line(weeks, "Runs and dropbacks, no-plays excluded | Dashed lines = equal net EPA per play"))
    save(fig, "team_tiers.png")
    t["net"] = t.off - t["def"]
    s = t.sort_values("net", ascending=False).round(3)
    f["team_tiers"] = {"top5_net": s.head(5).reset_index().rename(columns={"index": "team"}).to_dict("records"),
                       "bottom5_net": s.tail(5).reset_index().rename(columns={"index": "team"}).to_dict("records")}


def chart_proe(p, weeks, tc, f):
    sc = data.scrimmage(p)
    m = sc.down.isin([1, 2]) & sc.wp.between(0.2, 0.8) & (sc.half_seconds_remaining > 120) & sc.pass_oe.notna()
    n = sc[m]
    t = n.groupby("posteam").agg(proe=("pass_oe", "mean"), plays=("pass_oe", "size")).sort_values("proe", ascending=False)
    t["proe"] = t.proe / 100.0  # nflverse pass_oe is in percentage points
    off = sc[sc.two_point_attempt != 1].groupby("posteam").epa.mean()
    t["epa"] = off
    t["epa_rank"] = t.epa.rank(ascending=False, method="min").astype(int)
    fig = plt.figure(figsize=(10, 12.5), dpi=200, facecolor="white")
    ax = fig.add_axes([0.08, 0.10, 0.80, 0.74])
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    y = np.arange(len(t))[::-1]
    for yi, (abbr, r) in zip(y, t.iterrows()):
        c1, c2 = tc.loc[abbr, "team_color"], tc.loc[abbr, "team_color2"]
        ax.barh(yi, r.proe, color=c1, edgecolor=c2, lw=1.2, height=0.78, zorder=3)
        cap(ax, r.proe, yi, abbr, c1, c2)
        side_text(ax, r.proe, yi, f"{abbr}  {100 * r.proe:+.1f}%", right=r.proe >= 0, fontsize=9.5, fontweight="bold",
                  color=_readable(c1, c2), zorder=4)
        ax.text(1.005, yi, f"#{int(r.epa_rank)}", transform=ax.get_yaxis_transform(), va="center", ha="left",
                fontsize=9, color=MUTED)
    ax.text(1.005, len(t) - 0.2, "Off. EPA\nrank", transform=ax.get_yaxis_transform(), va="bottom", ha="left",
            fontsize=8.5, color=MUTED, fontweight="bold")
    ax.axvline(0, color=INK, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(range(1, len(t) + 1), fontsize=9)
    span = max(abs(t.proe.min()), abs(t.proe.max())) + 0.06
    ax.set_xlim(-span, span)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Pass rate over expected", fontsize=12, fontweight="bold")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    header_footer(fig, "Early-Down Pass Rate Over Expected",
                  sub_line(weeks, "1st & 2nd down | Win prob. 20-80% | Excl. last 2 min of halves | Expected = nflverse xpass"))
    save(fig, "early_down_proe.png")
    r = float(np.corrcoef(t.proe, t.epa)[0, 1])
    f["early_down_proe"] = {"most_pass_happy": t.head(3).proe.round(3).to_dict(), "most_run_heavy": t.tail(3).proe.round(3).to_dict(),
                            "corr_proe_off_epa": round(r, 2), "min_plays": int(t.plays.min())}


def chart_receivers(p, weeks, tc, f):
    tg = p[(p.pass_attempt == 1) & p.receiver_player_id.notna() & (p.two_point_attempt != 1)].copy()
    tg["air"] = tg.air_yards.fillna(0)
    team_game = tg.groupby(["posteam", "game_id"]).agg(t_tgt=("pass_attempt", "size"), t_air=("air", "sum")).reset_index()
    pl_game = tg.groupby(["receiver_player_id", "receiver_player_name", "posteam", "game_id"]).agg(
        tgt=("pass_attempt", "size"), air=("air", "sum")).reset_index()
    pl_game = pl_game.merge(team_game, on=["posteam", "game_id"])
    r = pl_game.groupby(["receiver_player_id", "receiver_player_name"]).agg(
        team=("posteam", lambda s: s.mode().iat[0]), tgt=("tgt", "sum"), air=("air", "sum"),
        t_tgt=("t_tgt", "sum"), t_air=("t_air", "sum"), games=("game_id", "nunique")).reset_index()
    r["tgt_share"] = r.tgt / r.t_tgt
    r["air_share"] = r.air / r.t_air
    r["wopr"] = 1.5 * r.tgt_share + 0.7 * r.air_share
    q = r[r.tgt >= 40].sort_values("wopr", ascending=False).head(40).copy()
    fig, ax = canvas()
    player_points(ax, q, "tgt_share", "air_share", "receiver_player_name", "team", tc)
    xs = np.linspace(q.tgt_share.min() * 0.9, q.tgt_share.max() * 1.05, 50)
    ax.plot(xs, xs, color="#9ca3af", ls="--", lw=1, zorder=1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    corner(ax, "Downfield role", "tl")
    corner(ax, "Volume, shorter targets", "br")
    ax.set_xlabel("Target share (in games played)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Air-yards share (in games played)", fontsize=12, fontweight="bold")
    header_footer(fig, "Receiver Roles: Targets vs. Air Yards",
                  sub_line(weeks, "Top 40 by WOPR, min. 40 targets | Dashed line = equal shares | WOPR = 1.5 x tgt share + 0.7 x air share"))
    save(fig, "receiver_share.png")
    f["receiver_share"] = {"top5_wopr": q.head(5)[["receiver_player_name", "team", "tgt_share", "air_share", "wopr"]].round(3).to_dict("records")}


def chart_defense(p, weeks, tc, f):
    db = p[(p.qb_dropback == 1) & p.epa.notna() & (p.two_point_attempt != 1)].copy()
    db["press"] = ((db.sack == 1) | (db.qb_hit == 1)).astype(int)
    t = db.groupby("defteam").agg(press=("press", "mean"), epa=("epa", "mean"), n=("epa", "size"))
    fig, ax = canvas()
    team_dots(ax, t, "press", "epa", tc)
    pad(ax)
    ax.invert_yaxis()
    mean_lines(ax, t.press.mean(), t.epa.mean())
    b = np.polyfit(t.press, t.epa, 1)
    xs = np.linspace(t.press.min(), t.press.max(), 50)
    ax.plot(xs, np.polyval(b, xs), color="#2563eb", ls="--", lw=1.2, zorder=1)
    ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.02))
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    corner(ax, "Wins without the rush", "tl")
    corner(ax, "Rush gets home, coverage leaks", "br")
    ax.set_xlabel("Sack or QB-hit rate per dropback faced", fontsize=12, fontweight="bold")
    ax.set_ylabel("EPA per dropback allowed (better is up)", fontsize=12, fontweight="bold")
    header_footer(fig, "Pass Defense: Pressure vs. Results",
                  sub_line(weeks, "Pressure proxy = sack or QB hit (play-by-play has no hurries) | Blue line = linear fit"))
    save(fig, "defense_pressure.png")
    r = float(np.corrcoef(t.press, t.epa)[0, 1])
    resid = (t.epa - np.polyval(b, t.press)).sort_values()
    f["defense_pressure"] = {"corr_press_epa": round(r, 2), "best_vs_fit": resid.head(3).round(3).to_dict(),
                             "worst_vs_fit": resid.tail(3).round(3).to_dict()}


# ---------------------------------------------------------------- set two (charts 7-12)

def chart_qb_adot_yac(p, weeks, tc, f):
    q = qb_table(p)
    q = q[q.attempts >= 150].copy()
    fig, ax = canvas()
    player_points(ax, q, "adot", "yac_share", "name", "team", tc)
    mean_lines(ax, q.adot.mean(), q.yac_share.mean())
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    corner(ax, "Short throws, YAC does the work", "tl")
    corner(ax, "Pushes it downfield", "br")
    ax.set_xlabel("Average depth of target (air yards per attempt)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Share of passing yards gained after the catch", fontsize=12, fontweight="bold")
    header_footer(fig, "Where QB Yards Come From",
                  sub_line(weeks, "Min. attempts: 150 | YAC share = YAC / passing yards on completions"))
    save(fig, "qb_adot_yac.png")
    s = q.sort_values("yac_share", ascending=False)
    f["qb_adot_yac"] = {"n_qbs": int(len(q)), "corr_adot_yac_share": round(float(q.adot.corr(q.yac_share)), 2),
                        "most_yac": s.head(3)[["name", "team", "adot", "yac_share"]].round(3).to_dict("records"),
                        "least_yac": s.tail(3)[["name", "team", "adot", "yac_share"]].round(3).to_dict("records")}



def ranked_bars(rows, value, label, team, tc, fmt, xlabel, title, sub, fname, ref=None, ref_label="", right=None,
                right_head="", diverging=False, names_left=False):
    """The ranked-bar look: name inside a team-colored bar, value at the end, optional right-hand column."""
    fig = plt.figure(figsize=(10, 12.5), dpi=200, facecolor="white")
    ax = fig.add_axes([0.30, 0.10, 0.62, 0.74] if names_left else [0.07, 0.10, 0.86, 0.74])
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    n = len(rows)
    y = np.arange(n)[::-1]
    vals = rows[value].to_numpy(float)
    if names_left:
        base, span = 0.0, np.abs(vals).max()
        lo, hi = min(0.0, vals.min()) - span * 0.12, vals.max() + span * 0.16
    elif diverging:
        base = 0.0
        span = np.abs(vals).max()
        lo, hi = -span * 1.45, span * 1.45
    else:
        lo = max(0.0, vals.min() - (vals.max() - vals.min()) * 0.45) if vals.min() >= 0 else vals.min() * 1.2
        base, hi = lo, vals.max() + (vals.max() - lo) * 0.14
    for yi, (_, r) in zip(y, rows.iterrows()):
        c1, c2 = tc.loc[r[team], "team_color"], tc.loc[r[team], "team_color2"]
        v = r[value]
        ax.barh(yi, v - base, left=base, color=c1, edgecolor=c2, lw=1.2, height=0.8, zorder=3)
        inside = "white" if _lum(c1) < 0.55 else INK
        cap(ax, v, yi, r[team], c1, c2)
        if names_left:
            ax.text(-0.012, yi, r[label], transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=9.5,
                    fontweight="bold", color=_readable(c1, c2), zorder=4)
            side_text(ax, v, yi, fmt(v), right=v >= 0, fontsize=9.5, fontweight="bold", color=INK, zorder=4)
        elif diverging:
            # name on the zero side, value beyond the badge at the bar end
            ax.text(-0.01 * span if v >= 0 else 0.01 * span, yi, r[label], ha="right" if v >= 0 else "left",
                    va="center", fontsize=9, fontweight="bold", color=_readable(c1, c2), zorder=4)
            side_text(ax, v, yi, fmt(v), right=v >= 0, fontsize=9.5, fontweight="bold", color=INK, zorder=4)
        else:
            side_text(ax, v, yi, r[label], right=False, pts=12, fontsize=9, fontweight="bold", color=inside, zorder=4)
            side_text(ax, v, yi, fmt(v), fontsize=9.5, fontweight="bold", color=INK, zorder=4)
        if right is not None:
            ax.text(1.005, yi, right(r), transform=ax.get_yaxis_transform(), va="center", ha="left", fontsize=9,
                    color=MUTED)
    if right is not None:
        ax.text(1.005, n - 0.2, right_head, transform=ax.get_yaxis_transform(), va="bottom", ha="left", fontsize=8.5,
                color=MUTED, fontweight="bold")
    if diverging:
        ax.axvline(0, color=INK, lw=1, zorder=2)
    if ref is not None:
        ax.axvline(ref, color=ACCENT, ls="--", lw=1.3, zorder=2)
        ax.text(ref, n - 0.1, f" {ref_label}", color=ACCENT, fontsize=9, fontweight="bold", va="bottom", ha="left")
    if diverging or names_left:
        ax.axvline(0, color=INK, lw=1, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(range(1, n + 1), fontsize=9)
    if names_left:
        ax.set_yticklabels([])
        ax.tick_params(axis="y", length=0)
        for yi, k in zip(y, range(1, n + 1)):
            ax.text(-0.42, yi, f"{k}", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=9, color=MUTED)
    ax.set_xlim(lo, hi)
    ax.set_ylim(-0.7, n + 0.6)
    ax.set_xlabel(xlabel, fontsize=12, fontweight="bold")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    header_footer(fig, title, sub)
    save(fig, fname)


def chart_receiver_epa_adot(p, weeks, tc, f):
    tg = p[(p.pass_attempt == 1) & (p.sack != 1) & p.receiver_player_id.notna() & p.epa.notna() & (p.two_point_attempt != 1)]
    r = tg.groupby(["receiver_player_id", "receiver_player_name"]).agg(
        team=("posteam", lambda s: s.mode().iat[0]), tgt=("epa", "size"), epa=("epa", "mean"),
        adot=("air_yards", "mean"), catch=("complete_pass", "mean")).reset_index()
    q = r[r.tgt >= 40].sort_values("tgt", ascending=False).head(45).copy()
    fig, ax = canvas()
    player_points(ax, q, "adot", "epa", "receiver_player_name", "team", tc)
    mean_lines(ax, q.adot.mean(), q.epa.mean())
    corner(ax, "Deep role, big value", "tr")
    corner(ax, "Short role, low value", "bl")
    ax.set_xlabel("Average depth of target (air yards)", fontsize=12, fontweight="bold")
    ax.set_ylabel("EPA per target", fontsize=12, fontweight="bold")
    header_footer(fig, "Receivers: Role vs. Value",
                  sub_line(weeks, "45 most-targeted receivers (WR, TE, RB), min. 40 targets | Dotted lines = group average"))
    save(fig, "receiver_epa_adot.png")
    s = q.sort_values("epa", ascending=False)
    f["receiver_epa_adot"] = {"n": int(len(q)), "top5_epa_per_target": s.head(5)[["receiver_player_name", "team", "tgt", "adot", "epa"]].round(3).to_dict("records"),
                              "corr_adot_epa": round(float(q.adot.corr(q.epa)), 2)}


def chart_yac_oe(p, weeks, tc, f):
    c = p[(p.complete_pass == 1) & p.receiver_player_id.notna() & p.yards_after_catch.notna() & p.xyac_mean_yardage.notna()
          & (p.two_point_attempt != 1)].copy()
    c["yacoe"] = c.yards_after_catch - c.xyac_mean_yardage
    r = c.groupby(["receiver_player_id", "receiver_player_name"]).agg(
        team=("posteam", lambda s: s.mode().iat[0]), rec=("yacoe", "size"), yacoe=("yacoe", "mean"),
        yac=("yards_after_catch", "mean")).reset_index()
    league = float(c.yacoe.mean())
    n_q = int((r.rec >= 25).sum())
    q = r[r.rec >= 25].sort_values("yacoe", ascending=False).head(30).reset_index(drop=True)
    q["lab"] = q.receiver_player_name + " (" + q.team + ", " + q.rec.astype(str) + ")"
    ranked_bars(q, "yacoe", "lab", "team", tc, lambda v: f"{v:+.2f}", "Yards after the catch over expected, per reception",
                "YAC Over Expected per Catch",
                sub_line(weeks, f"Top 30 of {n_q} players with 25+ catches | Expected = nflverse xYAC model | (team, catches)"),
                "yac_over_expected.png", ref=None, right=lambda r: f"{r.yac:.1f}", right_head="YAC/\nrec", names_left=True)
    f["yac_over_expected"] = {"league_mean": round(league, 3), "n_qualified": n_q,
                              "top5": q.head(5)[["receiver_player_name", "team", "rec", "yacoe", "yac"]].round(2).to_dict("records")}


def chart_defense_run_pass(p, weeks, tc, f):
    sc = data.scrimmage(p)
    sc = sc[sc.two_point_attempt != 1]
    run = sc[(sc.play_type == "run") & (sc.qb_scramble != 1)].groupby("defteam").epa.mean().rename("run")
    pas = sc[sc.qb_dropback == 1].groupby("defteam").epa.mean().rename("pass")
    t = pd.concat([run, pas], axis=1).dropna()
    fig, ax = canvas()
    team_dots(ax, t, "run", "pass", tc)
    pad(ax)
    ax.invert_xaxis()
    ax.invert_yaxis()
    mean_lines(ax, t["run"].mean(), t["pass"].mean())
    corner(ax, "Stops both", "tr")
    corner(ax, "Gets hit both ways", "bl")
    ax.set_xlabel("EPA per run allowed (better is right)", fontsize=12, fontweight="bold")
    ax.set_ylabel("EPA per dropback allowed (better is up)", fontsize=12, fontweight="bold")
    header_footer(fig, "Defense: Run Stopping vs. Pass Defense",
                  sub_line(weeks, "Designed runs (scrambles go to pass) | Dropbacks include sacks | Dotted lines = league average"))
    save(fig, "defense_run_pass.png")
    t["both"] = t["run"] + t["pass"]
    f["defense_run_pass"] = {"best_run_d": t["run"].nsmallest(3).round(3).to_dict(), "best_pass_d": t["pass"].nsmallest(3).round(3).to_dict(),
                             "corr_run_pass": round(float(t["run"].corr(t["pass"])), 2)}


def chart_pass_rush(p, weeks, tc, f):
    d = p[(p.qb_dropback == 1) & (p.two_point_attempt != 1)]
    rows = []
    for _, r in d.iterrows():
        seen = {}
        if pd.notna(r.sack_player_id):
            seen[r.sack_player_id] = (r.sack_player_name, 1.0)
        for i in (1, 2):
            pid = r[f"half_sack_{i}_player_id"]
            if pd.notna(pid):
                seen[pid] = (r[f"half_sack_{i}_player_name"], 0.5)
        for i in (1, 2):
            pid = r[f"qb_hit_{i}_player_id"]
            if pd.notna(pid) and pid not in seen:
                seen[pid] = (r[f"qb_hit_{i}_player_name"], 0.0)
        for pid, (nm, sk) in seen.items():
            rows.append((pid, nm, r.defteam, sk))
    e = pd.DataFrame(rows, columns=["pid", "name", "team", "sacks"])
    g = e.groupby("pid").agg(name=("name", "first"), team=("team", lambda s: s.mode().iat[0]), events=("sacks", "size"),
                             sacks=("sacks", "sum")).reset_index()
    q = g.sort_values(["events", "sacks"], ascending=False).head(30).reset_index(drop=True)
    q["lab"] = q.name + " (" + q.team + ")"
    ranked_bars(q, "events", "lab", "team", tc, lambda v: f"{int(v)}", "Plays with a sack or QB hit",
                "Pass Rush Leaders: Sacks + QB Hits",
                sub_line(weeks, "Each play counted once per player (a sack that is also a hit counts once) | Half sacks = 0.5"),
                "pass_rush_leaders.png", right=lambda r: f"{r.sacks:g}", right_head="Sacks")
    f["pass_rush_leaders"] = {"top5": q.head(5)[["name", "team", "events", "sacks"]].to_dict("records")}


def fg_model():
    """League make probability by distance from 2022-25 regular seasons (logistic in distance)."""
    from sklearn.linear_model import LogisticRegression
    cols = ["season_type", "field_goal_attempt", "field_goal_result", "kick_distance", "roof"]
    h = data.load_pbp(range(2022, 2026), columns=cols)
    h = h[(h.season_type == "REG") & (h.field_goal_attempt == 1) & h.kick_distance.notna()]
    X = np.c_[h.kick_distance, h.kick_distance ** 2, h.roof.isin(["dome", "closed"])]
    m = LogisticRegression(max_iter=1000, C=1e6).fit(X, (h.field_goal_result == "made").astype(int))
    return m, len(h)


def chart_kickers(p, weeks, tc, f):
    m, n_hist = fg_model()
    k = p[(p.field_goal_attempt == 1) & p.kick_distance.notna()].copy()
    k["p"] = m.predict_proba(np.c_[k.kick_distance, k.kick_distance ** 2, k.roof.isin(["dome", "closed"])])[:, 1]
    k["made"] = (k.field_goal_result == "made").astype(int)
    g = k.groupby(["kicker_player_id", "kicker_player_name"]).agg(
        team=("posteam", lambda s: s.mode().iat[0]), att=("made", "size"), made=("made", "sum"), exp=("p", "sum"),
        long=("kick_distance", lambda s: s[k.loc[s.index, "made"] == 1].max())).reset_index()
    g["fgoe_pts"] = 3 * (g.made - g.exp)
    q = g[g.att >= 8].sort_values("fgoe_pts", ascending=False).reset_index(drop=True)
    q["lab"] = q.kicker_player_name + " (" + q.team + ")"
    ranked_bars(q, "fgoe_pts", "lab", "team", tc, lambda v: f"{v:+.1f}", "Field-goal points over expected",
                "Kickers: FG Points Over Expected",
                sub_line(weeks, f"Min. 8 attempts | Expected make rate by distance and roof, fit on {n_hist:,} 2022-25 kicks | made-att at right"),
                "kicker_fgoe.png", right=lambda r: f"{int(r.made)}-{int(r.att)}", right_head="FG", diverging=True)
    f["kicker_fgoe"] = {"n": int(len(q)), "model_kicks": int(n_hist),
                        "top3": q.head(3)[["kicker_player_name", "team", "made", "att", "fgoe_pts"]].round(2).to_dict("records"),
                        "bottom3": q.tail(3)[["kicker_player_name", "team", "made", "att", "fgoe_pts"]].round(2).to_dict("records")}


def main(refresh: bool = False):
    p, weeks = load(refresh)
    tc = team_colors()
    f = {"season": SEASON, "weeks": [int(min(weeks)), int(max(weeks))], "built": date.today().isoformat(),
         "plays": int(len(p))}
    chart_qb_epa_cpoe(p, weeks, tc, f)
    chart_rb_success(p, weeks, tc, f)
    chart_team_tiers(p, weeks, tc, f)
    chart_proe(p, weeks, tc, f)
    chart_receivers(p, weeks, tc, f)
    chart_defense(p, weeks, tc, f)
    chart_qb_adot_yac(p, weeks, tc, f)
    chart_receiver_epa_adot(p, weeks, tc, f)
    chart_yac_oe(p, weeks, tc, f)
    chart_defense_run_pass(p, weeks, tc, f)
    chart_pass_rush(p, weeks, tc, f)
    chart_kickers(p, weeks, tc, f)
    (OUT / "findings.json").write_text(json.dumps(f, indent=1, default=float))
    print(json.dumps(f, indent=1, default=float)[:3000])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    main(ap.parse_args().refresh)
