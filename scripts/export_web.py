"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Export a benchmark for the web demo (web/), as small static files.

The demo never reads the benchmark itself: it reads what this script writes,
locally from data/web/ and later from object storage, the same paths.

    data/web/<benchmark>/<kind>/summary.json          headline numbers, per-series lengths and anomaly counts
    data/web/<benchmark>/<kind>/series/<file>.json    one series: values and label runs
    data/web/<benchmark>/<kind>/landscape.json        AUC-PR and VUS-PR of every detector on every series
    data/web/<benchmark>/<kind>/scores/<file>/<Detector>.u16   one detector's score, min-max scaled to uint16
    data/web/<benchmark>/<kind>/redundancy.json       pair agreement (weighted tau) and top-k vs best-k (TSB-AD univariate only)

Run, from the repo root:
    python scripts/export_web.py --benchmark tsb-ad --kind uni
    python scripts/export_web.py --benchmark tsb-uad --kind uni
    python scripts/export_web.py --benchmark timeeval --kind uni --all   # a toy example: only the scored series
    python scripts/export_web.py --benchmark tsb-ad --kind uni --series 001_NAB_id_1_Facility_tr_1007_1st_2014.csv   # one series and its scores, no tables
    python scripts/export_web.py --benchmark tsb-ad --kind uni --all      # every series and every score
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.parser import TSBADParser  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "game"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from build_summary import EXCLUDED as TSB_AD_EXCLUDED  # noqa: E402
from pack import round_values as sig  # noqa: E402
from scoring import labels_to_ranges as label_runs  # noqa: E402

OUT_ROOT = REPO_ROOT / "data" / "web"
TSB_AD_SUMMARY = REPO_ROOT / "data" / "benchmark_summary.json"

LABELS = {"tsb-ad": "TSB-AD", "tsb-uad": "TSB-UAD", "timeeval": "TimeEval", "tab": "TAB", "mtsbench": "mTSBench"}

# Toy examples: a few fast detectors run on a few datasets
# (scripts/run_examples.sh). Only the series they scored are exported.
TOY = {"timeeval", "tab", "mtsbench"}

# Detectors whose scores are unusable on part of the benchmark (the list is
# scripts/build_summary.py's); they are not counted and not exported.
EXCLUDED = {"tsb-ad": TSB_AD_EXCLUDED}

# The series the Intro draws: a short NAB series, the same one everywhere.
DEMO = {"tsb-ad": "001_NAB_id_1_Facility_tr_1007_1st_2014.csv"}


def per_series(parser: TSBADParser) -> tuple[dict, dict]:
    """Length and anomaly-event count of every series. TSB-AD's are already
    in the repo; anything else is read from the label columns, one file at
    a time."""
    if parser.is_tsb_ad() and TSB_AD_SUMMARY.exists():
        s = json.loads(TSB_AD_SUMMARY.read_text()).get(parser.kind)
        if s and "lengths" in s and "anomalies" in s:
            return s["lengths"], s["anomalies"]
    import pandas as pd
    lengths, anomalies = {}, {}
    for f in parser.meta.filename:
        y = pd.read_csv(parser.raw_path / f, usecols=lambda c: c == "Label")["Label"].to_numpy()
        lengths[f], anomalies[f] = int(len(y)), len(label_runs(y))
    return lengths, anomalies


def demo_series(parser: TSBADParser, lengths: dict) -> str | None:
    fixed = DEMO.get(parser.benchmark)
    files = set(parser.meta.filename)
    if fixed in files:
        return fixed
    pool = parser.meta[parser.meta.dataset == "NAB"]
    pool = pool if len(pool) else parser.meta
    if not len(pool):
        return None
    return min(pool.filename, key=lambda f: lengths.get(f, 10 ** 12))


