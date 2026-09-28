"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Shared helpers for the divergence study.

Loading is done by TSBADParser. This module only adds the three things every
step of the divergence study needs on top of it:

  1. which detectors we use   -> get_detectors()
  2. the rank transform       -> rank_transform()
  3. all pairwise Spearman    -> spearman_matrix() / pairs_from_matrix()

Keeping them here means the rules are defined once, not re-guessed per script.
"""

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.ndimage import maximum_filter1d
from scipy.stats import rankdata

# Repo root: this file lives at src/divergence/utils.py
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tsbadparser import TSBADParser  # noqa: E402

DATA_ROOT = REPO_ROOT / "data"
OUT_ROOT = DATA_ROOT / "divergence"


# --------------------------------------------------------------------------
# Parser + detector roster
# --------------------------------------------------------------------------

def get_parser(kind: str = "uni") -> TSBADParser:
    return TSBADParser(path=str(DATA_ROOT), kind=kind)


# parser.get_detectors() returns 32 for uni. Two of them are unusable here
# because their score arrays do not reliably match the series length:
#   Lag_Llama  emits T-10 points on 45 series, and is missing on ~5% of them
#   SAND       is truncated on at least one series (500 points instead of 1000)
# Dropping them removes every length mismatch in the benchmark, and stops
# load_scores from discarding whole series over one bad detector.
UNRELIABLE_LENGTH = ["Lag_Llama", "SAND"]


def get_detectors(parser: TSBADParser) -> list[str]:
    """Detectors used by the divergence study: parser roster minus the two
    with unreliable score lengths. Returns 30 for kind='uni'."""
    return [d for d in parser.get_detectors() if d not in UNRELIABLE_LENGTH]


def list_series(parser: TSBADParser, dataset: Optional[str] = None) -> list[str]:
    """Raw CSV filenames, optionally filtered to one dataset, in series_id order."""
    meta = parser.meta
    if dataset is not None:
        meta = meta[meta.dataset == dataset]
        if meta.empty:
            raise ValueError(
                f"No series for dataset {dataset!r}. "
                f"Available: {', '.join(parser.get_datasets())}"
            )
    return meta.filename.tolist()


# --------------------------------------------------------------------------
# Temporal tolerance
# --------------------------------------------------------------------------
# Pointwise correlation calls a detector that fires 20 points early "wrong".
# That is the same problem range-precision and VUS were invented to solve, and
# TSB-AD already carries VUS-PR at L = 0, 1, 2, 4 ... 256 for exactly this
# reason. We apply the same idea to detector-vs-detector agreement: max-pool
# both score vectors over a window first, so "fired somewhere near here" counts
# as firing here, then rank and correlate.
#
# Max, not mean: a detector fires with a peak, and a detection anywhere inside
# the buffer is what VUS credits.
#
# Reading the result across windows is the useful part:
#   agreement RISES with the window -> both caught it, one was early or late
#   agreement FALLS with the window -> one of them genuinely never fired
WINDOWS = [1, 4, 16, 64, 128, 256]


def maxpool(scores: np.ndarray, window: int) -> np.ndarray:
    """Rolling max along time, centred, edges extended.

    Args:
        scores: (n_detectors, T) or (T,).
        window: tolerance in points. window <= 1 returns the input unchanged.
    """
    if window <= 1:
        return scores
    return maximum_filter1d(scores, size=window, axis=-1, mode="nearest")


# --------------------------------------------------------------------------
# Per-anomaly detection
# --------------------------------------------------------------------------
# Buffers we report detection at. Density is a ramp-weighted mean percentile
# over the dilated anomaly, so a wider window fills with normal points and
# pulls every detector towards 0.5. Measured on TSB-AD-U, values are flat from
# 0 to about 12 and have washed out by 64, so there is nothing above it worth
# storing.
BUFFERS = [0, 1, 2, 4, 8, 16, 32, 64]

# Height the buffer ramp falls to at its far edge, as in VUS. A flag right
# beside an anomaly is worth nearly a direct hit; one at the edge of the buffer
# is worth ZITA of it. Without the ramp, a flag 64 points away would count as
# much as a flag on the anomaly itself.
ZITA = 1.0 / np.sqrt(2.0)


def buffer_weights(
    labels: np.ndarray,
    buffers: list[int] = BUFFERS,
    zita: float = ZITA,
) -> np.ndarray:
    """Credit each timestamp earns for being near an anomaly, per buffer.

    Follows the VUS buffer: weight 1 inside the anomaly, then a linear ramp
    down to `zita` at distance `buffer`, and 0 beyond. Where two anomalies are
    close enough for their buffers to meet, each point is attributed to the
    nearer anomaly so a single flag is never credited twice.

    Depends only on the labels, so it is computed once per series and reused
    across every detector.

    Args:
        labels:  binary ground truth, shape (T,).
        buffers: slack sizes to build weights for.
        zita:    ramp height at the buffer edge, in [0, 1].

    Returns:
        (len(buffers), T) array of weights in [0, 1].
    """
    n_points = len(labels)
    starts, ends = anomaly_bounds(labels)
    weights = np.zeros((len(buffers), n_points))
    if len(starts) == 0:
        return weights

    left_limit = np.r_[0, (ends[:-1] + starts[1:]) // 2]
    right_limit = np.r_[(ends[:-1] + starts[1:]) // 2, n_points]

    for b_idx, buffer in enumerate(buffers):
        row = weights[b_idx]
        for k, (start, end) in enumerate(zip(starts, ends)):
            row[start:end] = 1.0
            if buffer <= 0:
                continue
            lo = max(start - buffer, left_limit[k])
            if lo < start:
                distance = start - np.arange(lo, start)
                row[lo:start] = 1.0 - (1.0 - zita) * distance / buffer
            hi = min(end + buffer, right_limit[k])
            if hi > end:
                distance = np.arange(end, hi) - end + 1
                row[end:hi] = 1.0 - (1.0 - zita) * distance / buffer
    return weights


def anomaly_bounds(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Start (inclusive) and end (exclusive) index of every labelled anomaly."""
    edges = np.flatnonzero(np.diff(np.r_[0, labels.astype(np.int8), 0]))
    return edges[::2], edges[1::2]


