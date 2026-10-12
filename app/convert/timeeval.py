"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: TimeEval (Schmidl et al., VLDB 2022) -> common format.

Source, as shipped (per-collection zips from the TimeEval evaluation-paper site):
    _original/datasets.csv                          index of the indexed collections
    _original/{univariate,multivariate}/<coll>/<name>.test.csv   [+ <name>.train.csv]
    _original/GutenTAG/datasets.csv                 GutenTAG's own index
    _original/GutenTAG/<name>/{test,train_no_anomaly,train_anomaly}.csv

Every CSV is `timestamp, value(s)..., is_anomaly`. The timestamp is dropped.

Train split, following TimeEval's own convention:
  * `split_at` set (KDD-TSAD): the test file already starts with the train part,
    so the series is the test file and tr = split_at.
  * a separate train file: a separate recording. The series is train followed by
    test, tr = len(train) -- TSB-AD's "train prefix" layout.
  * no train file: tr_0.
GutenTAG lists every series once per training type, all sharing one test file.
One series is written per test file, with the anomaly-free train file when
there is one.

Collections present in the download but not in the index (TSB-UAD-artificial,
TSB-UAD-synthetic, TODS-synthetic, CATSv2) are found by scanning for
*.test.csv; their train file, if any, is the sibling *.train.csv.

Kitsune is not converted (41 GB unpacked; the zip is kept in _archives/).
The licence-restricted collections in the index (Yahoo, IOPS, SSA, SWaT, WADI,
Keogh) have no files and are listed in _excluded.csv.

No scores: TimeEval publishes metrics per run, not per-timestep scores.

Run:
    python app/convert/timeeval.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import BENCHMARKS_ROOT, Loaded, Spec, convert  # noqa: E402

NAME = "timeeval"
SRC = BENCHMARKS_ROOT / NAME / "_original"
SKIP_COLLECTIONS = {"Kitsune"}
TRAIN_PRIORITY = {"semi-supervised": 0, "supervised": 1, "unsupervised": 2}


def _from_index(index: pd.DataFrame, root: Path, missing: list) -> list:
    """Specs from a TimeEval index, one per test file."""
    index = index.assign(_p=index.train_type.map(TRAIN_PRIORITY).fillna(3))
    index = index.sort_values("_p").drop_duplicates("test_path")
    specs = []
    for r in index.itertuples():
        if r.collection_name in SKIP_COLLECTIONS:
            continue
        test = root / r.test_path
        if not test.exists():
            missing.append({"dataset": r.collection_name, "source_name": r.dataset_name,
                            "source_path": str(test.relative_to(SRC)), "reason": "not downloadable"})
            continue
        train = root / r.train_path if isinstance(r.train_path, str) else None
        specs.append(Spec(
            dataset=r.collection_name, source_name=r.dataset_name,
            source_path=str(test.relative_to(SRC)),
            kind="uni" if r.input_type == "univariate" else "multi",
            extra={"test": test, "train": train,
                   "split_at": int(r.split_at) if pd.notna(r.split_at) else None}))
    return specs


def list_specs() -> tuple:
    missing = []
    specs = _from_index(pd.read_csv(SRC / "datasets.csv"), SRC, missing)
    specs += _from_index(pd.read_csv(SRC / "GutenTAG" / "datasets.csv"), SRC / "GutenTAG", missing)

    indexed = {s.extra["test"].resolve() for s in specs} | {(SRC / m["source_path"]).resolve() for m in missing}
    for folder, kind in [("univariate", "uni"), ("multivariate", "multi")]:
        for test in sorted((SRC / folder).glob("*/*.test.csv")):
            coll = test.parent.name
            if coll in SKIP_COLLECTIONS or test.resolve() in indexed:
                continue
            stem = test.name[: -len(".test.csv")]
            train = test.with_name(stem + ".train.csv")
            specs.append(Spec(dataset=coll, source_name=stem, source_path=str(test.relative_to(SRC)),
                              kind=kind, extra={"test": test, "train": train if train.exists() else None,
                                                "split_at": None}))
    return specs, missing


def _read(path: Path) -> tuple:
    df = pd.read_csv(path)
    return df.iloc[:, 1:-1], df.iloc[:, -1].to_numpy()


def load(spec: Spec) -> Loaded:
    values, labels = _read(spec.extra["test"])
    train_len = 0
    if spec.extra["split_at"] is not None:
        train_len = spec.extra["split_at"]
    elif spec.extra["train"] is not None:
        tr_values, tr_labels = _read(spec.extra["train"])
        tr_values.columns = values.columns
        values = pd.concat([tr_values, values], ignore_index=True)
        labels = pd.concat([pd.Series(tr_labels), pd.Series(labels)], ignore_index=True).to_numpy()
        train_len = len(tr_labels)
    return Loaded(values=values.to_numpy(dtype=float), labels=labels, train_len=train_len,
                  columns=list(values.columns))


if __name__ == "__main__":
    specs, missing = list_specs()
    convert(NAME, specs, load, workers=8)
    # Series listed in the index but not downloadable go into _excluded.csv too.
    exc_path = BENCHMARKS_ROOT / NAME / "_excluded.csv"
    exc = pd.concat([pd.read_csv(exc_path), pd.DataFrame(missing)], ignore_index=True)
    exc.sort_values(["dataset", "source_name"]).to_csv(exc_path, index=False)
    print(f"plus {len(missing)} indexed series with no files (licence-restricted)")
