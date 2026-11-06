"""Fourth-down decision bot: expected win probability of going, kicking a field goal, or punting.

Built in the spirit of Ben Baldwin's nfl4th, but simplified and fully in Python:
  WP(go)   = P(convert) * E[WP | converted] + (1 - P(convert)) * WP(opponent ball at the spot)
  WP(fg)   = P(make)    * WP(+3, opponent receives kickoff) + (1 - P(make)) * WP(opponent ball at spot of kick)
  WP(punt) = WP(opponent ball at the expected net-punt spot)
Every component is an empirical model fit on the same play-by-play. Simplifications are listed
in reports/02-fourth-down-bot/README.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression

from .wp import WPModel, FEATURES

PLAY_SECONDS = {"go": 6, "fg": 5, "punt": 8}


def _flip(state: pd.DataFrame, new_yardline_100, points_scored, seconds_used) -> pd.DataFrame:
    """State for the OTHER team, first-and-ten, after we score `points_scored`."""
    s = state.copy()
    s["score_differential"] = -(state["score_differential"] + points_scored)
    s["yardline_100"] = np.clip(new_yardline_100, 1, 99)
    s["down"] = 1
    s["ydstogo"] = np.minimum(10, s["yardline_100"])
    s["posteam_timeouts_remaining"], s["defteam_timeouts_remaining"] = (
        state["defteam_timeouts_remaining"].values, state["posteam_timeouts_remaining"].values)
    s["posteam_spread"] = -state["posteam_spread"]
    # the team now receiving the 2nd-half kickoff is the one that did NOT have it
    s["receive_2h_ko"] = np.where(state["is_second_half"] == 1, 0, 1 - state["receive_2h_ko"])
    s = _tick(s, seconds_used)
    return s


def _tick(s: pd.DataFrame, seconds) -> pd.DataFrame:
    s = s.copy()
    s["game_seconds_remaining"] = np.maximum(s["game_seconds_remaining"] - seconds, 0)
    s["half_seconds_remaining"] = np.maximum(s["half_seconds_remaining"] - seconds, 0)
    return s


@dataclass
class FourthDownBot:
    wp: WPModel
    convert: HistGradientBoostingClassifier
    fg: LogisticRegression
    punt_net: HistGradientBoostingRegressor
    gain_given_convert: pd.DataFrame   # extra yards beyond the line to gain, by distance bucket
    kickoff_start: float               # opponent yardline_100 after our score (season-specific)

    # ---------- fitting ----------
    @staticmethod
    def fit_convert(plays: pd.DataFrame):
        """P(gain >= ydstogo) on 3rd/4th-down runs and passes (kneels and spikes excluded)."""
        d = plays[plays["down"].isin([3, 4]) & plays["play_type"].isin(["run", "pass"])].copy()
        d = d.dropna(subset=["ydstogo", "yardline_100", "yards_gained"])
        d["is4"] = (d["down"] == 4).astype(int)
        y = (d["yards_gained"] >= d["ydstogo"]) | (d["touchdown"] == 1) & (d["td_team"] == d["posteam"])
        X = d[["ydstogo", "yardline_100", "is4"]]
        clf = HistGradientBoostingClassifier(max_iter=200, monotonic_cst=[-1, 0, 0], min_samples_leaf=300, random_state=7)
        clf.fit(X, y.astype(int))
        # extra yards beyond the sticks on successful plays (median, by distance bucket)
        succ = d[y & (d["yards_gained"] >= d["ydstogo"])]
        succ = succ.assign(extra=(succ["yards_gained"] - succ["ydstogo"]).clip(0, 40),
                           bucket=pd.cut(succ["ydstogo"], [0, 1, 2, 4, 7, 10, 99]))
        gain = succ.groupby("bucket", observed=True)["extra"].median().rename("extra").reset_index()
        return clf, gain

    @staticmethod
    def fit_fg(plays: pd.DataFrame) -> LogisticRegression:
        k = plays[(plays["field_goal_attempt"] == 1) & plays["kick_distance"].notna()].copy()
        k["made"] = (k["field_goal_result"] == "made").astype(int)
        k["indoor"] = k["roof"].isin(["dome", "closed"]).astype(int)
        X = np.column_stack([k["kick_distance"], k["kick_distance"] ** 2, k["indoor"], k["season"] - 2015])
        return LogisticRegression(max_iter=2000).fit(X, k["made"])

    @staticmethod
    def fit_punt(plays: pd.DataFrame, pbp: pd.DataFrame) -> HistGradientBoostingRegressor:
        """Opponent's next-drive starting yardline_100 (from their perspective) after a punt."""
        p = plays[(plays["punt_attempt"] == 1) & (plays["play_type"] == "punt")][["game_id", "play_id", "yardline_100", "posteam"]]
        nxt = pbp[["game_id", "play_id", "posteam", "yardline_100", "play_type"]].copy()
        nxt = nxt[nxt["play_type"].isin(["run", "pass", "field_goal", "punt", "no_play"])]
        m = pd.merge_asof(p.sort_values("play_id"), nxt.sort_values("play_id").rename(
            columns={"posteam": "next_team", "yardline_100": "next_yl", "play_type": "next_type"}),
            on="play_id", by="game_id", direction="forward", allow_exact_matches=False)
        m = m[(m["next_team"] != m["posteam"]) & m["next_yl"].notna()]
        reg = HistGradientBoostingRegressor(max_iter=150, monotonic_cst=[1], random_state=7)
        reg.fit(m[["yardline_100"]], m["next_yl"])
        return reg

    # ---------- decisions ----------
    def _wp_after_convert(self, s: pd.DataFrame) -> np.ndarray:
        b = pd.cut(s["ydstogo"], [0, 1, 2, 4, 7, 10, 99])
        extra = b.map(dict(zip(self.gain_given_convert["bucket"], self.gain_given_convert["extra"]))).astype(float).fillna(1.0)
        new_yl = s["yardline_100"] - s["ydstogo"] - extra
        td = new_yl <= 0
        first = _tick(s, PLAY_SECONDS["go"]).assign(yardline_100=np.clip(new_yl, 1, 99), down=1)
        first["ydstogo"] = np.minimum(10, first["yardline_100"])
        wp_first = self.wp.predict(first)
        wp_td = 1 - self.wp.predict(_flip(s, self.kickoff_start, 7, PLAY_SECONDS["go"]))
        return np.where(td, wp_td, wp_first)

    def evaluate(self, s: pd.DataFrame) -> pd.DataFrame:
        """s: 4th-down states with the WP FEATURES plus 'roof_indoor' and 'season'. Returns WP by option."""
        s = s.reset_index(drop=True)
        X = s[["ydstogo", "yardline_100"]].assign(is4=1)
        p_conv = self.convert.predict_proba(X)[:, 1]
        wp_conv = self._wp_after_convert(s)
        wp_fail = 1 - self.wp.predict(_flip(s, 100 - s["yardline_100"], 0, PLAY_SECONDS["go"]))
        wp_go = p_conv * wp_conv + (1 - p_conv) * wp_fail

        dist = s["yardline_100"] + 18
        Xf = np.column_stack([dist, dist ** 2, s["roof_indoor"], s["season"] - 2015])
        p_make = np.where(dist <= 66, self.fg.predict_proba(Xf)[:, 1], 0.0)
        wp_make = 1 - self.wp.predict(_flip(s, self.kickoff_start, 3, PLAY_SECONDS["fg"]))
        miss_spot = 100 - np.maximum(s["yardline_100"] + 7, 20)
        wp_miss = 1 - self.wp.predict(_flip(s, miss_spot, 0, PLAY_SECONDS["fg"]))
        wp_fg = np.where(dist <= 66, p_make * wp_make + (1 - p_make) * wp_miss, np.nan)

        opp_yl = self.punt_net.predict(s[["yardline_100"]])
        wp_punt = np.where(s["yardline_100"] >= 35, 1 - self.wp.predict(_flip(s, opp_yl, 0, PLAY_SECONDS["punt"])), np.nan)

        out = pd.DataFrame({"p_convert": p_conv, "p_make": p_make, "wp_go": wp_go, "wp_fg": wp_fg, "wp_punt": wp_punt})
        kick = out[["wp_fg", "wp_punt"]].max(axis=1, skipna=True)
        out["best_kick"] = np.where(out["wp_fg"].fillna(-1) >= out["wp_punt"].fillna(-1), "fg", "punt")
        out["go_boost"] = 100 * (out["wp_go"] - kick)  # WP points gained by going vs the best kick
        out["rec"] = np.where(out["go_boost"] > 0, "go", out["best_kick"])
        return out
