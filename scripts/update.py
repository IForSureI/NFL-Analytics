"""Refresh the season in progress and its side tables (contracts, charting, players, snaps, Next Gen Stats),
then rebuild every study, test and README.

    python scripts/update.py            # refresh the current season, run everything
    python scripts/update.py --no-download

Weekly in season: run this, check that tests pass, read the diff in reports/*/findings.json,
then commit with a one-line LOG.md entry.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflan import data  # noqa: E402

STUDIES = ["flag_audit", "fourth_down_bot", "sack_leverage", "luck_index", "kickoff_value", "pass_run", "box_score_tax", "yac_tax", "run_game_value", "in_season_snippets"]


def current_season(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year if today.month >= 9 else today.year - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()
    import os
    os.chdir(ROOT)
    season = current_season()
    if not a.no_download:
        for s in range(data.FIRST_SEASON, season + 1):
            data.pbp_path(s, refresh=(s == season))
        data.load_officials(refresh=True)
        # the side tables the contract and kickoff studies read; without this they would stay at their first download
        data.load_contracts(refresh=True)
        data.load_pfr_def(refresh=True)
        data.load_players(refresh=True)
        data.load_ngs_receiving(refresh=True)
        data.load_draft_picks(refresh=True)
        data.load_snap_counts(range(2018, season + 1), refresh_current=season)
        from projects.run_game_value import load_ngs_rushing
        load_ngs_rushing(refresh=True)
    for name in STUDIES:
        print(f"== {name}")
        importlib.import_module(f"projects.{name}").main()
    importlib.import_module("projects.in_season_web").main()  # the interactive snippets page, docs/snippets.html
    subprocess.run([sys.executable, "scripts/build_figures.py"], check=True)
    subprocess.run([sys.executable, "scripts/build_readmes.py"], check=True)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
