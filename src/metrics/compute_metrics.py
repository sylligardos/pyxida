"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Per-series metrics for any benchmark in the common format.

Writes metrics/<kind>/<Detector>.csv with exactly the columns of TSB-AD's own
metric files, computed the same way, so every benchmark is evaluated alike:

    File Name, Model Name, Length, AUC-PR, AUC-PR Time cost,
    VUS-PR (L: 0), (L: 1), (L: 2), (L: 4), ..., (L: 256), VUS-PR Time cost

AUC-PR is scikit-learn's average precision. VUS-PR comes from FF-VUS
(~/Documents/ff-vus), cumulative up to buffer 256, read at the ten buffers
above. GPU if available, CPU otherwise.

Run from the ffvus environment, which has FF-VUS's dependencies:
    conda run -n ffvus python src/metrics/compute_metrics.py --benchmark tsb-uad
    conda run -n ffvus python src/metrics/compute_metrics.py --benchmark tab --detectors IForest SR
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

FFVUS_SRC = Path.home() / "Documents" / "ff-vus" / "src"
sys.path.insert(0, str(FFVUS_SRC))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsbadparser import TSBADParser  # noqa: E402

BUFFERS = [0] + [2 ** x for x in range(9)]   # 0, 1, 2, 4, ..., 256

_metric = None  # one FF-VUS object per worker process


def _get_metric(device: str):
    global _metric
    if _metric is None:
        if device == "cuda":
            from vus.vus_torch import VUSTorch
            _metric = VUSTorch(slope_size=BUFFERS[-1], cumulative=True, device="cuda")
        else:
            from vus.vus_numpy import VUSNumpy
            _metric = VUSNumpy(slope_size=BUFFERS[-1], cumulative=True)
    return _metric


def metrics_for(label: np.ndarray, score: np.ndarray, device: str) -> dict:
    """The row TSB-AD's metric files hold for one detector on one series."""
    out = {}
    tic = time.perf_counter()
    out["AUC-PR"] = min(1.0, average_precision_score(label, score))
    out["AUC-PR Time cost"] = time.perf_counter() - tic

    (vus, _), vus_time = _get_metric(device).compute(label, score)
    for b in BUFFERS:
        v = vus[b]
        # Clipped: float rounding gives 1.0000000000000002 on perfect detections.
        out[f"VUS-PR (L: {b})"] = min(1.0, v.item() if hasattr(v, "item") else float(v))
    out["VUS-PR Time cost"] = vus_time
    return out


def _series_job(args):
    """All requested detectors on one series. Missing or bad scores are skipped."""
    raw_path, scores_path, filename, detectors, device = args
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
                     **metrics_for(label, score, device)})
    return rows, skipped


def compute(benchmark: str, kind: str, detectors=None, workers: int = 14, device: str = "auto"):
    parser = TSBADParser(benchmark=benchmark, kind=kind)
    detectors = detectors or parser.get_detectors()
    if not detectors or parser.meta.empty:
        print(f"{benchmark}/{kind}: nothing to do")
        return
    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    # One GPU cannot be shared well by many processes.
    workers = 1 if device == "cuda" else workers

    jobs = [(parser.raw_path, parser.scores_path, f, detectors, device) for f in parser.meta.filename]
    rows, skipped = [], []
    with Pool(workers) as pool:
        for r, s in tqdm(pool.imap_unordered(_series_job, jobs, chunksize=4), total=len(jobs),
                         desc=f"{benchmark}/{kind} on {device}"):
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
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = ap.parse_args()
    for kind in (["uni", "multi"] if args.kind == "both" else [args.kind]):
        compute(args.benchmark, kind, args.detectors, args.workers, args.device)
