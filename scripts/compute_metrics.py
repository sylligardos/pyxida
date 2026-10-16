"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Per-series metrics for any benchmark in the common format.

Writes metrics/<kind>/<Detector>.csv with exactly the columns of TSB-AD's own
metric files, computed the same way, so every benchmark is evaluated alike:

    File Name, Model Name, Length, AUC-PR, AUC-PR Time cost,
    VUS-PR (L: 0), (L: 1), (L: 2), (L: 4), ..., (L: 256), VUS-PR Time cost

AUC-PR is scikit-learn's average precision. VUS-PR is TSB-AD's own
implementation (scripts/vus.py, with its source and references), one pass up
to buffer 256, read at the ten buffers above. It is slow on long series;
--workers spreads the series over processes.

Run, from the repo root:
    python scripts/compute_metrics.py --benchmark tsb-uad
    python scripts/compute_metrics.py --benchmark tab --detectors IForest SR
"""

import argparse
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parser import TSBADParser  # noqa: E402
from vus import vus_pr  # noqa: E402

BUFFERS = [0] + [2 ** x for x in range(9)]   # 0, 1, 2, 4, ..., 256


def metrics_for(label: np.ndarray, score: np.ndarray) -> dict:
    """The row TSB-AD's metric files hold for one detector on one series."""
    out = {}
    tic = time.perf_counter()
    out["AUC-PR"] = min(1.0, average_precision_score(label, score))
    out["AUC-PR Time cost"] = time.perf_counter() - tic

    tic = time.perf_counter()
    vus = vus_pr(label, score, BUFFERS)
    for b in BUFFERS:
        # Clipped: float rounding gives 1.0000000000000002 on perfect detections.
        out[f"VUS-PR (L: {b})"] = min(1.0, vus[b])
    out["VUS-PR Time cost"] = time.perf_counter() - tic
    return out


def _series_job(args):
    """All requested detectors on one series. Missing or bad scores are skipped."""
    raw_path, scores_path, filename, detectors = args
    label = pd.read_csv(raw_path / filename)["Label"].to_numpy().astype(int)
    rows, skipped = [], []
    for det in detectors:
        path = scores_path / det / filename.replace(".csv", ".npy")
        if not path.exists():
            continue
        score = np.load(path).astype(np.float64).ravel()
        if len(score) != len(label) or not np.isfinite(score).all():
            skipped.append((det, filename))
            continue
        rows.append({"File Name": filename, "Model Name": det, "Length": len(label),
                     **metrics_for(label, score)})
    return rows, skipped


def compute(benchmark: str, kind: str, detectors=None, workers: int = 14):
    parser = TSBADParser(benchmark=benchmark, kind=kind)
    detectors = detectors or parser.get_detectors()
    if not detectors or parser.meta.empty:
        print(f"{benchmark}/{kind}: nothing to do")
        return
    jobs = [(parser.raw_path, parser.scores_path, f, detectors) for f in parser.meta.filename]
    rows, skipped = [], []
    with Pool(workers) as pool:
        for r, s in tqdm(pool.imap_unordered(_series_job, jobs, chunksize=4), total=len(jobs),
                         desc=f"{benchmark}/{kind}"):
            rows += r
            skipped += s

    out_dir = parser.path / "metrics" / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for det, part in df.groupby("Model Name"):
        part.sort_values("File Name").to_csv(out_dir / f"{det}.csv", index=False)
    print(f"{benchmark}/{kind}: {len(df)} rows for {df['Model Name'].nunique()} detectors; "
          f"{len(skipped)} (detector, series) pairs skipped for bad scores")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--kind", choices=["uni", "multi", "both"], default="both")
    ap.add_argument("--detectors", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=14)
    args = ap.parse_args()
    for kind in (["uni", "multi"] if args.kind == "both" else [args.kind]):
        compute(args.benchmark, kind, args.detectors, args.workers)
