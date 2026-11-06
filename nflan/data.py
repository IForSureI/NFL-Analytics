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