def detection_density(
    labels: np.ndarray,
    score: np.ndarray,
    buffers: list[int] = BUFFERS,
    weights: Optional[np.ndarray] = None,
) -> np.ndarray:
    """How strongly did this detector respond at each anomaly?

    Counts true positives the way VUS does, over every threshold and every
    buffer, rather than at one fixed threshold:

        density(a, b) = sum_i w_b(i) p(i) / sum_i w_b(i),  i in R(a, b)

    where p is the percentile rank of the score, w_b is the VUS ramp (see
    buffer_weights) and R(a, b) is the anomaly dilated by b, clipped at the
    midpoint to its neighbours.

    The percentile is not an approximation of the threshold sweep, it is the
    sweep. Averaging "is this point flagged at threshold t" over all thresholds
    gives exactly that point's percentile rank, so the sweep never has to run.

    The earlier version fixed one threshold, giving the detector a budget equal
    to the anomaly rate and counting how much of it landed on each anomaly.
    That is winner-take-all: on 772_YAHOO, MatrixProfile spent its whole
    12-point budget on two spikes and scored 0 on eleven anomalies where it sat
    at the 85th to 99th percentile and was plainly responding. Sweeping every
    threshold removes the cliff, and those eleven now score 0.75 to 0.99.

    Ranking is still what makes detectors comparable. Scores are min-max
    normalised to [0, 1], not z-normalised, so an absolute cut like
    `score >= 0.5` means "extremely confident" for one detector and "below
    average" for another.

    At buffer 0:

        perfect detector  -> ~1.0
        random score      -> ~0.5   (a percentile's expectation, not an anomaly
                                     rate; the floor is 0.5, not 0)
        constant score    ->  0.0
        inverted score    -> ~0.0

    Widening the buffer pulls every detector towards 0.5 as the window fills
    with normal points, so values are comparable across detectors at a fixed
    buffer and not across buffers. Past roughly 16 the measure stops
    discriminating; BUFFERS is capped accordingly.

    Args:
        labels:  binary ground truth, shape (T,).
        score:   detector scores, shape (T,).
        buffers: how many points of slack to allow either side of the anomaly.

    Returns:
        (n_anomalies, len(buffers)) array in [0, 1].
    """
    n_points = len(labels)
    starts, ends = anomaly_bounds(labels)
    if len(starts) == 0:
        return np.zeros((0, len(buffers)))

    # A constant score carries no information; it should never look like a
    # detection. Its percentiles would all be 0.5, i.e. exactly chance.
    if score.min() == score.max():
        return np.zeros((len(starts), len(buffers)))

    if weights is None:
        weights = buffer_weights(labels, buffers)

    percentile = rankdata(score, method="average") / n_points

    # Clipping each window at the midpoint to its neighbour stops one anomaly
    # from being credited with the detection meant for the next.
    left_limit = np.r_[0, (ends[:-1] + starts[1:]) // 2]
    right_limit = np.r_[(ends[:-1] + starts[1:]) // 2, n_points]

    out = np.zeros((len(starts), len(buffers)))
    for b_idx, buffer in enumerate(buffers):
        numerator = np.r_[0, np.cumsum(percentile * weights[b_idx])]
        denominator = np.r_[0, np.cumsum(weights[b_idx])]
        lo = np.maximum(starts - buffer, left_limit)
        hi = np.minimum(ends + buffer, right_limit)
        mass = denominator[hi] - denominator[lo]
        out[:, b_idx] = np.divide(numerator[hi] - numerator[lo], mass,
                                  out=np.zeros(len(starts)), where=mass > 0)
    return out


def detection_chance(
    labels: np.ndarray,
    buffers: list[int] = BUFFERS,
    weights: Optional[np.ndarray] = None,
) -> np.ndarray:
    """What detection_density a random detector would score, per anomaly.

    Density is a weighted mean of percentile ranks, and a random score's ranks
    are a uniform permutation, so every point has expectation 0.5 whatever the
    weights are. Chance is therefore 0.5 at every anomaly and every buffer.

    That is a constant rather than a computed baseline, so it is not something
    to divide by; it is the line the numbers should be read against. The
    previous measure counted flags at one threshold, giving a chance that
    depended on the anomaly rate and grew with the buffer, which is why this
    used to be worth computing per anomaly.

    Returns:
        (n_anomalies, len(buffers)) array, every entry 0.5.
    """
    starts, _ = anomaly_bounds(labels)
    return np.full((len(starts), len(buffers)), 0.5)


# --------------------------------------------------------------------------
# Rank transform + Spearman
# --------------------------------------------------------------------------

def rank_transform(scores: np.ndarray) -> np.ndarray:
    """Rank-transform each row independently, ties averaged.

    Detector scores are min-max normalised to [0, 1], not z-normalised, so
    their scales are not comparable: on one series the means range from 0.01
    to 0.66. Ranking asks the question we actually mean -- do two detectors
    order the timestamps the same way -- and the scale drops out.

    Ties matter. Every detector emits a constant plateau at the start of a
    series (window padding), sometimes hundreds of points long. method
    'average' is what scipy.stats.spearmanr uses, so the fast path below and
    the reference implementation agree.

    Args:
        scores: array of shape (n_detectors, T).

    Returns:
        Array of shape (n_detectors, T) holding average ranks.
    """
    return np.stack([rankdata(row, method="average") for row in scores])


def spearman_matrix(scores: np.ndarray) -> np.ndarray:
    """All pairwise Spearman correlations for one series, in one shot.

    Ranks once, standardises, then a single matrix multiply produces every
    pair. Same answer as calling scipy.stats.spearmanr on each pair, without
    re-sorting the arrays once per pair.

    A detector with a constant score vector (POLY is all-zero on some series)
    has zero variance, so its correlations are undefined. Those come back as
    NaN, never 0 -- "no answer" and "no agreement" are different facts.

    Args:
        scores: array of shape (n_detectors, T).

    Returns:
        (n_detectors, n_detectors) correlation matrix, NaN where undefined.
    """
    ranks = rank_transform(scores)
    centred = ranks - ranks.mean(axis=1, keepdims=True)
    sd = centred.std(axis=1, keepdims=True)
    sd[sd == 0] = np.nan
    z = centred / sd
    corr = (z @ z.T) / ranks.shape[1]
    return np.clip(corr, -1.0, 1.0)


def pairs_from_matrix(corr: np.ndarray, detectors: list[str]) -> pd.DataFrame:
    """Flatten the upper triangle of a correlation matrix into long rows.

    Detectors are sorted, so detector_a < detector_b always holds and a pair
    has exactly one representation in the output.

    Returns:
        DataFrame with columns detector_a, detector_b, spearman.
    """
    i, j = np.triu_indices(len(detectors), k=1)
    return pd.DataFrame(
        {
            "detector_a": [detectors[a] for a in i],
            "detector_b": [detectors[b] for b in j],
            "spearman": corr[i, j],
        }
    )
