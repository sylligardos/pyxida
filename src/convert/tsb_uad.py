"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: TSB-UAD (Paparrizos et al., VLDB 2022) -> common format, scores included.

Source, as shipped (moved here from the MSAD-E project):
    _original/raw/<dataset>/<name>.out                   value,label  (no header)
    _original/scores/<dataset>/<Det>/score/<name>.out    one score per line

TSB-UAD is univariate and has no train split, so every series is tr_0. It is
the only benchmark besides TSB-AD that ships detector scores, so they are
converted too: scores/uni/<Det>/<file>.npy. The shipped scores are rounded to
two decimals; they are kept as they are.

Run:
    python src/convert/tsb_uad.py
"""

import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from common import BENCHMARKS_ROOT, Loaded, Spec, convert  # noqa: E402

NAME = "tsb-uad"
SRC = BENCHMARKS_ROOT / NAME / "_original"


def list_specs() -> list:
    return [Spec(dataset=p.parent.name, source_name=p.name, source_path=str(p.relative_to(SRC)), kind="uni")
            for p in sorted((SRC / "raw").glob("*/*.out"))]


def load(spec: Spec) -> Loaded:
    df = pd.read_csv(SRC / spec.source_path, header=None)
    return Loaded(values=df.iloc[:, 0].values, labels=df.iloc[:, 1].values, train_len=0, columns=["Data"])


def _score_one(args):
    src, dst, length = args
    s = pd.read_csv(src, header=None).iloc[:, 0].values.astype(np.float64)
    if len(s) != length:
        return f"{src}: {len(s)} scores for {length} points"
    np.save(dst, s)
    return None


def convert_scores(source_map: pd.DataFrame, workers: int = 12) -> None:
    out = BENCHMARKS_ROOT / NAME / "scores" / "uni"
    if out.exists():
        import shutil
        shutil.rmtree(out)
    detectors = sorted({p.parent.name for p in (SRC / "scores").glob("*/*/score")})
    jobs = []
    for det in detectors:
        (out / det).mkdir(parents=True)
        for r in source_map.itertuples():
            # NaN rows were dropped from the series; scores would no longer align
            if r.n_dropped_nan:
                continue
            src = SRC / "scores" / r.dataset / det / "score" / r.source_name
            if src.exists():
                jobs.append((src, out / det / (Path(r.file_name).stem + ".npy"), r.length))
    with Pool(workers) as pool:
        problems = [p for p in tqdm(pool.imap_unordered(_score_one, jobs, chunksize=32),
                                    total=len(jobs), desc="scores") if p]
    print(f"scores: {len(jobs) - len(problems)} files for {len(detectors)} detectors, "
          f"{len(problems)} skipped (length mismatch)")
    for p in problems[:10]:
        print("  ", p)


if __name__ == "__main__":
    smap = convert(NAME, list_specs(), load)
    convert_scores(smap)
