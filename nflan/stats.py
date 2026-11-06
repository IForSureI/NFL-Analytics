"""Small statistics helpers used across projects."""
from __future__ import annotations

import numpy as np
import pandas as pd


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial rate k/n."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z ** 2 / n
    mid = (p + z ** 2 / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / den
    return (mid - half, mid + half)


def shrink_rate(k: pd.Series, n: pd.Series) -> pd.Series:
    """Empirical-Bayes (beta-binomial, method of moments) shrinkage of k/n toward the pooled rate."""
    k = k.astype(float); n = n.astype(float)
    p = k / n
    mu = k.sum() / n.sum()
    var_obs = np.average((p - mu) ** 2, weights=n)
    var_noise = np.average(mu * (1 - mu) / n, weights=n)
    var_true = max(var_obs - var_noise, 1e-12)
    m = mu * (1 - mu) / var_true - 1  # prior strength in pseudo-trials
    m = max(m, 0)
    return (k + m * mu) / (n + m)


def split_half_r(team_games: pd.DataFrame, col: str) -> float:
    """Correlate a team's odd-week mean with its even-week mean, within season (regular season)."""
    g = team_games.groupby(["season", "team", "odd"])[col].mean().unstack("odd").dropna()
    return float(g[0].corr(g[1]))


def pythag_wins(pf, pa, games, exp: float = 2.37):
    pf = np.asarray(pf, float); pa = np.asarray(pa, float)
    return games * pf ** exp / (pf ** exp + pa ** exp)
