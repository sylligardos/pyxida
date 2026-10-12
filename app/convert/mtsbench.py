"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: mTSBench (Zhou, Brif & Lourentzou, 2025) -> common format.

Source, as shipped (Hugging Face dataset PLAN-Lab/mTSBench, downloaded by
_scripts/download_mtsbench.sh):
    _original/data/<dataset>/<name>_{train,test}.csv     [+ <name>_val.csv]
    _original/published/vus_pr_{test,val}.csv            their per-series VUS-PR
    _original/published/data_summary.csv

Every CSV is `timestamp, features..., is_anomaly`, except the train files of
SMD, SMAP, MSL and PSM, which have no label column: they are anomaly-free
training data and get label 0. The timestamp is dropped.

Multivariate only. Train split, following mTSBench's own convention: the series
is train followed by test, tr = len(train). The 19 validation segments (one per
dataset, which mTSBench holds out to train its model selectors) are not part of
the series -- CalIt2's covers the same dates as its train file -- and are listed
in _excluded.csv.

348 test series ship; mTSBench's published results cover 344 of them (SMAP A-7,
G-4, R-1 and cicids_0 are extra). All 348 are converted.

No scores: mTSBench publishes a per-series VUS-PR table (kept in
_original/published/, computed with its own evaluation code), not scores.

Run:
    python app/convert/mtsbench.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import BENCHMARKS_ROOT, Loaded, Spec, convert  # noqa: E402

NAME = "mtsbench"
SRC = BENCHMARKS_ROOT / NAME / "_original"
LABEL = "is_anomaly"


def list_specs() -> list:
    specs = []
    for test in sorted((SRC / "data").glob("*/*_test.csv")):
        stem = test.name[: -len("_test.csv")]
        specs.append(Spec(dataset=test.parent.name, source_name=stem,
                          source_path=str(test.relative_to(SRC)), kind="multi",
                          extra={"test": test, "train": test.with_name(stem + "_train.csv")}))
    return specs


def excluded_validation() -> list:
    return [{"dataset": v.parent.name, "source_name": v.name[: -len("_val.csv")],
             "source_path": str(v.relative_to(SRC)),
             "reason": "validation segment (held out by mTSBench for model selection)"}
            for v in sorted((SRC / "data").glob("*/*_val.csv"))]


def _read(path: Path) -> tuple:
    df = pd.read_csv(path).iloc[:, 1:]          # drop the timestamp
    if LABEL in df.columns:
        return df.drop(columns=LABEL), df[LABEL].to_numpy()
    return df, pd.Series(0, index=df.index).to_numpy()   # unlabelled = anomaly-free train


def load(spec: Spec) -> Loaded:
    test_values, test_labels = _read(spec.extra["test"])
    train_values, train_labels = _read(spec.extra["train"])
    if list(train_values.columns) != list(test_values.columns):
        raise ValueError("train and test have different channels")
    values = pd.concat([train_values, test_values], ignore_index=True)
    labels = pd.concat([pd.Series(train_labels), pd.Series(test_labels)], ignore_index=True)
    return Loaded(values=values.to_numpy(dtype=float), labels=labels.to_numpy(),
                  train_len=len(train_values), columns=list(values.columns))


if __name__ == "__main__":
    convert(NAME, list_specs(), load, workers=8)
    exc_path = BENCHMARKS_ROOT / NAME / "_excluded.csv"
    exc = pd.concat([pd.read_csv(exc_path), pd.DataFrame(excluded_validation())], ignore_index=True)
    exc.sort_values(["dataset", "source_name"]).to_csv(exc_path, index=False)
    print(f"plus {len(excluded_validation())} validation segments listed as excluded")
