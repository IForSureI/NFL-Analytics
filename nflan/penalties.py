"""Penalty helpers: accepted flags and the objective/subjective split.

Objective flags are called on a fact the official sees at the snap (alignment, motion,
the clock). Subjective flags need a judgment about contact or intent. The split follows
the logic MacKelvie uses ("We looked at 92,255 flags", 2026).
"""
from __future__ import annotations

import pandas as pd

OBJECTIVE = {
    "False Start", "Defensive Offside", "Neutral Zone Infraction", "Encroachment",
    "Offensive Offside", "Delay of Game", "Illegal Formation", "Illegal Shift",
    "Illegal Motion", "Illegal Substitution", "Too Many Men on Field",
    "Defensive Too Many Men on Field", "Offensive Too Many Men on Field",
    "Ineligible Downfield Pass", "Illegal Forward Pass", "Ineligible Downfield Kick",
    "Defensive Delay of Game", "Illegal Touch Pass", "Illegal Touch Kick",
    "Offside on Free Kick", "Kickoff Out of Bounds", "Illegal Kickoff Formation",
}
SUBJECTIVE = {
    "Offensive Holding", "Defensive Holding", "Defensive Pass Interference",
    "Offensive Pass Interference", "Roughing the Passer", "Unnecessary Roughness",
    "Illegal Contact", "Illegal Use of Hands", "Face Mask", "Unsportsmanlike Conduct",
    "Illegal Block Above the Waist", "Taunting", "Horse Collar Tackle", "Clipping",
    "Chop Block", "Low Block", "Roughing the Kicker", "Running Into the Kicker",
    "Tripping", "Illegal Blindside Block", "Lowering the Head to Initiate Contact",
    "Personal Foul", "Intentional Grounding", "Illegal Crackback", "Lowering the Head to Make Forcible Contact",
    "Disqualification", "Fair Catch Interference", "Defensive Holding ",
}


def accepted_flags(pbp: pd.DataFrame) -> pd.DataFrame:
    """Rows where a flag was thrown and enforced (declined and offsetting removed)."""
    m = (pbp["penalty"] == 1) & pbp["penalty_type"].notna() & pbp["penalty_team"].notna()
    desc = pbp["desc"].fillna("")
    m &= ~desc.str.contains("declined", case=False) & ~desc.str.contains("offsetting", case=False)
    out = pbp.loc[m].copy()
    out["flag_kind"] = classify(out["penalty_type"])
    out["on_offense"] = out["penalty_team"] == out["posteam"]
    return out


def classify(types: pd.Series) -> pd.Series:
    return types.map(lambda t: "objective" if t in OBJECTIVE else ("subjective" if t in SUBJECTIVE else "other"))
