"""Draft prospect report (reports/draft-2027-drew-mestemaker): the data adds up and the page matches findings.json."""
import json
from pathlib import Path

import pandas as pd

from projects.draft_mestemaker import ME, SEASON, load, ncaa_rating

R = Path(__file__).resolve().parents[1] / "reports" / "draft-2027-drew-mestemaker"
SECTIONS = ["**TL;DR**", "## Key numbers", "## Why it matters for a club", "## The question", "## Data", "## Results", "## Verdict",
            "## Method", "## Validation", "## Limitations", "## Next steps", "## Reproduce", "## Files in this folder"]


def test_game_log_sums_to_season_line():
    D, G, *_ = load()
    me = D[(D.Name == ME) & (D.season == SEASON)].iloc[0]
    g = G[(G.player == ME) & (G.season == SEASON)]
    for col in ["Att", "Comp", "Yards", "TD", "Int"]:
        assert g[col].sum() == me[col], col
    assert abs(ncaa_rating(me.Comp, me.Att, me.Yards, me.TD, me.Int) - me.Rating) < 0.01


def test_first_round_group_is_complete():
    D, _, _, FR, _ = load()
    fr = FR[FR.in_fbs_data].merge(D, left_on=["cfbstats_name", "final_season"], right_on=["Name", "season"])
    assert len(fr) == 18 and fr.x25.notna().all() and fr.r3.notna().all()


def test_every_mover_has_both_seasons():
    D, *_, MV = load()
    for r in MV.itertuples():
        for y in (r.season_before, r.season_after):
            assert len(D[(D.player_id == r.player_id) & (D.season == y)]) == 1, (r.name, y)


def test_readme_matches_findings():
    f = json.loads((R / "findings.json").read_text())
    text = (R / "README.md").read_text()
    for s in SECTIONS:
        assert s in text, s
    L = f["line"]
    assert f"{L['Comp']}-of-{L['Att']}, {L['Yards']:,} yards, {L['TD']} TD, {L['Int']} INT" in text
    for png in ["explosive_vs_first_round", "national_ranks", "class_map", "g5_to_p4", "stability", "game_log"]:
        assert f"{png}.png" in text and (R / f"{png}.png").exists()
    assert pd.read_csv(R / "class_table.csv").Name.iloc[0] == ME