def export_summary(parser: TSBADParser, out: Path) -> dict:
    lengths, anomalies = per_series(parser)
    detectors = [d for d in parser.get_detectors() if d not in EXCLUDED.get(parser.benchmark, [])]
    meta = parser.meta
    channels = {}
    if parser.kind == "multi":   # the Workbench warns before loading a big series
        import pandas as pd
        channels = {f: len(pd.read_csv(parser.raw_path / f, nrows=0).columns) - 1 for f in meta.filename}
    summary = {
        "benchmark": parser.benchmark,
        "label": LABELS.get(parser.benchmark, parser.benchmark),
        "kind": parser.kind,
        "toy": parser.benchmark in TOY,
        "n_series": int(len(meta)),
        "n_datasets": int(meta.dataset.nunique()),
        "n_detectors": len(detectors),
        "n_anomalies": int(sum(anomalies.values())),
        "n_points": int(sum(lengths.values())),
        "detectors": detectors,
        "demo_series": demo_series(parser, lengths),
        "series": [
            {"file": r.filename, "dataset": r.dataset, "type": r.entity_type,
             "n": lengths.get(r.filename), "anomalies": anomalies.get(r.filename),
             **({"channels": channels[r.filename]} if channels else {})}
            for r in meta.itertuples()
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, separators=(",", ":")))
    return summary


def export_series(parser: TSBADParser, out: Path, filename: str, series=None, labels=None) -> Path:
    if series is None:
        names, ts, lb = parser.load_timeseries(filename=[filename])
        series, labels = ts[0], lb[0]
    doc = {"file": filename, "n": int(len(series)), "labels": label_runs(labels)}
    if series.ndim == 2 and series.shape[1] > 1:
        import pandas as pd
        header = [str(c) for c in pd.read_csv(parser.raw_path / filename, nrows=0).columns[:-1]]
        doc["n_channels"] = int(series.shape[1])
        doc["channels"] = [{"name": header[c] if c < len(header) else f"C{c}", "values": sig(series[:, c])}
                           for c in range(series.shape[1])]
    else:
        doc["values"] = sig(series[:, 0] if series.ndim == 2 else series)
    (out / "series").mkdir(parents=True, exist_ok=True)
    path = out / "series" / (Path(filename).stem + ".json")
    path.write_text(json.dumps(doc, separators=(",", ":")))
    return path


def export_scores(parser: TSBADParser, out: Path, filename: str, detectors: list[str], n: int) -> int:
    """One uint16 file per detector: the score min-max scaled to 0..65535.
    A lane has its own scale anyway, so the shape is all the page draws.
    Scores of the wrong length are skipped, as the Workbench skips them."""
    folder = out / "scores" / Path(filename).stem
    folder.mkdir(parents=True, exist_ok=True)
    written = 0
    for d in detectors:
        src = parser.scores_path / d / (Path(filename).stem + ".npy")
        if not src.exists():
            continue
        x = np.load(src).astype(np.float64).ravel()
        if len(x) != n or not np.isfinite(x).all():
            continue
        lo, hi = x.min(), x.max()
        q = np.zeros(n, dtype="<u2") if hi <= lo else np.round((x - lo) / (hi - lo) * 65535).astype("<u2")
        (folder / f"{d}.u16").write_bytes(q.tobytes())
        written += 1
    return written


def export_all(parser: TSBADParser, out: Path, summary: dict) -> None:
    """Every series and every score. Loads one series at a time: the whole
    benchmark does not fit in memory with its scores."""
    detectors = summary["detectors"]
    files = [s["file"] for s in summary["series"]]
    for i, f in enumerate(files, 1):
        ts, lb = parser._load_single_csv(parser.raw_path / f)
        export_series(parser, out, f, ts, lb)
        k = export_scores(parser, out, f, detectors, len(ts))
        print(f"  [{i}/{len(files)}] {f}: {len(ts)} points, {k} scores", flush=True)


VUS_BUFFER = 10
DIVERGENCE = REPO_ROOT / "data" / "divergence"


