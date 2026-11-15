"""Held-out tests for the fourth-down bot's component models.

Fit on earlier seasons, score on later seasons the fit never saw, compare with a simple baseline, and put an
interval on every score by resampling whole games. Nothing here knows about football beyond the word "season".
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def split_seasons(df: pd.DataFrame, train_last: int):
    """(training rows, test rows): seasons through `train_last`, and every season after it."""
    return df[df["season"] <= train_last], df[df["season"] > train_last]


def brier_rows(p, y) -> np.ndarray:
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def log_loss_rows(p, y, eps: float = 1e-6) -> np.ndarray:
    """Log loss per row. Probabilities are clipped so a confident miss is large, not infinite."""
    p = np.clip(np.asarray(p, float), eps, 1 - eps); y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def bin_rate(x_train, y_train, edges):
    """A lookup-table baseline: the training mean of y in each bin of x. Returns a function of new x.
    A bin with no training rows (or an x outside the edges) gets the overall training mean."""
    x_train = np.asarray(x_train, float); y_train = np.asarray(y_train, float)
    overall = float(y_train.mean())
    t = pd.Series(y_train).groupby(pd.cut(x_train, edges), observed=True).mean()

    def predict(x):
        b = pd.cut(np.asarray(x, float), edges)
        return pd.Series(b).map(t).astype(float).fillna(overall).to_numpy()
    return predict


def paired_scores(losses: dict, groups, n: int = 2000, seed: int = 7, root: bool = False) -> dict:
    """Mean loss for each entry of `losses` (per-row arrays, the model first), each as [point, low, high], plus
    "model_minus_<name>" for every other entry. Intervals are 95%, from resampling whole groups (games), and the
    same resampled games score the model and the baseline, so the difference is paired.
    root=True reports the square root of the mean (RMSE from squared errors)."""
    names = list(losses)
    L = np.column_stack([np.asarray(losses[k], float) for k in names])
    codes = pd.factorize(np.asarray(groups))[0]
    G = int(codes.max()) + 1
    sums = np.zeros((G, L.shape[1])); np.add.at(sums, codes, L)
    cnt = np.bincount(codes, minlength=G).astype(float)
    idx = np.random.default_rng(seed).integers(0, G, (n, G))
    bs = sums[idx].sum(axis=1) / cnt[idx].sum(axis=1)[:, None]
    pt = L.mean(axis=0)
    if root:
        bs, pt = np.sqrt(bs), np.sqrt(pt)

    def tri(point, draws):
        lo, hi = np.percentile(draws, [2.5, 97.5])
        return [float(point), float(lo), float(hi)]
    out = {k: tri(pt[i], bs[:, i]) for i, k in enumerate(names)}
    for i, k in enumerate(names[1:], start=1):
        out[f"{names[0]}_minus_{k}"] = tri(pt[0] - pt[i], bs[:, 0] - bs[:, i])
    return out


def beats(diff) -> str:
    """Read a paired difference [point, low, high] where lower is better: 'better', 'worse' or 'tie'."""
    return "better" if diff[2] < 0 else "worse" if diff[1] > 0 else "tie"


def calibration_by(x, pred, actual, edges) -> pd.DataFrame:
    """Predicted against actual by bin of x, with counts. Empty bins are left out."""
    d = pd.DataFrame({"x": np.asarray(x, float), "pred": np.asarray(pred, float), "actual": np.asarray(actual, float)})
    d["bin"] = pd.cut(d["x"], edges, include_lowest=True)
    t = d.groupby("bin", observed=True).agg(pred=("pred", "mean"), actual=("actual", "mean"), n=("actual", "size")).reset_index()
    t["bin"] = t["bin"].astype(str)
    return t


def flip_share(rec_a, rec_b, groups, n: int = 2000, seed: int = 7) -> list:
    """Share of rows where two sets of recommendations differ: [point, low, high], 95% from resampling games."""
    flip = (np.asarray(rec_a) != np.asarray(rec_b)).astype(float)
    return paired_scores({"flip": flip}, groups, n=n, seed=seed)["flip"]


def headline_moves(rates: dict, card: pd.DataFrame, min_card_r: float = 0.9) -> list:
    """The rule, set before looking, for whether refitting on the training seasons moves the headline numbers.

    rates: {season: (production rate, low, high, held-out rate)}; a season counts when the held-out go rate falls
    outside the production rate's 95% interval.
    card: one row per team with wp_lost_per_game, ci_low, ci_high (production) and held_out; a team counts when its
    held-out value falls outside its production 90% interval, and the card counts when the two versions correlate
    below `min_card_r` across teams.
    Returns the list of reasons; an empty list means the headline numbers did not move materially."""
    why = [f"go rate {s}" for s, (_, lo, hi, held) in rates.items() if not (lo <= held <= hi)]
    out = card[(card["held_out"] < card["ci_low"]) | (card["held_out"] > card["ci_high"])]
    why += [f"team card {t}" for t in out["posteam"]]
    r = float(np.corrcoef(card["wp_lost_per_game"], card["held_out"])[0, 1]) if len(card) > 2 else 1.0
    if r < min_card_r:
        why.append(f"team card r {r:.2f}")
    return why
