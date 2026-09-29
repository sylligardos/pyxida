"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Shared machinery for converting a TSAD benchmark into the common format.

The common format is TSB-AD's, unchanged:

    <benchmark>/raw/{uni,multi}/<file>.csv          values..., Label
    <benchmark>/scores/{uni,multi}/<Det>/<file>.npy one float per timestamp
    <benchmark>/splits/{U,M}-{Eval,Label}.csv

    <file> = <num>_<Dataset>_id_<k>_<Domain>_tr_<train>_1st_<first>

Two rules on top of TSB-AD's:
  * no `_` inside a field; anything outside [A-Za-z0-9-] becomes `-`
  * a series with no train split gets tr_0 (semi-supervised detectors skip it)

Each benchmark module only has to say *what* its series are (a list of Specs)
and *how* to read one (a loader returning values, labels, train length). This
module does the rest: validation, numbering, writing, and the bookkeeping files
`_source_map.csv` (every written series -> where it came from) and
`_excluded.csv` (every source series that was not written, and why).

Numbering happens after validation, so excluded series leave no gaps. Series
are numbered per kind in (dataset, source name) order, which makes the output
deterministic across runs.
"""

import os
import re
import shutil
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

BENCHMARKS_ROOT = Path(os.environ.get("TSAD_BENCHMARKS", Path.home() / "Documents" / "tsad-benchmarks"))


def clean_field(text: str) -> str:
    """One filename field: `_` and anything else unsafe become `-`."""
    text = re.sub(r"[^A-Za-z0-9-]+", "-", str(text))
    return re.sub(r"-{2,}", "-", text).strip("-") or "x"


# --------------------------------------------------------------------- domains
# TSB-AD's own vocabulary. Datasets TSB-AD also has keep TSB-AD's domain; the
# rest are assigned by what the data measures. Keys are clean_field(dataset).
DOMAINS = {
    # human activity
    "Daphnet": "HumanActivity", "M-daphnet": "HumanActivity", "OPPORTUNITY": "HumanActivity",
    # medical
    "ECG": "Medical", "LTDB": "Medical", "MITDB": "Medical", "SVDB": "Medical", "SED": "Medical",
    # sensors / industrial control
    "Genesis": "Sensor", "M-genesis": "Sensor", "GHL": "Sensor", "CATSv2": "Sensor",
    "MSL": "Sensor", "SMAP": "Sensor", "NASA-MSL": "Sensor", "NASA-SMAP": "Sensor",
    "NASA-MSL-new": "Sensor", "NASA-SMAP-new": "Sensor", "SWaT": "Sensor", "SWAT": "Sensor",
    "GECCO": "Sensor", "PUMP": "Sensor", "SKAB": "Sensor", "DLR": "Sensor",
    # facilities / servers
    "SMD": "Facility", "M-SMD": "Facility", "PSM": "Facility", "Exathlon": "Facility",
    "ASD": "Facility", "Occupancy": "Facility",
    # web services / networks
    "IOPS": "WebService", "GAIA": "WebService", "CICIDS": "WebService", "KDD-99": "WebService",
    # traffic
    "Dodgers": "Traffic", "CalIt2": "Traffic", "Metro": "Traffic", "NYC": "Traffic",
    # environment
    "SensorScope": "Environment", "TAO": "Environment", "SWAN": "Environment",
    # finance
    "Creditcard": "Finance",
    # synthetic
    "MGAB": "Synthetic", "GutenTAG": "Synthetic", "TODS": "Synthetic", "TODS-synthetic": "Synthetic",
    "TSB-UAD-artificial": "Synthetic", "TSB-UAD-synthetic": "Synthetic",
    # UCR archive: many sources in one dataset
    "KDD21": "Mixed", "KDD-TSAD": "Mixed", "NormA": "Mixed",
}

_NAB_RULES = [  # substring of the source name -> domain, first match wins
    ("art", "Synthetic"), ("Tweets", "WebService"), ("tweets", "WebService"),
    ("AWS", "WebService"), ("ec2", "WebService"), ("rds", "WebService"), ("elb", "WebService"),
    ("grok", "WebService"), ("AdExchange", "WebService"), ("exchange", "WebService"),
    ("Traffic", "Traffic"), ("TravelTime", "Traffic"), ("speed", "Traffic"), ("occupancy", "Traffic"),
    ("taxi", "Traffic"), ("temperature", "Environment"),
]


def domain_of(dataset: str, source_name: str) -> str:
    """Domain for one series. NAB and Yahoo mix domains, so they go per series."""
    ds = clean_field(dataset)
    if ds == "NAB":
        for key, dom in _NAB_RULES:
            if key in source_name:
                return dom
        return "Facility"
    if ds.upper() == "YAHOO":
        return "WebService" if re.search(r"A1|real", source_name) else "Synthetic"
    return DOMAINS.get(ds, "Unknown")


# ------------------------------------------------------------------ the spec
@dataclass
class Spec:
    """One source series, before it is read."""
    dataset: str                 # dataset name as the benchmark calls it
    source_name: str             # series name as the benchmark calls it
    source_path: str             # main file, for the source map
    kind: Optional[str] = None   # 'uni' / 'multi'; None = decide from the data
    extra: dict = field(default_factory=dict)  # anything the loader needs


@dataclass
class Loaded:
    values: np.ndarray           # (n, d) float
    labels: np.ndarray           # (n,) int 0/1
    train_len: int               # 0 = no train split
    columns: list                # d channel names


# ------------------------------------------------------------------ one series
def _process(args):
    """Load, validate and write one series to a temporary name."""
    spec, loader, tmp_dir, idx = args
    base = dict(dataset=spec.dataset, source_name=spec.source_name, source_path=spec.source_path)
    try:
        s = loader(spec)
    except Exception as e:  # a broken source file is excluded, never fatal
        return {**base, "status": "excluded", "reason": f"load error: {type(e).__name__}: {e}"}

    values = np.asarray(s.values, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    labels = np.asarray(s.labels).astype(float)
    if len(values) != len(labels):
        return {**base, "status": "excluded", "reason": f"length mismatch {len(values)} vs {len(labels)}"}

    # Missing values. A channel missing in more than half of its points is
    # dropped first (a few OPPORTUNITY sensors are missing almost everywhere,
    # and would otherwise take every row with them); then rows with any missing
    # value go, as TSB-AD's own runner does, and the train boundary moves with them.
    columns = list(s.columns)
    dead = np.isnan(values).mean(axis=0) > 0.5
    if dead.all():
        return {**base, "status": "excluded", "reason": "every channel missing"}
    values, columns = values[:, ~dead], [c for c, d in zip(columns, dead) if not d]
    keep = ~(np.isnan(values).any(axis=1) | np.isnan(labels))
    n_dropped = int((~keep).sum())
    train_len = int(keep[: s.train_len].sum()) if s.train_len else 0
    values, labels = values[keep], labels[keep].astype(int)

    if len(values) == 0:
        return {**base, "status": "excluded", "reason": "empty"}
    if not set(np.unique(labels)) <= {0, 1}:
        return {**base, "status": "excluded", "reason": "labels not 0/1"}
    if labels.sum() == 0:
        return {**base, "status": "excluded", "reason": "no anomalies"}
    if labels.sum() == len(labels):
        return {**base, "status": "excluded", "reason": "all points anomalous"}

    kind = spec.kind or ("uni" if values.shape[1] == 1 else "multi")
    if kind == "uni" and values.shape[1] != 1:
        return {**base, "status": "excluded", "reason": f"declared uni but has {values.shape[1]} channels"}

    if kind == "uni":
        columns = ["Data"]
    else:
        columns = [str(c) if str(c) != "Label" else "Label-channel" for c in columns]
    df = pd.DataFrame(values, columns=columns)
    df["Label"] = labels
    tmp = Path(tmp_dir) / f"{idx}.csv"
    df.to_csv(tmp, index=False)

    return {**base, "status": "ok", "tmp": str(tmp), "kind": kind, "length": len(df),
            "channels": values.shape[1], "train_len": train_len,
            "first_anomaly": int(np.argmax(labels)), "n_dropped_nan": n_dropped,
            "n_dropped_channels": int(dead.sum())}


# ------------------------------------------------------------------ the writer
def convert(
    benchmark: str,
    specs: list,
    loader: Callable[[Spec], Loaded],
    workers: int = 12,
    out_root: Path = BENCHMARKS_ROOT,
) -> pd.DataFrame:
    """Write every valid series of `specs` in the common format.

    Returns the source map (one row per written series). Existing converted
    output for this benchmark is replaced; `_original/` and `_archives/` are
    never touched.
    """
    out = Path(out_root) / benchmark
    for sub in ["raw", "splits", "_tmp"]:
        shutil.rmtree(out / sub, ignore_errors=True)
    for kind in ["uni", "multi"]:
        (out / "raw" / kind).mkdir(parents=True, exist_ok=True)
    (out / "splits").mkdir(parents=True)
    (out / "_tmp").mkdir()

    jobs = [(s, loader, out / "_tmp", i) for i, s in enumerate(specs)]
    with Pool(workers) as pool:
        results = list(tqdm(pool.imap_unordered(_process, jobs), total=len(jobs), desc=benchmark))

    res = pd.DataFrame(results)
    ok = res[res.status == "ok"].copy()
    excluded = res[res.status != "ok"].reindex(columns=["dataset", "source_name", "source_path", "reason"])

    rows = []
    for kind in ["uni", "multi"]:
        part = ok[ok.kind == kind].sort_values(["dataset", "source_name"])
        width = max(3, len(str(len(part))))
        id_in_ds = {}
        for num, r in enumerate(part.itertuples(), start=1):
            ds = clean_field(r.dataset)
            id_in_ds[ds] = id_in_ds.get(ds, 0) + 1
            dom = domain_of(r.dataset, r.source_name)
            name = (f"{num:0{width}d}_{ds}_id_{id_in_ds[ds]}_{clean_field(dom)}"
                    f"_tr_{int(r.train_len)}_1st_{int(r.first_anomaly)}.csv")
            os.replace(r.tmp, out / "raw" / kind / name)
            rows.append({"file_name": name, "kind": kind, "dataset": r.dataset, "domain": dom,
                         "source_name": r.source_name, "source_path": r.source_path,
                         "length": int(r.length), "channels": int(r.channels), "train_len": int(r.train_len),
                         "n_dropped_nan": int(r.n_dropped_nan),
                         "n_dropped_channels": int(r.n_dropped_channels)})
    shutil.rmtree(out / "_tmp")

    source_map = pd.DataFrame(rows)
    source_map.to_csv(out / "_source_map.csv", index=False)
    excluded.sort_values(["dataset", "source_name"]).to_csv(out / "_excluded.csv", index=False)

    # No benchmark but TSB-AD has a tuning split, so everything is Eval and
    # Label is empty.
    for kind, letter in [("uni", "U"), ("multi", "M")]:
        part = source_map[source_map.kind == kind] if len(source_map) else source_map
        ev = pd.DataFrame({"file_name": part.get("file_name", []), "domain_name": part.get("domain", [])})
        ev.to_csv(out / "splits" / f"{letter}-Eval.csv", index=False)
        pd.DataFrame(columns=["file_name", "domain_name"]).to_csv(
            out / "splits" / f"{letter}-Label.csv", index=False)

    print(f"{benchmark}: wrote {len(source_map)} series "
          f"({(source_map.kind == 'uni').sum()} uni, {(source_map.kind == 'multi').sum()} multi), "
          f"excluded {len(excluded)}")
    if len(excluded):
        print(excluded.reason.str.replace(r":.*", "", regex=True).value_counts().to_string())
    unknown = source_map[source_map.domain == "Unknown"].dataset.unique()
    if len(unknown):
        print("datasets with no domain:", list(unknown))
    return source_map