def metric_tables(parser: TSBADParser, detectors: list[str]):
    """AUC-PR and VUS-PR per series per detector, as frames indexed by file.

    VUS-PR at buffer 10 is in the combination tables (TSB-AD univariate, k=1
    rows; detectors that emit a constant are dropped there). Elsewhere the
    metrics the benchmark ships, at the nearest buffer they have."""
    import re
    import pandas as pd
    metrics = parser.load_metrics(models=detectors)
    if metrics.empty or "File Name" not in metrics.columns:
        return None, None, None
    metrics = metrics[metrics["File Name"].isin(set(parser.meta.filename))]
    aucpr = (metrics.pivot_table(index="File Name", columns="Model Name", values="AUC-PR")
             if "AUC-PR" in metrics.columns else pd.DataFrame())
    buffers = sorted(int(m.group(1)) for c in metrics.columns
                     for m in [re.match(r"VUS-PR \(L: (\d+)\)", c)] if m)

    roster = DIVERGENCE / f"combos_{parser.kind}_detectors.parquet"
    shards = [p for p in sorted(DIVERGENCE.glob(f"combos_{parser.kind}_*.parquet")) if p != roster]
    if parser.is_tsb_ad() and roster.exists() and shards:
        names = pd.read_parquet(roster).detector.tolist()
        parts = []
        for shard in shards:
            f = pd.read_parquet(shard, columns=["filename", "k", "d0", "n_constant", f"vus_{VUS_BUFFER}"])
            f = f[(f.k == 1) & (f.n_constant == 0)]
            parts.append(pd.DataFrame({"file": f.filename.to_numpy(), "det": [names[i] for i in f.d0],
                                       "vus": f[f"vus_{VUS_BUFFER}"].to_numpy()}))
        vus = pd.concat(parts).pivot_table(index="file", columns="det", values="vus")
        buffer = VUS_BUFFER
    elif buffers:
        buffer = min(buffers, key=lambda b: abs(b - VUS_BUFFER))
        vus = metrics.pivot_table(index="File Name", columns="Model Name", values=f"VUS-PR (L: {buffer})")
    else:
        vus, buffer = pd.DataFrame(), None
    return aucpr, vus, buffer


def export_landscape(parser: TSBADParser, out: Path, summary: dict) -> Path | None:
    import math
    detectors = summary["detectors"]
    aucpr, vus, buffer = metric_tables(parser, detectors)
    if aucpr is None:
        print("  landscape      no metrics in this benchmark, skipped")
        return None

    def row_of(table, file):
        if table.empty or file not in table.index:
            return [None] * len(detectors)
        r = table.loc[file]
        return [None if d not in r.index or math.isnan(r[d]) else round(float(r[d]), 4) for d in detectors]

    rows = [{**s, "aucpr": row_of(aucpr, s["file"]), "vus": row_of(vus, s["file"])}
            for s in summary["series"]]
    rows = [r for r in rows if any(v is not None for v in r["vus"] + r["aucpr"])]
    doc = {"detectors": detectors,
           "metrics": {"aucpr": {"label": "AUC-PR"}, "vus": {"label": f"VUS-PR, buffer {buffer}" if buffer is not None else "VUS-PR", "buffer": buffer}},
           "rows": rows}
    path = out / "landscape.json"
    path.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"  landscape      {len(rows)} series scored, VUS-PR at buffer {buffer}")
    return path


def _tau_one(args) -> np.ndarray:
    """Every pair's weighted tau on one series; a worker of weighted_tau."""
    from scipy.stats import weightedtau
    scores_path, file, detectors = args
    x = []
    for d in detectors:
        src = scores_path / d / (Path(file).stem + ".npy")
        v = np.load(src).astype(np.float64).ravel() if src.exists() else None
        x.append(v if v is not None and np.isfinite(v).all() and v.max() > v.min() else None)
    lens = Counter(len(v) for v in x if v is not None).most_common(1)
    nd = len(detectors)
    m = np.full((nd, nd), np.nan)
    for a in range(nd):
        for b in range(a + 1, nd):
            if x[a] is not None and x[b] is not None and len(x[a]) == len(x[b]) == lens[0][0]:
                m[a, b] = m[b, a] = weightedtau(x[a], x[b]).statistic
    return m


