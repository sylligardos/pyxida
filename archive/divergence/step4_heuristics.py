"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Step 4 of the divergence study -- do the obvious heuristics find the best set?

Step 3 scored every detector combination of size 1..3. This step asks whether a
researcher could have picked the winner without that exhaustive search, by
scoring five candidate sets per (series, k, buffer):

    best        the highest-VUS combination -- an oracle, and the thing to beat
    top_k       the k detectors with the highest solo VUS on that series
    least_corr  the combination with the lowest mean pairwise Spearman
    least_corr_top10   the same, but restricted to the 10 best solo detectors
    max_coverage       greedy on detection density, from step 2

least_corr is included to show why naive diversity fails: POLY is constant on
40% of series and SR is nearly flat, and a flat score correlates with nothing,
so those pairs win "most diverse" by being useless. least_corr_top10 is the
honest opponent -- be accurate AND diverse -- and the one worth beating.

Run:
    python src/divergence/step4_heuristics.py --dataset NAB
    python src/divergence/step4_heuristics.py --summary-only
"""

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from selection import (HEURISTICS, combo_lookup, greedy_coverage,
                       mean_pairwise_rho, pick_sets, rho_matrix)
from utils import OUT_ROOT, get_detectors, get_parser

KS = [2, 3]
COVERAGE_BUFFER = 0       # density column used by the max-coverage greedy


def load_inputs(kind: str, dataset: str | None):
    suffix = f"_{dataset}" if dataset else ""
    combos_path = OUT_ROOT / f"combos_{kind}{suffix}.parquet"
    if not combos_path.exists():
        raise SystemExit(f"Missing {combos_path}. Run step3_combos.py first.")

    combos = pd.read_parquet(combos_path)
    detectors = pd.read_parquet(
        OUT_ROOT / f"combos_{kind}_detectors.parquet")["detector"].tolist()

    agreement = pd.read_parquet(OUT_ROOT / f"pair_agreement_{kind}.parquet")
    detection = pd.read_parquet(OUT_ROOT / f"detection_{kind}.parquet")
    return combos, detectors, agreement, detection


def series_density(detection: pd.DataFrame, filename: str,
                   detectors: list[str]) -> np.ndarray | None:
    """(n_anomalies, n_detectors) density matrix for one series."""
    rows = detection[detection.filename == filename]
    if rows.empty:
        return None
    wide = rows.pivot_table(index="anomaly_idx", columns="detector",
                            values=f"d{COVERAGE_BUFFER}")
    wide = wide.reindex(columns=detectors)
    return wide.to_numpy(dtype=np.float64, na_value=0.0)


def evaluate_series(filename, dataset, frame, detectors, matrix, density,
                    buffers):
    """One row per (k, buffer, heuristic) for a single series."""
    n_detectors = len(detectors)
    vus_columns = [f"vus_{b}" for b in buffers]

    solo = frame[frame.k == 1]
    solo_order = solo.d0.to_numpy()
    solo_vus = solo[vus_columns].to_numpy(dtype=np.float64)      # (30, n_buffers)
    solo_by_detector = np.full((n_detectors, len(buffers)), -np.inf)
    solo_by_detector[solo_order] = solo_vus

    records = []
    for k in KS:
        block = frame[frame.k == k]
        if block.empty:
            continue
        combos = block[[f"d{i}" for i in range(k)]].to_numpy()
        vus = block[vus_columns].to_numpy(dtype=np.float64)       # (n_combos, n_buffers)
        genuine = block.n_constant.to_numpy() == 0
        if not genuine.any():
            continue

        rho = mean_pairwise_rho(matrix, combos)
        lookup = combo_lookup(combos)
        coverage_set = None
        if density is not None and density.shape[0] > 0:
            coverage_set = greedy_coverage(density, k)

        for bi, buffer in enumerate(buffers):
            picks = pick_sets(combos, vus[:, bi], genuine,
                              solo_by_detector[:, bi], rho, coverage_set,
                              lookup=lookup)
            if picks["best"] is None:
                continue

            for name in HEURISTICS:
                row_index = picks.get(name)
                if row_index is None:
                    continue
                combo = sorted(combos[row_index].tolist())
                records.append({
                    "filename": filename, "dataset": dataset,
                    "k": k, "buffer": buffer, "heuristic": name,
                    "detectors": "|".join(detectors[d] for d in combo),
                    "vus": vus[row_index, bi],
                    # Negative regret is possible and meaningful: it means the
                    # heuristic picked a degenerate set that beats every genuine
                    # k-combination, i.e. combining actively hurt on that series.
                    "regret": vus[picks["best"], bi] - vus[row_index, bi],
                    "is_best": row_index == picks["best"],
                    "n_constant": int(block.n_constant.to_numpy()[row_index]),
                })
    return records


def build(kind, dataset, buffers):
    combos, detectors, agreement, detection = load_inputs(kind, dataset)
    available = [b for b in buffers if f"vus_{b}" in combos.columns]
    if not available:
        raise SystemExit("None of the requested buffers exist in the combos table.")

    records = []
    for filename, frame in tqdm(combos.groupby("filename", observed=True),
                                desc="Series"):
        if frame.empty:
            continue
        pairs = agreement[agreement.filename == filename]
        matrix = rho_matrix(pairs, detectors)
        density = series_density(detection, filename, detectors)
        dataset_name = str(frame.dataset.iloc[0])
        records += evaluate_series(filename, dataset_name, frame, detectors,
                                   matrix, density, available)

    return pd.DataFrame(records)


def summarise(table: pd.DataFrame, buffer: int) -> pd.DataFrame:
    """How often each heuristic finds the winner, and what it costs when it does not."""
    at = table[table.buffer == buffer]
    rows = []
    for k in sorted(at.k.unique()):
        block = at[at.k == k]
        for name in HEURISTICS:
            sub = block[block.heuristic == name]
            if sub.empty:
                continue
            rows.append({
                "k": k, "heuristic": name, "series": len(sub),
                "finds_best": f"{sub.is_best.mean() * 100:.1f}%",
                "mean_vus": round(sub.vus.mean(), 4),
                "mean_regret": round(sub.regret.mean(), 4),
                "median_regret": round(sub.regret.median(), 4),
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"])
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--buffers", default="all",
                    help="Comma-separated VUS buffers, or 'all' for 0..256. "
                         "Step 3 stores every buffer, so there is no reason to "
                         "quantise the slider in the demo.")
    ap.add_argument("--report-buffer", type=int, default=128)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    buffers = (list(range(257)) if args.buffers == "all"
               else [int(b) for b in args.buffers.split(",")])
    table = build(args.kind, args.dataset, buffers)
    if table.empty:
        raise SystemExit("No rows produced.")

    suffix = f"_{args.dataset}" if args.dataset else ""
    out = Path(args.out) if args.out else OUT_ROOT / f"heuristics_{args.kind}{suffix}.parquet"
    table.to_parquet(out, index=False, compression="zstd")
    print(f"\n{len(table):,} rows, {table.filename.nunique()} series -> {out}")

    print(f"\nAt VUS buffer L={args.report_buffer}:\n")
    print(summarise(table, args.report_buffer).to_string(index=False))


if __name__ == "__main__":
    main()
