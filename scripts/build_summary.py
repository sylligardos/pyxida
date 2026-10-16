"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: One small JSON with the benchmark's headline numbers.

The Start page shows how big TSB-AD is. Series, dataset and detector counts come
straight off `parser.meta` and cost nothing, but counting anomaly *events* means
reading every label file -- about a minute. A demo cannot pay that on page load,
so it is paid here, once, into a file small enough to ship with the repo.

Run:
    python scripts/build_summary.py            # uni
    python scripts/build_summary.py --kind multi
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.parser import TSBADParser  # noqa: E402

OUT_PATH = REPO_ROOT / "data" / "benchmark_summary.json"

# Scores are unusable on 10.7% of series for Lag_Llama (absent on 48, wrong
# length on 45) and on 0.1% for SAND (one file). See archive/references/DEMO_PLAN.md --
# SAND is meant to come back.
EXCLUDED = ["Lag_Llama", "SAND"]


def summarise(kind: str) -> dict:
    parser = TSBADParser(path=str(REPO_ROOT / "data"), kind=kind)
    filenames = parser.meta.filename.tolist()
    _, timeseries, labels = parser.load_timeseries(filename=filenames)

    # An anomaly is a contiguous run of 1s, not a labelled point: the median
    # series holds 2 events but hundreds of anomalous points.
    events = sum(int(np.diff(np.r_[0, label, 0]).clip(min=0).sum()) for label in labels)
    detectors = parser.get_detectors()

    return {
        "kind": kind,
        # Per-series length and anomaly count. The Workbench's sample button
        # needs lengths to skip the 900k-point series, and the Landscape tables
        # show both -- neither page can afford to open 870 files to find out.
        "lengths": {name: len(ts) for name, ts in zip(filenames, timeseries)},
        "anomalies": {
            name: int(np.diff(np.r_[0, label, 0]).clip(min=0).sum())
            for name, label in zip(filenames, labels)
        },
        "n_series": len(filenames),
        "n_datasets": parser.meta.dataset.nunique(),
        "n_detectors": len(detectors),
        "n_usable_detectors": len([d for d in detectors if d not in EXCLUDED]),
        "n_anomalies": events,
        "n_points": int(sum(len(t) for t in timeseries)),
        "n_entity_types": parser.meta.entity_type.nunique(),
    }


def main():
    ap = argparse.ArgumentParser(description="Headline numbers for the Start page.")
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"])
    args = ap.parse_args()

    summary = summarise(args.kind)

    existing = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())
    existing[args.kind] = summary

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(existing, indent=2) + "\n")

    for key, value in summary.items():
        if isinstance(value, dict):
            print(f"  {key:20s} {len(value)} series")
            continue
        print(f"  {key:20s} {value}")
    print(f"\n  written to {OUT_PATH}")


if __name__ == "__main__":
    main()
