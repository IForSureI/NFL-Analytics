"""2026 In-Season Snippets: six quick charts on the season in progress.

Question: what does the 2026 season look like so far, through the lens of a few
numbers a coaching staff or front office would actually look at on a Monday?

Charts (all from nflverse play-by-play, regular season, completed weeks only):
  1. qb_epa_cpoe.png         QB efficiency: EPA per dropback vs completion % over expected
  2. qb_adot_yac.png         How QBs get their yards: depth of target vs share of yards after the catch
  3. team_tiers.png          Team tiers: offensive EPA/play vs defensive EPA/play allowed
  4. early_down_proe.png     Who throws on early downs: neutral-situation pass rate over expected
  5. receiver_share.png      Receiver roles: target share vs air-yards share (WOPR)
  6. defense_pressure.png    Pass defense: pressure-proxy rate vs EPA per dropback allowed

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

INK = "#1d2433"
MUTED = "#6b7280"
GRID = "#e5e7eb"
BAND = "#1d2433"
ACCENT = "#c2410c"
BOX = "#e8f1fb"
BOX_EDGE = "#5b7fa6"
HANDLE = "Dylan Fanelli  |  github.com/IForSureI/NFL-Analytics"


# ---------------------------------------------------------------- data

def team_colors(refresh: bool = False) -> pd.DataFrame:
    t = data._release("teams", "teams_colors_logos.parquet", refresh)
    t = t[["team_abbr", "team_name", "team_color", "team_color2"]].drop_duplicates("team_abbr")
    return t.set_index("team_abbr")


def completed_weeks(pbp: pd.DataFrame) -> list[int]:
    """Weeks whose games are all in the file (a week in progress is dropped)."""
    g = pbp.groupby("week")["game_id"].nunique()
    # A week is complete if it has at least 13 games (max 6 teams on bye) and is not the last
    # week when that last week has fewer games than the week before it.
    weeks = sorted(g.index)
    keep = [w for w in weeks if g[w] >= 13]
    return keep


def load(refresh: bool = False):
    cols = ["season", "season_type", "week", "game_id", "posteam", "defteam", "play_type", "down", "ydstogo",
            "epa", "success", "qb_dropback", "pass_attempt", "sack", "qb_hit", "qb_scramble", "cpoe",
            "air_yards", "yards_after_catch", "complete_pass", "passing_yards", "receiving_yards",
            "id", "name", "passer_player_id", "passer_player_name", "receiver_player_id",
            "receiver_player_name", "wp", "half_seconds_remaining", "pass_oe", "xpass", "two_point_attempt"]
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


def _readable(hexc: str, other: str) -> str:
    """Team color for text on white; fall back to the secondary or ink if too light."""
    if _lum(hexc) < 0.62:
        return hexc
    return other if _lum(other) < 0.62 else INK


def canvas(figsize=(10, 8.6)):
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#9ca3af", "axes.linewidth": 1.0,
                         "xtick.color": INK, "ytick.color": INK, "axes.labelcolor": INK, "text.color": INK})
    fig = plt.figure(figsize=figsize, dpi=200, facecolor="white")
    ax = fig.add_axes([0.10, 0.12, 0.86, 0.70])
    ax.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    return fig, ax


def header_footer(fig, title: str, sub: str):
    fig.text(0.5, 0.93, title, ha="center", va="center", fontsize=25, fontweight="black", color=INK)
    fig.text(0.5, 0.875, sub, ha="center", va="center", fontsize=10, color=MUTED)
    fig.add_artist(Rectangle((0, 0), 1, 0.055, transform=fig.transFigure, color=BAND, zorder=0))
    fig.text(0.02, 0.0275, HANDLE, ha="left", va="center", fontsize=10.5, color="white", fontweight="bold")
    fig.text(0.98, 0.0275, "Data: nflverse play-by-play", ha="right", va="center", fontsize=10.5,
             color="#fca5a5", fontweight="bold")


def corner(ax, text, where):
    pos = {"tl": (0.02, 0.97, "left", "top"), "tr": (0.98, 0.97, "right", "top"),
           "bl": (0.02, 0.03, "left", "bottom"), "br": (0.98, 0.03, "right", "bottom")}[where]
    ax.text(pos[0], pos[1], text, transform=ax.transAxes, ha=pos[2], va=pos[3], fontsize=11,
            fontweight="bold", color="#1e40af",
            bbox=dict(boxstyle="round,pad=0.35", fc=BOX, ec=BOX_EDGE, lw=1.0), zorder=6)


def pad(ax, frac=0.12):
    """Add head-room so the corner boxes sit in empty space, not on top of points."""
    for get, setter in ((ax.get_xlim, ax.set_xlim), (ax.get_ylim, ax.set_ylim)):
        a, b = get()
        d = (b - a) * frac
        setter(a - d, b + d)


def team_dots(ax, t, xcol, ycol, tc, size=360, invert_y=False):
    """Team markers, nudged apart where they would overlap; a thin line marks the true spot."""
    xs, ys = t[xcol].to_numpy(float), t[ycol].to_numpy(float)
    xr, yr = xs.max() - xs.min(), ys.max() - ys.min()
    u, v = (xs - xs.min()) / xr, (ys - ys.min()) / yr          # unit square
    pu, pv = u.copy(), v.copy()
    rad = 0.036
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
            ax.plot([xs[k], px[k]], [ys[k], py[k]], color="#9ca3af", lw=0.8, zorder=4)
            ax.scatter([xs[k]], [ys[k]], s=10, color=c1, zorder=4)
        ax.scatter([px[k]], [py[k]], s=size, color=c1, edgecolor=c2, linewidth=2.0, zorder=5)
        ax.text(px[k], py[k], abbr, ha="center", va="center", fontsize=6.8, fontweight="bold",
                color="white" if _lum(c1) < 0.55 else INK, zorder=6)


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
                             color=_readable(c1, c2), zorder=7))
    adjust_text(texts, ax=ax, expand=(1.25, 1.5), arrowprops=dict(arrowstyle="-", color="#9ca3af", lw=0.6))


def mean_lines(ax, xm, ym):
    ax.axvline(xm, color=ACCENT, ls=":", lw=1.1, zorder=2)
    ax.axhline(ym, color=ACCENT, ls=":", lw=1.1, zorder=2)


def sub_line(weeks, extra):
    w = f"Weeks: {min(weeks)}-{max(weeks)}"
    return f"Season: {SEASON} | {w} | {extra}"


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=200, facecolor="white")
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
    player_points(ax, q, "epa", "cpoe", "name", "team", tc, size_col="dropbacks")
    mean_lines(ax, q.epa.mean(), q.cpoe.mean())
    corner(ax, "Efficient & accurate", "tr")
    corner(ax, "Struggling", "bl")
    ax.set_xlabel("EPA per dropback", fontsize=12, fontweight="bold")
    ax.set_ylabel("Completion % over expected (CPOE)", fontsize=12, fontweight="bold")
    header_footer(fig, "QB Efficiency: EPA vs. CPOE",
                  sub_line(weeks, f"Min. dropbacks: 150 | Dropbacks include sacks and scrambles | Bubble size = dropbacks"))
    save(fig, "qb_epa_cpoe.png")
    top = q.sort_values("epa", ascending=False)
    f["qb_epa_cpoe"] = {"n_qbs": int(len(q)), "top3_epa": top.head(3)[["name", "team", "epa", "cpoe"]].round(3).to_dict("records"),
                        "bottom3_epa": top.tail(3)[["name", "team", "epa", "cpoe"]].round(3).to_dict("records"),
                        "corr_epa_cpoe": round(float(q.epa.corr(q.cpoe)), 2)}


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
        xt = r.proe + (0.003 if r.proe >= 0 else -0.003)
        ax.text(xt, yi, f"{abbr}  {100 * r.proe:+.1f}%", va="center", ha="left" if r.proe >= 0 else "right",
                fontsize=9.5, fontweight="bold", color=_readable(c1, c2), zorder=4)
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


def main(refresh: bool = False):
    p, weeks = load(refresh)
    tc = team_colors()
    f = {"season": SEASON, "weeks": [int(min(weeks)), int(max(weeks))], "built": date.today().isoformat(),
         "plays": int(len(p))}
    chart_qb_epa_cpoe(p, weeks, tc, f)
    chart_qb_adot_yac(p, weeks, tc, f)
    chart_team_tiers(p, weeks, tc, f)
    chart_proe(p, weeks, tc, f)
    chart_receivers(p, weeks, tc, f)
    chart_defense(p, weeks, tc, f)
    (OUT / "findings.json").write_text(json.dumps(f, indent=1, default=float))
    print(json.dumps(f, indent=1, default=float)[:3000])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    main(ap.parse_args().refresh)
