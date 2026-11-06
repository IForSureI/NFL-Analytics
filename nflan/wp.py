"""A transparent win-probability model trained on nflverse play-by-play.

Gradient-boosted trees (scikit-learn HistGradientBoostingClassifier) on the same inputs
public WP models use: score, clock, field position, down and distance, timeouts, who gets
the second-half kickoff, and the pregame point spread. The point is not to beat nflfastR's
model; it is to own a model we can query for any hypothetical state (the 4th-down bot needs that).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

# Game-state inputs every caller must supply.
FEATURES = ["score_differential", "game_seconds_remaining", "half_seconds_remaining", "yardline_100",
            "down", "ydstogo", "posteam_timeouts_remaining", "defteam_timeouts_remaining",
            "receive_2h_ko", "posteam_spread", "is_second_half"]
# What the trees actually see. Like nflfastR's model, the pregame spread fades as the clock runs
# (spread_time) and a lead matters more as time runs out (diff_time_ratio).
MODEL_FEATURES = ["score_differential", "game_seconds_remaining", "half_seconds_remaining", "yardline_100",
                  "down", "ydstogo", "posteam_timeouts_remaining", "defteam_timeouts_remaining",
                  "receive_2h_ko", "spread_time", "diff_time_ratio", "is_second_half"]
# Monotone where football logic is: more points ahead -> higher WP,
# farther from the end zone -> lower WP, bigger favorite -> higher WP.
MONOTONE = {"score_differential": 1, "yardline_100": -1, "spread_time": 1, "diff_time_ratio": 1, "ydstogo": -1}


def derive(states: pd.DataFrame) -> pd.DataFrame:
    elapsed = 1 - states["game_seconds_remaining"].astype(float) / 3600.0
    X = states[[f for f in MODEL_FEATURES if f in states.columns]].copy()
    X["spread_time"] = states["posteam_spread"] * np.exp(-4 * elapsed)
    X["diff_time_ratio"] = states["score_differential"] * np.exp(4 * elapsed)
    return X[MODEL_FEATURES]

PBP_COLUMNS = ["game_id", "season", "season_type", "posteam", "defteam", "home_team", "away_team", "qtr",
               "score_differential", "game_seconds_remaining", "half_seconds_remaining", "yardline_100",
               "down", "ydstogo", "posteam_timeouts_remaining", "defteam_timeouts_remaining",
               "home_opening_kickoff", "spread_line", "result", "play_type", "wp", "vegas_wp"]


def add_features(pbp: pd.DataFrame) -> pd.DataFrame:
    df = pbp.copy()
    home_has_ball = df["posteam"] == df["home_team"]
    df["posteam_spread"] = np.where(home_has_ball, df["spread_line"], -df["spread_line"])
    home_got_opening = df["home_opening_kickoff"] == 1
    # The team that did NOT receive the opening kickoff receives the second-half kickoff.
    posteam_got_opening = np.where(home_has_ball, home_got_opening, ~home_got_opening)
    df["receive_2h_ko"] = ((df["qtr"] <= 2) & ~posteam_got_opening.astype(bool)).astype(int)
    df["is_second_half"] = (df["qtr"] >= 3).astype(int)
    return df


def labels(df: pd.DataFrame) -> pd.Series:
    """1 if the team with the ball won; ties are dropped by the caller."""
    home_won = df["result"] > 0
    return np.where(df["posteam"] == df["home_team"], home_won, ~home_won).astype(int)


def training_frame(pbp: pd.DataFrame) -> pd.DataFrame:
    df = add_features(pbp)
    m = (df["play_type"].isin(["run", "pass", "punt", "field_goal", "no_play"]) & df["down"].notna()
         & df["posteam"].notna() & (df["result"] != 0) & df["spread_line"].notna() & (df["qtr"] <= 4))
    df = df.loc[m, FEATURES + ["game_id", "season", "posteam", "home_team", "result", "wp", "vegas_wp"]].dropna(subset=FEATURES)
    df["y"] = labels(df)
    return df


@dataclass
class WPModel:
    model: HistGradientBoostingClassifier

    @classmethod
    def fit(cls, train: pd.DataFrame, seed: int = 7) -> "WPModel":
        cst = [MONOTONE.get(f, 0) for f in MODEL_FEATURES]
        clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, max_leaf_nodes=48,
                                             min_samples_leaf=200, l2_regularization=1.0,
                                             monotonic_cst=cst, random_state=seed)
        clf.fit(derive(train), train["y"])
        return cls(clf)

    def predict(self, states: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(derive(states))[:, 1]


def brier(p, y) -> float:
    p = np.asarray(p, float); y = np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def calibration_table(p, y, bins: int = 20) -> pd.DataFrame:
    df = pd.DataFrame({"p": p, "y": y})
    df["bin"] = pd.cut(df["p"], np.linspace(0, 1, bins + 1), include_lowest=True)
    return df.groupby("bin", observed=True).agg(pred=("p", "mean"), actual=("y", "mean"), n=("y", "size")).reset_index()
