"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Fill the AUC-PR of the (series, detector) pairs that have no row in
       metrics/<kind>/<Detector>.csv but do have a score. The new rows carry
       AUC-PR only; the VUS-PR columns stay empty (the demo reads VUS-PR from
       the combination tables for TSB-AD anyway).

Run, from the repo root:
    python scripts/fill_aucpr.py --benchmark tsb-ad --kind uni
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.parser import TSBADParser  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"])
    a = ap.parse_args()

    parser = TSBADParser(benchmark=a.benchmark, kind=a.kind)
    metrics_dir = parser.path / "metrics" / a.kind
    labels: dict[str, np.ndarray] = {}
    added = 0
    for det in parser.get_detectors():
        path = metrics_dir / f"{det}.csv"
        df = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["File Name", "Model Name", "Length", "AUC-PR", "AUC-PR Time cost"])
        have = set(df["File Name"])
        rows = []
        for f in parser.meta.filename:
            score_path = parser.scores_path / det / f.replace(".csv", ".npy")
            if f in have or not score_path.exists():
                continue
            if f not in labels:
                labels[f] = pd.read_csv(parser.raw_path / f, usecols=["Label"])["Label"].to_numpy().astype(int)
            label = labels[f]
            score = np.load(score_path).astype(np.float64).ravel()
            if len(score) != len(label) or not np.isfinite(score).all():
                print(f"  skipped {det} on {f}: bad score")
                continue
            tic = time.perf_counter()
            ap_ = min(1.0, average_precision_score(label, score))
            rows.append({"File Name": f, "Model Name": det, "Length": len(label),
                         "AUC-PR": ap_, "AUC-PR Time cost": time.perf_counter() - tic})
        if rows:
            df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True).sort_values("File Name")
            df.to_csv(path, index=False)
            added += len(rows)
            print(f"{det}: +{len(rows)} rows")
    print(f"{a.benchmark}/{a.kind}: {added} AUC-PR values added")


if __name__ == "__main__":
    main()
