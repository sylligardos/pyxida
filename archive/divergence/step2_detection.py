"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Step 2 of the divergence study -- the detection table.

One row per (series, anomaly, detector): how much of that anomaly the detector
actually flagged, at several buffer sizes. That table is what the coverage
study queries -- which small set of detectors catches the most anomalies, and
what each one uniquely contributes.

Run:
    python src/divergence/step2_detection.py                 # all of TSB-AD-U
    python src/divergence/step2_detection.py --dataset NAB   # one dataset
    python src/divergence/step2_detection.py --test          # sanity checks only

The measure is detection density: the detector gets a budget equal to the
series' anomaly rate, and we ask what fraction of each anomaly falls inside it.
See detection_density() in utils.py for why ranking and a rate-scaled budget
are both necessary.

We also tried per-anomaly existence ("did any point of the anomaly beat the
threshold"). It saturates: a 134-point anomaly contains a high-percentile point
by chance alone, so a random score scores 0.996 and a constant score scores
1.000. Existence works as a reward term inside VUS, not as a measure on its own.
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from utils import (
    BUFFERS,
    OUT_ROOT,
    anomaly_bounds,
    buffer_weights,
    detection_chance,
    detection_density,
    get_parser,
    list_series,
)


def build_detection_table(parser, filenames, detectors, njobs=None):
    """One row per (series, anomaly, detector), one column per buffer.

    Loads a detector at a time rather than a series at a time: the parser drops
    a whole series when any requested detector is missing from it, so asking
    for all detectors at once would silently lose every series that Lag_Llama
    or SAND could not score. Per detector, a missing or length-mismatched cell
    costs only that cell.

    Returns:
        (table, skipped) where skipped counts dropped (detector, series) cells.
    """
    print("Loading time series and labels ...")
    kept_files, _, labels = parser.load_timeseries(filename=list(filenames), njobs=njobs)
    label_of = dict(zip(kept_files, labels))

    meta = parser.meta.set_index("filename")["dataset"].to_dict()

    # Anomaly geometry and the chance baseline depend only on the labels, so
    # they are computed once per series rather than once per detector.
    geometry = {}
    chance_of = {}
    weights_of = {}
    for fname in kept_files:
        starts, ends = anomaly_bounds(label_of[fname])
        if len(starts):
            geometry[fname] = (starts, ends)
            weights_of[fname] = buffer_weights(label_of[fname], BUFFERS)
            chance_of[fname] = detection_chance(label_of[fname], BUFFERS,
                                                weights=weights_of[fname])

    print(f"  {len(kept_files)} series, {len(geometry)} of them with anomalies")

    buffer_columns = [f"d{b}" for b in BUFFERS]
    frames = []
    skipped = 0

    for detector in tqdm(detectors, desc="Detectors"):
        scored_files, scores, _ = parser.load_scores(
            detectors=[detector], filenames=list(geometry),
            njobs=njobs, drop_missing=True, return_filenames=True,
        )
        rows = []
        for fname, score_matrix in zip(scored_files, scores):
            labels_here = label_of[fname]
            score = score_matrix[0]
            if len(score) != len(labels_here):
                skipped += 1
                continue

            starts, ends = geometry[fname]
            density = detection_density(labels_here, score, BUFFERS,
                                        weights=weights_of[fname])
            block = pd.DataFrame(density, columns=buffer_columns)
            for b_idx, buffer in enumerate(BUFFERS):
                block[f"chance{buffer}"] = chance_of[fname][:, b_idx]
            block.insert(0, "filename", fname)
            block.insert(1, "dataset", meta.get(fname, "Unknown"))
            block.insert(2, "detector", detector)
            block.insert(3, "anomaly_idx", np.arange(len(starts)))
            block.insert(4, "start", starts)
            block.insert(5, "end", ends)
            block.insert(6, "length", ends - starts)
            block.insert(7, "anomaly_rate", float(labels_here.mean()))
            block.insert(8, "ts_length", len(labels_here))
            rows.append(block)

        skipped += len(geometry) - len(scored_files)
        if rows:
            frames.append(pd.concat(rows, ignore_index=True))

    if not frames:
        return pd.DataFrame(), skipped
    return pd.concat(frames, ignore_index=True), skipped


def run_sanity_checks() -> bool:
    """Four detectors whose answer we know in advance.

    A measure that cannot separate these cannot separate real detectors either
    -- this is exactly the check that ruled out per-anomaly existence.
    """
    rng = np.random.default_rng(0)
    n_points = 4000
    labels = np.zeros(n_points, dtype=int)
    labels[1000:1134] = 1
    labels[2000:2134] = 1
    # Point anomalies too: they are 77.5% of TSB-AD-U and the buffer behaves
    # differently on them, since a widened window is almost all normal points.
    for index in (3000, 3200, 3400):
        labels[index] = 1
    rate = labels.mean()
    point_rows = [2, 3, 4]     # the three length-1 anomalies

    # A detector that responds clearly at every anomaly but has one enormous
    # spike elsewhere. Under the old fixed-threshold measure the spike ate the
    # whole budget and this scored 0 on every anomaly, which is what sweeping
    # thresholds is meant to fix. Modelled on MatrixProfile on 772_YAHOO.
    spiky = rng.uniform(0.0, 0.3, size=n_points)
    spiky[labels == 1] = rng.uniform(0.6, 0.7, size=int(labels.sum()))
    spiky[500:520] = 1.0

    # Fires over a short block ending just before every anomaly, never on it.
    # For the point anomalies that is entirely outside the event, so only the
    # buffer can recover it. A block rather than a single point because that is
    # what a windowed detector does: MatrixProfile on 772_YAHOO responded over
    # ten consecutive points beside the anomaly.
    early = np.zeros(n_points)
    for start, _ in zip(*anomaly_bounds(labels)):
        early[max(0, start - 12):max(0, start - 4)] = 1.0

    cases = {
        "perfect": labels.astype(float),
        "random": rng.uniform(size=n_points),
        "constant": np.zeros(n_points),
        "inverted": 1.0 - labels.astype(float),
        "early by 10": early,
        "responds, spike elsewhere": spiky,
    }

    print(f"\nSanity checks   (anomaly rate = {rate:.3f})\n")
    header = "  ".join(f"b={b:<5}" for b in BUFFERS)
    print(f"  {'detector':12s} {header}")

    results = {"chance": detection_chance(labels, BUFFERS).mean(axis=0)}
    on_points = {}
    print(f"  {'chance':26s} " + "  ".join(f"{v:<7.3f}" for v in results["chance"]))
    for name, score in cases.items():
        density = detection_density(labels, score, BUFFERS)
        results[name] = density.mean(axis=0)
        on_points[name] = density[point_rows].mean(axis=0)
        print(f"  {name:26s} " + "  ".join(f"{v:<7.3f}" for v in results[name]))

    print(f"\n  on the three point anomalies only:")
    for name in ("perfect", "early by 10"):
        print(f"  {name:26s} " + "  ".join(f"{v:<7.3f}" for v in on_points[name]))

    # A perfect detector cannot reach 1.0: its flagged points occupy the top
    # `rate` of the ranking, whose mean percentile is 1 - rate/2. That ceiling
    # is a property of the measure, not a defect, so it is asserted rather than
    # rounded away.
    ceiling = 1.0 - rate / 2
    checks = [
        (f"perfect detector reaches its ceiling of 1 - rate/2 = {ceiling:.3f}",
         abs(results["perfect"][0] - ceiling) < 0.01),
        # Chance is 0.5 now, not the anomaly rate: density is a mean percentile
        # and a random score's ranks are a uniform permutation.
        ("random scores about 0.5", abs(results["random"][0] - 0.5) < 0.05),
        ("random stays at chance for every buffer",
         np.abs(results["random"] - 0.5).max() < 0.05),
        ("constant scores 0.0", results["constant"].max() == 0.0),
        ("inverted scores near 0.0", results["inverted"][0] < 0.05),
        ("perfect ranks above random at every buffer",
         bool(np.all(results["perfect"] > results["random"]))),
        # An offset detector is invisible on a point anomaly at buffer 0, and
        # only the buffer can find it. On a 134-point subsequence a 10-point
        # shift still overlaps, which is why this is checked on the point
        # anomalies alone.
        ("an offset detector is missed on point anomalies at buffer 0",
         on_points["early by 10"][0] < 0.6),
        ("and the buffer recovers it",
         on_points["early by 10"][BUFFERS.index(16)] > on_points["early by 10"][0] + 0.1),
        ("but it still ranks below a direct hit",
         on_points["early by 10"][0] < on_points["perfect"][0]),
        # The case this rewrite exists for: one huge spike elsewhere used to
        # zero out every anomaly, because a single global threshold is
        # winner-take-all.
        ("a detector that responds is not zeroed by a spike elsewhere",
         results["responds, spike elsewhere"][0] > 0.7),
        ("and still ranks below a perfect detector",
         results["responds, spike elsewhere"][0] < results["perfect"][0]),
    ]
    print()
    for description, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {description}")
    passed = all(ok for _, ok in checks)
    print(f"\n  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


def main():
    ap = argparse.ArgumentParser(
        description="Step 2: per-anomaly detection density for every detector."
    )
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"])
    ap.add_argument("--dataset", default=None, help="Restrict to one dataset (e.g. NAB).")
    ap.add_argument("--test", action="store_true",
                    help="Run the sanity checks on synthetic detectors and stop.")
    ap.add_argument("--njobs", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.test:
        raise SystemExit(0 if run_sanity_checks() else 1)

    parser = get_parser(args.kind)
    detectors = parser.get_detectors()
    filenames = list_series(parser, args.dataset)

    print(f"kind      : {args.kind}")
    print(f"dataset   : {args.dataset or 'ALL'}")
    print(f"series    : {len(filenames)}")
    print(f"detectors : {len(detectors)}")
    print(f"buffers   : {BUFFERS}")

    start = time.time()
    table, skipped = build_detection_table(parser, filenames, detectors, njobs=args.njobs)
    elapsed = time.time() - start

    if table.empty:
        print("\nNothing computed. Nothing written.")
        raise SystemExit(1)

    suffix = f"_{args.dataset}" if args.dataset else ""
    out_path = (Path(args.out) if args.out
                else OUT_ROOT / f"detection_{args.kind}{suffix}.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  rows          : {len(table):,}")
    print(f"  anomalies     : {table.groupby(['filename', 'anomaly_idx']).ngroups:,}")
    print(f"  series        : {table.filename.nunique()}")
    print(f"  detectors     : {table.detector.nunique()}")
    print(f"  cells skipped : {skipped} (missing or length-mismatched scores)")
    print(f"  written to    : {out_path}")


if __name__ == "__main__":
    main()
