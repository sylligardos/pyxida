"""Candidate-set selection, shared by step 4 and the demo page.

Kept free of any project imports so both the batch script and Streamlit can use
it without the two `utils` modules (divergence/utils.py and app/utils.py)
shadowing each other on sys.path.

The five candidates, per (series, k, VUS buffer):

    best                the highest-VUS genuine combination -- an oracle
    top_k               the k detectors with the highest solo VUS
    least_corr          lowest mean pairwise Spearman, over all combinations
    least_corr_top10    the same, restricted to the 10 best solo detectors
    max_coverage        greedy on per-anomaly detection density
"""

import itertools

import numpy as np

HEURISTICS = ["best", "top_k", "least_corr", "least_corr_top10", "max_coverage"]
TOP_POOL = 10


def rho_matrix(pairs, detectors: list[str]) -> np.ndarray:
    """Symmetric Spearman matrix for one series, NaN where undefined.

    NaN means one of the two scores was constant, so the correlation does not
    exist. Those pairs must never read as "perfectly diverse".
    """
    index = {d: i for i, d in enumerate(detectors)}
    n = len(detectors)
    matrix = np.full((n, n), np.nan, dtype=np.float64)
    for a, b, rho in zip(pairs.detector_a, pairs.detector_b, pairs.spearman):
        ia, ib = index.get(a), index.get(b)
        if ia is not None and ib is not None:
            matrix[ia, ib] = matrix[ib, ia] = rho
    np.fill_diagonal(matrix, 1.0)
    return matrix


def mean_pairwise_rho(matrix: np.ndarray, combos: np.ndarray) -> np.ndarray:
    """Mean off-diagonal rho per combination.

    A combination containing an undefined pair gets +inf so it is never picked
    as least correlated -- undefined is not the same as uncorrelated.
    """
    k = combos.shape[1]
    if k < 2:
        return np.zeros(len(combos))
    stacked = np.stack([matrix[combos[:, i], combos[:, j]]
                        for i, j in itertools.combinations(range(k), 2)])
    # Plain mean, not nanmean: any undefined pair must poison the whole
    # combination rather than be averaged around.
    out = stacked.mean(axis=0)
    out[np.isnan(stacked).any(axis=0)] = np.inf
    return out


def greedy_coverage(density: np.ndarray, k: int) -> tuple[int, ...]:
    """Greedy max-coverage over detectors.

    coverage(S) = mean over anomalies of the best density in S is monotone
    submodular, so greedy carries the usual 1 - 1/e guarantee.
    """
    n_anomalies = density.shape[0]
    chosen: list[int] = []
    running = np.zeros(n_anomalies)
    for _ in range(k):
        gains = np.maximum(density, running[:, None]).mean(axis=0)
        gains[chosen] = -np.inf
        pick = int(np.argmax(gains))
        chosen.append(pick)
        running = np.maximum(running, density[:, pick])
    return tuple(sorted(chosen))


def combo_lookup(combos: np.ndarray) -> dict[tuple[int, ...], int]:
    """Map a sorted detector tuple to its row. Build once per (series, k).

    Hoisted out of pick_sets because it is buffer independent, and rebuilding a
    4,060 entry dict for each of 257 buffers dominated everything else.
    """
    return {tuple(sorted(c)): i for i, c in enumerate(combos)}


def pick_sets(combos: np.ndarray, vus: np.ndarray, genuine: np.ndarray,
              solo_vus: np.ndarray, rho: np.ndarray,
              coverage_set: tuple[int, ...] | None,
              lookup: dict[tuple[int, ...], int] | None = None) -> dict[str, int | None]:
    """Row index into `combos` for each heuristic, at one buffer.

    Args:
        combos: (n_combos, k) detector indices.
        vus: (n_combos,) VUS of each combination at this buffer.
        genuine: (n_combos,) True where no member had a constant score.
        solo_vus: (n_detectors,) solo VUS at this buffer, -inf if absent.
        rho: (n_combos,) mean pairwise Spearman, +inf where undefined.
        coverage_set: greedy max-coverage set, or None.

    `best` searches genuine combinations only. A constant score shifts an
    average uniformly and so cannot change the ranking, meaning such a
    combination scores exactly what its non-constant members score alone --
    left in, argmax reports a "pair" that is really a singleton. Heuristics
    keep the full pool: one of them picking a degenerate set is a real property
    of that heuristic, not an artefact.
    """
    k = combos.shape[1]
    if lookup is None:
        lookup = combo_lookup(combos)
    picks: dict[str, int | None] = {}

    picks["best"] = (int(np.flatnonzero(genuine)[np.argmax(vus[genuine])])
                     if genuine.any() else None)

    ranking = np.argsort(-solo_vus, kind="stable")
    picks["top_k"] = lookup.get(tuple(sorted(ranking[:k].tolist())))
    picks["least_corr"] = int(np.argmin(rho)) if np.isfinite(rho).any() else None

    # Membership by boolean mask rather than a set comprehension over every
    # combination: this runs once per buffer, so a Python loop over 4,060
    # combinations here is what made sweeping all 257 buffers impossible.
    pool = np.zeros(len(solo_vus), dtype=bool)
    pool[ranking[:TOP_POOL]] = True
    in_pool = pool[combos].all(axis=1)
    masked = np.where(in_pool, rho, np.inf)
    picks["least_corr_top10"] = (int(np.argmin(masked))
                                 if np.isfinite(masked).any() else None)

    picks["max_coverage"] = lookup.get(coverage_set) if coverage_set else None
    return picks
