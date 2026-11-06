"""Download, cache and load nflverse play-by-play and side tables.

Data: nflverse (https://github.com/nflverse/nflverse-data), CC-BY 4.0.
Files are cached in ./data/raw (git-ignored). Set NFLAN_DATA to move the cache.
"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
DATA_DIR = Path(os.environ.get("NFLAN_DATA", Path(__file__).resolve().parents[1] / "data" / "raw"))

FIRST_SEASON = 2006  # pbp is complete with EPA/WP from 1999; we start in 2006 for modern rules


def _fetch(url: str, dest: Path, refresh: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if refresh or not dest.exists():
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    return dest


def pbp_path(season: int, refresh: bool = False) -> Path:
    return _fetch(f"{BASE}/pbp/play_by_play_{season}.parquet", DATA_DIR / f"pbp_{season}.parquet", refresh)


def load_pbp(seasons, columns=None, refresh_current: int | None = None) -> pd.DataFrame:
    """Load play-by-play for one or more seasons (list or range).

    refresh_current: a season to re-download even if cached (the season in progress).
    """
    if isinstance(seasons, int):
        seasons = [seasons]
    frames = []
    for s in seasons:
        p = pbp_path(s, refresh=(s == refresh_current))
        frames.append(pd.read_parquet(p, columns=columns))
    return pd.concat(frames, ignore_index=True)


def load_officials(refresh: bool = False) -> pd.DataFrame:
    p = _fetch(f"{BASE}/officials/officials.parquet", DATA_DIR / "officials.parquet", refresh)
    return pd.read_parquet(p)


def load_draft_picks(refresh: bool = False) -> pd.DataFrame:
    p = _fetch(f"{BASE}/draft_picks/draft_picks.parquet", DATA_DIR / "draft_picks.parquet", refresh)
    return pd.read_parquet(p)


def latest_season_available() -> int:
    """Highest season whose pbp file is cached locally."""
    seasons = [int(p.stem.split("_")[1]) for p in DATA_DIR.glob("pbp_*.parquet")]
    return max(seasons)


def scrimmage(pbp: pd.DataFrame) -> pd.DataFrame:
    """Real offensive snaps: runs and dropbacks with a valid EPA (penalty no-plays excluded)."""
    m = pbp["play_type"].isin(["run", "pass"]) & pbp["epa"].notna() & pbp["down"].notna()
    return pbp.loc[m]


def games(pbp: pd.DataFrame) -> pd.DataFrame:
    """One row per game with final score, teams, spread and season info."""
    cols = ["game_id", "season", "season_type", "week", "home_team", "away_team",
            "home_score", "away_score", "result", "spread_line", "roof", "home_coach", "away_coach"]
    g = pbp[cols].drop_duplicates("game_id").copy()
    return g.reset_index(drop=True)


def _release(tag: str, fname: str, refresh: bool = False) -> pd.DataFrame:
    return pd.read_parquet(_fetch(f"{BASE}/{tag}/{fname}", DATA_DIR / fname, refresh))


def load_contracts(refresh: bool = False) -> pd.DataFrame:
    """Over The Cap contract history via nflverse (one row per contract)."""
    return _release("contracts", "historical_contracts.parquet", refresh)


def load_pfr_def(refresh: bool = False) -> pd.DataFrame:
    """Pro Football Reference advanced defense, season level (2018+): pressures, hurries, coverage."""
    return _release("pfr_advstats", "advstats_season_def.parquet", refresh)


def load_players(refresh: bool = False) -> pd.DataFrame:
    return _release("players", "players.parquet", refresh)


def load_snap_counts(seasons, refresh_current: int | None = None) -> pd.DataFrame:
    if isinstance(seasons, int):
        seasons = [seasons]
    return pd.concat([_release("snap_counts", f"snap_counts_{s}.parquet", s == refresh_current) for s in seasons],
                     ignore_index=True)


def load_ngs_receiving(refresh: bool = False) -> pd.DataFrame:
    """NFL Next Gen Stats receiving (2016+). week == 0 rows are season totals for qualified receivers."""
    return _release("nextgen_stats", "ngs_receiving.parquet", refresh)


def contract_end_year(history) -> float:
    """Last season of a player's current deal from Over The Cap contract_history.

    New deals run year_signed .. year_signed + yrs - 1. An extension adds its years after the deal
    it extends (OTC counts only the new years). Fifth-year options and void years are not counted.
    """
    if history is None or len(history) == 0:
        return float("nan")
    seen, rows = set(), []
    for h in history:
        if h.get("year_signed") is None or h.get("yrs") is None:
            continue
        key = (h.get("contract_type"), int(h["year_signed"]), int(h["yrs"]))
        if key not in seen:  # OTC sometimes lists the same deal twice
            seen.add(key); rows.append(h)
    rows.sort(key=lambda h: h["year_signed"])
    end = None
    for h in rows:
        y, n = int(h["year_signed"]), int(h["yrs"])
        if h.get("contract_type") == "Extension" and end is not None and end >= y:
            end = end + n
        else:
            end = y + n - 1
    return float(end) if end is not None else float("nan")
