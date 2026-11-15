"""Draft evaluation (reports/draft-2027-drew-mestemaker): the data adds up, the methods behave, the page matches findings.json."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from projects.draft_mestemaker import CLASS, DATA, ME, SEASON, load, ncaa_rating, opp_adjusted, wilson, with_outcomes

R = Path(__file__).resolve().parents[1] / "reports" / "draft-2027-drew-mestemaker"
SECTIONS = ["**TL;DR**", "## Key numbers", "## Why it matters for a club", "## The question", "## Data", "## Results", "## Verdict",
            "## Method", "## Validation", "## Limitations", "## Next steps", "## Reproduce", "## Files in this folder"]
FIGS = ["opponent_adjusted", "national_ranks", "class_map", "base_rate", "g5_to_p4", "stability", "explosive_vs_first_round", "game_log"]


def test_game_log_sums_to_season_line():
    D, G, *_ = load()
    me = D[(D.Name == ME) & (D.season == SEASON)].iloc[0]
    g = G[(G.player == ME) & (G.season == SEASON)]
    for col in ["Att", "Comp", "Yards", "TD", "Int"]:
        assert g[col].sum() == me[col], col
    assert abs(ncaa_rating(me.Comp, me.Att, me.Yards, me.TD, me.Int) - me.Rating) < 0.01


def test_first_round_group_is_complete():
    D, G, _, FR, _ = load()
    fr = FR[FR.in_fbs_data].merge(D, left_on=["cfbstats_name", "final_season"], right_on=["Name", "season"])
    assert len(fr) == 18 and fr.x25.notna().all() and fr.r3.notna().all()
    for r in FR[FR.in_fbs_data].itertuples():  # a game log for the same-games and opponent comparisons
        g = G[(G.player == r.cfbstats_name) & (G.season == r.final_season) & G.Att.notna()]
        row = D[(D.Name == r.cfbstats_name) & (D.season == r.final_season)].iloc[0]
        assert g.Att.sum() == row.Att and g.Yards.sum() == row.Yards, r.cfbstats_name


def test_every_mover_has_both_seasons_and_fbs_splits():
    D, _, SP, _, MV = load()
    fb = SP[SP.Split == "vs. FBS (I-A)"]
    for r in MV.itertuples():
        for y in (r.season_before, r.season_after):
            assert len(D[(D.player_id == r.player_id) & (D.season == y)]) == 1, (r.name, y)
            assert len(fb[(fb.player == r.name) & (fb.season == y)]) == 1, (r.name, y)


def test_wilson_interval():
    lo, hi = wilson(50, 100)
    assert abs(lo - 40.38) < 0.05 and abs(hi - 59.62) < 0.05  # textbook value for 50 of 100
    lo, hi = wilson(0, 20)
    assert lo == 0 and 15 < hi < 17.5


def test_opponent_adjustment_on_a_made_up_schedule():
    """One game against a defense whose other games allow exactly the passer's own line: over expected is zero."""
    G = pd.DataFrame([dict(player="QB", season=2030, Date="09/01/30", Opponent="@ 5 Team A", Att=30, Comp=20, Yards=240, TD=2, Int=1),
                      dict(player="QB", season=2030, Date="09/08/30", Opponent="FCS State", Att=20, Comp=18, Yards=300, TD=4, Int=0)])
    T = pd.DataFrame([dict(Name="Team A", season=2030, Att=330, Comp=220, Yards=2640, TD=22, Int=11)])
    out = opp_adjusted(G, T, "QB", 2030)
    assert out["games"] == 1 and out["att"] == 30          # the game against a team outside the table is dropped
    assert abs(out["over"]) < 1e-9
    T.loc[0, ["Comp", "Yards", "TD"]] = [170, 1840, 12]     # a tougher defense in its other games
    assert opp_adjusted(G, T, "QB", 2030)["over"] > 0


def test_draft_outcomes_match_known_picks():
    D, *_ = load()
    D = with_outcomes(D)
    row = lambda n, y: D[(D.Name == n) & (D.season == y)].iloc[0]  # noqa: E731
    assert row("Cam Ward", 2024).outcome == "round 1, pick 1 (2025)"
    assert row("Kyle Trask", 2020).outcome == "round 2, pick 64 (2021)"
    assert row(ME, 2025).outcome == f"in college in {SEASON}"
    assert len(pd.read_csv(DATA / "qb_draft_picks_2021_2026.csv")) == 68


def test_findings_are_internally_consistent():
    f = json.loads((R / "findings.json").read_text())
    o = f["opp"]
    assert [c["name"] for c in o["cls"]] == CLASS
    assert o["class_rank"] == 1 + sum(c["over"] > o["cls"][0]["over"] for c in o["cls"])
    assert len(o["first_round"]) == 18 and abs(o["fr_median"] - np.median([x["over"] for x in o["first_round"]])) < 1e-9
    assert sum(b["n"] for b in f["base_rate"]) == f["base_rate_n"] and sum(b["his_band"] for b in f["base_rate"]) == 1
    iv = f["intervals"]
    assert iv["x25_lo"] < f["line"]["x25"] < iv["x25_hi"] and iv["int_lo"] < f["line"]["INTp"] < iv["int_hi"]
    assert f["same_games"]["games"] == f["line"]["G"] and len(f["same_games"]["rows"]) == 18
    assert f["move_fbs"]["n"] == 20


def test_readme_matches_findings():
    f = json.loads((R / "findings.json").read_text())
    text = (R / "README.md").read_text()
    for s in SECTIONS:
        assert s in text, s
    L, o = f["line"], f["opp"]
    assert f"{L['Comp']}-of-{L['Att']}, {L['Yards']:,} yards, {L['TD']} TD, {L['Int']} INT" in text
    assert f"#{o['class_rank']} of {o['class_n']} in this class" in text and f"{o['cls'][0]['over']:+.1f}" in text
    for png in FIGS:
        assert f"{png}.png" in text and (R / f"{png}.png").exists()
    assert pd.read_csv(R / "class_table.csv").Name.iloc[0] == ME
