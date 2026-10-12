"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: TAB (Qiu et al., VLDB 2025) -> common format.

Source, as shipped (TAB_dataset.zip from the TAB repository's Google Drive):
    _original/dataset/anomaly_detect/DETECT_META.csv
    _original/dataset/anomaly_detect/data/<file_name>.csv

Each series is one long CSV `date, data, cols`: the values of every channel
stacked one after the other, `cols` naming the channel, and the label stored as
the channel called `label` (split into `label(<channels>)` pieces in ASD and
M_SMD, merged back here). DETECT_META.csv gives the dataset, the train length
(`train_lens`) and whether the series is univariate. TAB's train length is kept
as it is, even where the train part contains anomalies.

No scores: TAB publishes only aggregated results.

Run:
    python app/convert/tab.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import BENCHMARKS_ROOT, Loaded, Spec, convert  # noqa: E402

NAME = "tab"
SRC = BENCHMARKS_ROOT / NAME / "_original" / "dataset" / "anomaly_detect"


def list_specs() -> list:
    meta = pd.read_csv(SRC / "DETECT_META.csv")
    return [Spec(dataset=r.dataset_name, source_name=r.file_name,
                 source_path=f"dataset/anomaly_detect/data/{r.file_name}",
                 kind="uni" if bool(r.if_univariate) else "multi",
                 extra={"train_len": int(r.train_lens)})
            for r in meta.itertuples()]


def load(spec: Spec) -> Loaded:
    df = pd.read_csv(SRC / "data" / spec.source_name, dtype={"cols": str})
    # ASD and M_SMD split the label over several channels, `label(channel4,...)`
    # naming which channels are anomalous at those points. Together they cover
    # every timestamp once; merged back by date they are the plain label.
    is_label = df["cols"].str.startswith("label")
    lab = df[is_label]
    labels = (lab.sort_values("date")["data"].to_numpy() if "date" in df and lab["cols"].nunique() > 1
              else lab["data"].to_numpy())
    df = df[~is_label]
    channels = {c: g["data"].to_numpy() for c, g in df.groupby("cols", sort=False)}
    names = list(channels)
    values = pd.DataFrame(channels, columns=names).to_numpy(dtype=float)
    return Loaded(values=values, labels=labels, train_len=spec.extra["train_len"], columns=names)


if __name__ == "__main__":
    convert(NAME, list_specs(), load)
