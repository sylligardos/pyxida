"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Run TSB-AD's detectors on any benchmark in the common format.

Scores come from the TSB-AD package itself (github.com/thedatumorg/TSB-AD,
cloned in ~/Documents/TSB-AD, installed in the `tsbad-run` env), with its tuned
hyperparameters (Optimal_{Uni,Multi}_algo_HP_dict), so a detector means the same
thing on every benchmark. Writes, in the benchmark's own folder:

    scores/<kind>/<Detector>/<file>.npy
    runtime/<kind>/<Detector>.csv      File Name, Model Name, Time Cost, Length

Unlike TSB-AD's own Run_Detector_U.py this reads the train split from the
parser (so it works for any benchmark), skips semi-supervised detectors on
series with no train split (tr_0), and never stores a failure as a score: the
wrapper returns an error *string* when a detector crashes, which is logged.

Series already scored are skipped, so a rerun resumes.

Run:
    conda run -n tsbad-run python src/metrics/run_detectors.py \\
        --benchmark tab --kind uni --datasets NAB YAHOO --detectors SR IForest
"""

import os

# One thread per process: parallelism is across (series, detector) jobs.
# NUMBA matters too: MatrixProfile (stumpy) otherwise starts a thread per core
# in every worker.
for var in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS"]:
    os.environ.setdefault(var, "1")

import argparse  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from tqdm import tqdm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tsbadparser import TSBADParser  # noqa: E402


def _job(args):
    raw_path, out_path, filename, detector, kind, train_len = args
    import torch
    torch.set_num_threads(1)
    from TSB_AD.HP_list import Optimal_Multi_algo_HP_dict, Optimal_Uni_algo_HP_dict
    from TSB_AD.model_wrapper import (Semisupervise_AD_Pool, Unsupervise_AD_Pool,
                                      run_Semisupervise_AD, run_Unsupervise_AD)

    hp = (Optimal_Uni_algo_HP_dict if kind == "uni" else Optimal_Multi_algo_HP_dict).get(detector, {})
    df = pd.read_csv(raw_path / filename)
    data = df.iloc[:, :-1].to_numpy(dtype=float)

    tic = time.perf_counter()
    if detector in Semisupervise_AD_Pool:
        if train_len == 0:
            return filename, detector, None, "skipped: no train split"
        out = run_Semisupervise_AD(detector, data[:train_len], data, **hp)
    elif detector in Unsupervise_AD_Pool:
        out = run_Unsupervise_AD(detector, data, **hp)
    else:
        return filename, detector, None, "unknown detector"
    elapsed = time.perf_counter() - tic

    if not isinstance(out, np.ndarray):
        return filename, detector, None, f"failed: {str(out)[:200]}"
    out = np.asarray(out, dtype=np.float64).ravel()
    if len(out) != len(data):
        return filename, detector, None, f"failed: {len(out)} scores for {len(data)} points"
    np.save(out_path / detector / filename.replace(".csv", ".npy"), out)
    return filename, detector, elapsed, len(data)


def run(benchmark, kind, detectors, datasets=None, workers=14):
    parser = TSBADParser(benchmark=benchmark, kind=kind)
    meta = parser.meta if not datasets else parser.meta[parser.meta.dataset.isin(datasets)]
    if meta.empty:
        print(f"{benchmark}/{kind}: no series for {datasets}")
        return
    for det in detectors:
        (parser.scores_path / det).mkdir(parents=True, exist_ok=True)

    jobs = [(parser.raw_path, parser.scores_path, r.filename, det, kind, int(r.train_length))
            for det in detectors for r in meta.itertuples()
            if not (parser.scores_path / det / r.filename.replace(".csv", ".npy")).exists()]
    results = []
    with Pool(workers) as pool:
        for res in tqdm(pool.imap_unordered(_job, jobs), total=len(jobs), desc=f"{benchmark}/{kind}"):
            results.append(res)

    ok = [r for r in results if r[2] is not None]
    bad = [r for r in results if r[2] is None]
    runtime_dir = parser.path / "runtime" / kind
    runtime_dir.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame([{"File Name": f, "Model Name": d, "Time Cost": t, "Length": n} for f, d, t, n in ok])
    for det, part in new.groupby("Model Name") if len(new) else []:
        path = runtime_dir / f"{det}.csv"
        if path.exists():
            old = pd.read_csv(path)
            part = pd.concat([old[~old["File Name"].isin(part["File Name"])], part])
        part.sort_values("File Name").to_csv(path, index=False)

    log = parser.path / "_run_log.csv"
    pd.DataFrame([{"kind": kind, "file_name": f, "detector": d, "problem": msg} for f, d, _, msg in bad],
                 columns=["kind", "file_name", "detector", "problem"]).to_csv(
        log, mode="a", header=not log.exists(), index=False)
    print(f"{benchmark}/{kind}: {len(ok)} scored, {len(bad)} failed or skipped "
          f"({len(meta)} series x {len(detectors)} detectors; failures in _run_log.csv)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--kind", choices=["uni", "multi"], required=True)
    ap.add_argument("--detectors", nargs="+", required=True)
    ap.add_argument("--datasets", nargs="*", default=None)
    # Multivariate detectors build window matrices of several GB per series
    # (PCA on SMD: ~6 GB each); 14 of them at once exhausted 62 GB of RAM.
    ap.add_argument("--workers", type=int, default=None, help="default: 14 uni, 3 multi")
    args = ap.parse_args()
    args.workers = args.workers or (14 if args.kind == "uni" else 3)
    run(args.benchmark, args.kind, args.detectors, args.datasets, args.workers)
