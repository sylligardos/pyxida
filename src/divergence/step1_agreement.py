"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Step 1 of the divergence study -- the agreement table.

For every pair of detectors, on every series: the Spearman correlation of
their score vectors. That is the table everything downstream queries.

Run:
    python src/divergence/step1_agreement.py                    # all of TSB-AD-U
    python src/divergence/step1_agreement.py --dataset NAB      # one dataset
    python src/divergence/step1_agreement.py --test             # verify first

Why Spearman and not Euclidean: detector scores are min-max normalised to
[0, 1], not z-normalised, so one spike sets the scale and the distributions
are not comparable. Euclidean distance would measure whether two detectors
have a similar score distribution -- it calls POLY/SR the most equivalent
pair on a series where they agree on nothing (rho = -0.04). Spearman asks
whether they order the timestamps the same way, which is what we mean.
"""

import argparse
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from tqdm import tqdm

from utils import (
    OUT_ROOT,
    WINDOWS,
    get_detectors,
    get_parser,
    list_series,
    maxpool,
    pairs_from_matrix,
    spearman_matrix,
)

# How many series to load per parser call. Bounds peak memory and amortises
# the cost of spawning the multiprocessing pool.
CHUNK_SIZE = 40


def iter_score_chunks(parser, filenames, detectors, chunk_size=CHUNK_SIZE, njobs=None):
    """Yield (filename, score_matrix) pairs, loading in chunks.

    Series missing a score for any detector are dropped by the parser; they
    are reported by the caller, not silently skipped.
    """
    for start in range(0, len(filenames), chunk_size):
        chunk = filenames[start : start + chunk_size]
        kept, scores, _ = parser.load_scores(
            detectors=detectors,
            filenames=chunk,
            njobs=njobs,
            drop_missing=True,
            return_filenames=True,
        )
        for fname, score_matrix in zip(kept, scores):
            yield fname, score_matrix


def build_agreement_table(parser, filenames, detectors, njobs=None):
    """Compute all pairwise Spearman correlations for every series and window.

    One column per tolerance window: w1 is pointwise, w256 credits a detector
    that fires anywhere within 256 points. Comparing the columns separates a
    timing offset (agreement rises with the window) from a real miss
    (agreement falls).

    Returns:
        (table, dropped) where table has one row per (series, detector pair),
        and dropped lists the series the parser could not return complete
        scores for.
    """
    meta = parser.meta.set_index("filename")["dataset"].to_dict()
    frames = []
    seen = []

    stream = iter_score_chunks(parser, filenames, detectors, njobs=njobs)
    for fname, score_matrix in tqdm(stream, total=len(filenames), desc="Series"):
        rows = None
        for window in WINDOWS:
            corr = spearman_matrix(maxpool(score_matrix, window))
            pairs = pairs_from_matrix(corr, detectors)
            if rows is None:
                rows = pairs.rename(columns={"spearman": f"w{window}"})
            else:
                rows[f"w{window}"] = pairs["spearman"].values
        rows["filename"] = fname
        rows["dataset"] = meta.get(fname, "Unknown")
        rows["n_points"] = score_matrix.shape[1]
        frames.append(rows)
        seen.append(fname)

    dropped = [f for f in filenames if f not in set(seen)]
    if not frames:
        return pd.DataFrame(), dropped

    table = pd.concat(frames, ignore_index=True)
    # `spearman` stays as an alias for the pointwise column so anything already
    # reading it keeps working.
    table["spearman"] = table["w1"]
    columns = (["filename", "dataset", "detector_a", "detector_b", "spearman"]
               + [f"w{w}" for w in WINDOWS] + ["n_points"])
    return table[columns], dropped


def verify_against_scipy(parser, filenames, detectors, njobs=None):
    """Recompute every correlation the slow trusted way and compare.

    The fast path ranks each detector once per series and gets all pairs from
    one matrix multiply. That is easy to get subtly wrong -- tie handling
    above all, since every score vector starts with a long constant plateau
    from window padding. This recomputes the same numbers with
    scipy.stats.spearmanr and reports the largest disagreement.

    Returns:
        True if every value matches to within 1e-9.
    """
    n_pairs = len(detectors) * (len(detectors) - 1) // 2
    print(f"\nVerifying {n_pairs} pairs x {len(WINDOWS)} windows "
          f"on {len(filenames)} series, both ways ...")

    worst = 0.0
    worst_where = None
    n_checked = 0
    n_nan_both = 0

    stream = iter_score_chunks(parser, filenames, detectors, njobs=njobs)
    for fname, score_matrix in tqdm(stream, total=len(filenames), desc="Verify"):
        for window in WINDOWS:
            pooled = maxpool(score_matrix, window)
            fast = spearman_matrix(pooled)

            with warnings.catch_warnings():
                # scipy warns on constant input; NaN is the answer we want there.
                warnings.simplefilter("ignore")
                for a in range(len(detectors)):
                    for b in range(a + 1, len(detectors)):
                        slow = spearmanr(pooled[a], pooled[b]).statistic
                        quick = fast[a, b]

                        if np.isnan(slow) and np.isnan(quick):
                            n_nan_both += 1
                            n_checked += 1
                            continue
                        if np.isnan(slow) != np.isnan(quick):
                            print(
                                f"\n  NaN mismatch on {fname} w={window} "
                                f"{detectors[a]}/{detectors[b]}: fast={quick} scipy={slow}"
                            )
                            return False

                        diff = abs(slow - quick)
                        n_checked += 1
                        if diff > worst:
                            worst = diff
                            worst_where = (fname, window, detectors[a], detectors[b], quick, slow)

    print(f"\n  checked            : {n_checked} correlations")
    print(f"  NaN in both        : {n_nan_both} (constant score vectors)")
    print(f"  largest difference : {worst:.3e}")
    if worst_where is not None:
        fname, window, det_a, det_b, quick, slow = worst_where
        print(f"  worst case         : {det_a}/{det_b} on {fname} (w={window})")
        print(f"                       fast={quick:.15f}  scipy={slow:.15f}")

    passed = worst < 1e-9
    print("\n  RESULT: PASS -- fast path matches scipy" if passed
          else f"\n  RESULT: FAIL -- difference {worst:.3e} exceeds 1e-9")
    return passed


def main():
    ap = argparse.ArgumentParser(
        description="Step 1: Spearman correlation of every detector pair on every series."
    )
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"],
                    help="Benchmark kind (default: uni)")
    ap.add_argument("--dataset", default=None,
                    help="Restrict to one dataset (e.g. NAB). Default: all.")
    ap.add_argument("--test", action="store_true",
                    help="Verify the fast path against scipy on a small subset, "
                         "then stop. Uses --dataset, or NAB if not given.")
    ap.add_argument("--njobs", type=int, default=None,
                    help="Worker processes for score loading (default: cpu_count)")
    ap.add_argument("--out", default=None,
                    help="Output parquet path (default: data/divergence/pair_agreement.parquet)")
    args = ap.parse_args()

    parser = get_parser(args.kind)
    detectors = get_detectors(parser)

    dataset = args.dataset
    if args.test and dataset is None:
        dataset = "NAB"
        print("--test with no --dataset: using NAB (28 short series)")

    filenames = list_series(parser, dataset)

    print(f"kind      : {args.kind}")
    print(f"dataset   : {dataset or 'ALL'}")
    print(f"series    : {len(filenames)}")
    print(f"detectors : {len(detectors)}")
    print(f"pairs     : {len(detectors) * (len(detectors) - 1) // 2} per series")

    if args.test:
        ok = verify_against_scipy(parser, filenames, detectors, njobs=args.njobs)
        raise SystemExit(0 if ok else 1)

    start = time.time()
    table, dropped = build_agreement_table(parser, filenames, detectors, njobs=args.njobs)
    elapsed = time.time() - start

    if table.empty:
        print("\nNo scores could be loaded. Nothing written.")
        raise SystemExit(1)

    # Name carries the kind, matching data/anomaly_features_<kind>.parquet, so
    # a uni run and a multi run cannot overwrite each other.
    suffix = f"_{dataset}" if dataset else ""
    out_path = (Path(args.out) if args.out
                else OUT_ROOT / f"pair_agreement_{args.kind}{suffix}.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)

    n_nan = int(table.spearman.isna().sum())
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  rows            : {len(table):,}")
    print(f"  series          : {table.filename.nunique()}")
    print(f"  undefined (NaN) : {n_nan:,} ({n_nan / len(table) * 100:.2f}%) "
          f"-- constant score vectors")
    if dropped:
        print(f"  series dropped  : {len(dropped)} (incomplete or NaN scores)")
        for f in dropped[:5]:
            print(f"      {f}")
        if len(dropped) > 5:
            print(f"      ... and {len(dropped) - 5} more")
    print(f"  written to      : {out_path}")


if __name__ == "__main__":
    main()
