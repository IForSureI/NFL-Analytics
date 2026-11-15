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


def boot_r(x, y, groups=None, n: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Pearson r with a 95% bootstrap interval. With groups, whole groups are resampled together
    (use the team or crew, so repeat seasons from one club are not counted as independent)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    rng = np.random.default_rng(seed)
    r = float(np.corrcoef(x, y)[0, 1])
    if groups is None:
        idx = [rng.integers(0, len(x), len(x)) for _ in range(n)]
    else:
        g = pd.Series(np.arange(len(x))).groupby(np.asarray(groups)).apply(lambda s: s.to_numpy())
        members = list(g.values)
        idx = [np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))]) for _ in range(n)]
    rs = [np.corrcoef(x[i], y[i])[0, 1] for i in idx]
    lo, hi = np.nanpercentile(rs, [2.5, 97.5])
    return r, float(lo), float(hi)


def boot_ratio(num, den, n: int = 2000, seed: int = 7, scale: float = 1.0) -> tuple[float, float, float]:
    """sum(num) / sum(den) with a 95% interval from resampling rows (one row per game)."""
    num = np.asarray(num, float); den = np.asarray(den, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(num), (n, len(num)))
    b = scale * num[idx].sum(1) / den[idx].sum(1)
    lo, hi = np.percentile(b, [2.5, 97.5])
    return float(scale * num.sum() / den.sum()), float(lo), float(hi)