def weighted_tau(parser: TSBADParser, files: list[str], detectors: list[str]) -> dict:
    """Per series, the weighted Kendall tau (Vigna 2015, scipy's default
    hyperbolic weights) of every pair's raw scores: rank correlation where
    the top of the ranking, the likely anomalies, counts most. NaN where a
    score is missing or constant. Slow (tens of minutes on one core), so
    spread over the cores and cached next to the study's tables."""
    from concurrent.futures import ProcessPoolExecutor
    name = f"weighted_tau_{parser.kind}.npz" if parser.is_tsb_ad() else f"weighted_tau_{parser.benchmark}_{parser.kind}.npz"
    cache = DIVERGENCE / name
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        if list(z["files"]) == files and list(z["detectors"]) == detectors:
            print(f"  weighted tau   cached, {cache.name}")
            return dict(zip(files, z["tau"]))
    out = []
    with ProcessPoolExecutor() as pool:
        jobs = [(parser.scores_path, f, detectors) for f in files]
        for i, m in enumerate(pool.map(_tau_one, jobs, chunksize=4), 1):
            out.append(m)
            if i % 50 == 0 or i == len(files):
                print(f"  weighted tau   {i}/{len(files)}", flush=True)
    np.savez_compressed(cache, files=np.array(files), detectors=np.array(detectors), tau=np.stack(out))
    return dict(zip(files, out))


EXAMPLES = 3   # per dataset and pair, the series with the highest weighted tau


def export_redundancy(parser: TSBADParser, out: Path, summary: dict) -> Path | None:
    """The Redundancy page's tables: every pair's agreement, the weighted
    Kendall tau of their scores, and, where the exhaustive search exists
    (TSB-AD univariate), per series what the top-k by rank scored against
    the best k-set."""
    import warnings
    import pandas as pd
    roster = DIVERGENCE / f"combos_{parser.kind}_detectors.parquet"
    shards = [p for p in sorted(DIVERGENCE.glob(f"combos_{parser.kind}_*.parquet")) if p != roster]
    if not (out / "landscape.json").exists():
        return None
    search = parser.is_tsb_ad() and roster.exists() and bool(shards)
    detectors = summary["detectors"]
    nd = len(detectors)
    land = json.loads((out / "landscape.json").read_text())

    # Agreement: weighted tau per series, averaged per dataset, and a global
    # matrix that averages the datasets (YAHOO holds a third of the series
    # and would otherwise decide it alone). Per series: the pairs among that
    # series' top five against every pair.
    tau = weighted_tau(parser, [r["file"] for r in land["rows"]], detectors)
    by_ds: dict[str, list] = {}
    for r in land["rows"]:
        by_ds.setdefault(r["dataset"], []).append(tau[r["file"]])

    def nanmean(ms):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN cells stay NaN
            return np.nanmean(np.stack(ms), axis=0)

    def clean(mat):
        return [[None if np.isnan(v) else round(float(v), 3) for v in row] for row in mat]

    per_dataset = {ds: nanmean(ms) for ds, ms in by_ds.items()}
    global_mat = nanmean(list(per_dataset.values()))
    agree = {"global": clean(global_mat), "datasets": {ds: clean(m) for ds, m in per_dataset.items()},
             "n": {ds: len(ms) for ds, ms in by_ds.items()}}

    # Concrete cases per dataset: for every pair, the series where it agrees
    # most. Compact: the dataset's file names once, then per pair "a-b"
    # (a < b) a list of [file index, tau].
    iu = np.triu_indices(nd, 1)
    examples = {}
    for ds in by_ds:
        files = [r["file"] for r in land["rows"] if r["dataset"] == ds]
        stack = np.stack([tau[f] for f in files])
        pairs = {}
        for a, b in zip(*iu):
            col = stack[:, a, b]
            idx = [int(i) for i in np.argsort(-np.nan_to_num(col, nan=-np.inf), kind="stable") if np.isfinite(col[i])][:EXAMPLES]
            if idx:
                pairs[f"{a}-{b}"] = [[i, round(float(col[i]), 2)] for i in idx]
        examples[ds] = {"files": files, "pairs": pairs}

    rank_on = {r["file"]: np.argsort([-(v if v is not None else -1.0) for v in r["vus"]]) for r in land["rows"]}
    series_agree = {}
    for file, m in tau.items():
        top = rank_on[file][:5]
        mask = np.zeros((nd, nd), dtype=bool)
        mask[np.ix_(top, top)] = True
        t, a = m[iu][mask[iu]], m[iu]
        if np.isfinite(t).any() and np.isfinite(a).any():
            series_agree[file] = {"top5": round(float(np.nanmean(t)), 3), "all": round(float(np.nanmean(a)), 3)}

    # Top-k by rank against the best k-set, from the combination search.
    # Without it, each series' best single detector only.
    rows = []
    if not search:
        for r in land["rows"]:
            vals = [(v, d) for v, d in zip(r["vus"], detectors) if v is not None]
            if vals:
                v, d = max(vals)
                rows.append({"file": r["file"], "dataset": r["dataset"], "best1": v, "best1_det": d,
                             "agree": series_agree.get(r["file"])})
    names = pd.read_parquet(roster).detector.tolist() if search else []
    vcol = f"vus_{VUS_BUFFER}"
    for shard in (shards if search else []):
        f = pd.read_parquet(shard, columns=["filename", "dataset", "k", "d0", "d1", "d2", "n_constant", vcol])
        f = f[f.n_constant == 0]
        for file, g in f.groupby("filename"):
            solo = g[g.k == 1].sort_values(vcol, ascending=False)
            if len(solo) < 3:
                continue
            solo_names = [names[i] for i in solo.d0]
            row = {"file": file, "dataset": g.dataset.iloc[0],
                   "best1": round(float(solo[vcol].iloc[0]), 4), "best1_det": solo_names[0]}
            for k, cols in ((2, ["d0", "d1"]), (3, ["d0", "d1", "d2"])):
                gk = g[g.k == k]
                if gk.empty:
                    continue
                top = frozenset(int(i) for i in solo.d0.iloc[:k])
                sets = [frozenset(int(x) for x in t) for t in gk[cols].to_numpy()]
                vus = gk[vcol].to_numpy()
                top_vus = next((float(v) for s, v in zip(sets, vus) if s == top), None)
                j = int(vus.argmax())
                row[f"k{k}"] = {
                    "top": None if top_vus is None else round(top_vus, 4),
                    "top_dets": solo_names[:k],
                    "best": round(float(vus[j]), 4),
                    "best_dets": [names[i] for i in sorted(sets[j])],
                }
            row["agree"] = series_agree.get(file)
            rows.append(row)

    vus_mean = []
    for i, d in enumerate(detectors):
        vals = [r["vus"][i] for r in land["rows"] if r["vus"][i] is not None]
        vus_mean.append(round(sum(vals) / len(vals), 4) if vals else None)
    doc = {"buffer": land["metrics"]["vus"].get("buffer") if not search else VUS_BUFFER, "detectors": detectors, "mean_vus": vus_mean, "agree": agree, "examples": examples, "series": rows}
    path = out / "redundancy.json"
    path.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"  redundancy     {len(rows)} series, {len(series_agree)} with agreement, {len(per_dataset)} datasets"
          f"{'' if search else ', no exhaustive search'}")
    return path


