"""Refresh the season in progress and rebuild every study, test and README.

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

STUDIES = ["flag_audit", "fourth_down_bot", "sack_leverage", "luck_index", "kickoff_value", "pass_run", "box_score_tax", "yac_tax"]


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
    for name in STUDIES:
        print(f"== {name}")
        importlib.import_module(f"projects.{name}").main()
    subprocess.run([sys.executable, "scripts/build_figures.py"], check=True)
    subprocess.run([sys.executable, "scripts/build_readmes.py"], check=True)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