def main():
    ap = argparse.ArgumentParser(description="Export a benchmark for web/.")
    ap.add_argument("--benchmark", default="tsb-ad")
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"])
    ap.add_argument("--series", nargs="*", default=None,
                    help="series to export (default: the demo series)")
    ap.add_argument("--all", action="store_true", help="every series and every score")
    args = ap.parse_args()

    parser = TSBADParser(benchmark=args.benchmark, kind=args.kind)
    if parser.benchmark in TOY:
        scored = set(parser.load_metrics().get("File Name", []))
        parser.meta = parser.meta[parser.meta.filename.isin(scored)].reset_index(drop=True)
    out = OUT_ROOT / args.benchmark / args.kind
    summary = export_summary(parser, out)
    for key in ("n_series", "n_datasets", "n_detectors", "n_anomalies", "n_points", "demo_series"):
        print(f"  {key:14s} {summary[key]}")

    if args.series is None:
        # The tables, not when a single series is asked for: they read the
        # whole study (minutes) and do not change.
        export_landscape(parser, out, summary)
        export_redundancy(parser, out, summary)

    if args.all:
        export_all(parser, out, summary)
    else:
        wanted = args.series if args.series is not None else [summary["demo_series"]]
        for f in [w for w in wanted if w]:
            ts, lb = parser._load_single_csv(parser.raw_path / f)
            path = export_series(parser, out, f, ts, lb)
            k = export_scores(parser, out, f, summary["detectors"], len(ts))
            print(f"  wrote {path} and {k} scores")
    print(f"\n  {out}")


if __name__ == "__main__":
    main()
