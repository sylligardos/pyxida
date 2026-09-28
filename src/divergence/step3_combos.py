"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Step 3 of the divergence study -- VUS of every small detector combination.

One row per (series, detector combination): the VUS-PR of the averaged score,
at every buffer from 0 to 256. That table answers the question the demo is
built around -- is the best pair the top-2, the least correlated pair, or the
max-coverage pair? Any answer is a result.

Run (from the ffvus environment, which has torch+CUDA):
    conda run -n ffvus python src/divergence/step3_combos.py --dataset NAB
    conda run -n ffvus python src/divergence/step3_combos.py --max-k 3
    conda run -n ffvus python src/divergence/step3_combos.py --test

Two data defects force preprocessing, both measured on TSB-AD-U:

  SR is not min-max normalised. Its median maximum is 0.303 and only 2.5% of
  its series reach 1.0, while 26 of the 30 detectors are exactly [0, 1] on
  every series. Averaging raw scores would silently down-weight SR, so every
  score is re-scaled to [0, 1] per (series, detector) first. That is a no-op
  for the detectors already normalised.

  POLY is constant on 40% of series. Adding a constant to an average shifts
  every point equally, so it cannot change the ranking and the combination
  scores exactly what it would have scored without it. Such combinations are
  flagged (n_constant) so they can be read as the smaller set they really are.
"""

import argparse
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import OUT_ROOT, get_detectors, get_parser, list_series

FFVUS_SRC = Path.home() / "Documents" / "ff-vus" / "src"

SLOPE_SIZE = 256          # VUS buffers 0..256
N_BUFFERS = SLOPE_SIZE + 1
MAX_K = 3


def load_vus(device: str = "cuda"):
    """FF-VUS, GPU if available. Falls back to the numpy version on CPU.

    Kept behind a function so the module imports fine in the tsbad env, which
    has no torch -- only the actual computation needs ffvus.
    """
    if str(FFVUS_SRC) not in sys.path:
        sys.path.insert(0, str(FFVUS_SRC))

    if device == "cpu":
        from vus.vus_numpy import VUSNumpy
        metric = VUSNumpy(slope_size=SLOPE_SIZE, step=1, metric="vus_pr",
                          cumulative=True)
        return metric, "cpu"

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("--device cuda but torch reports no CUDA device")
    from vus.vus_torch import VUSTorch
    return VUSTorch(slope_size=SLOPE_SIZE, step=1, cumulative=True,
                    device="cuda"), "cuda"


def vus_curve(metric, label: np.ndarray, score: np.ndarray) -> np.ndarray:
    """VUS-PR at every buffer 0..256, as a float32 vector of length 257.

    compute() is wrapped in FF-VUS' @time_it, so it returns
    ((vus, time_analysis), elapsed) -- two layers of bookkeeping around the
    only thing we want. Unwrap until we reach the array.
    """
    out = metric.compute(label, score)
    while isinstance(out, (tuple, list)):
        out = out[0]
    arr = out.detach().cpu().numpy() if hasattr(out, "detach") else np.asarray(out)
    return np.asarray(arr, dtype=np.float32).ravel()


def normalise(score: np.ndarray) -> tuple[np.ndarray, bool]:
    """Re-scale a score vector to [0, 1]. Returns (score, is_constant).

    A constant vector has no range to scale by, so it is returned as zeros --
    which is what it already means: no point ranks above any other.
    """
    score = np.asarray(score, dtype=np.float64).ravel()
    lo, hi = score.min(), score.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros_like(score), True
    return (score - lo) / (hi - lo), False


def load_series_scores(parser, filename: str, detectors: list[str]):
    """Labels plus one normalised score vector per detector, all length T.

    Returns (labels, scores, constant_flags) or None when the series cannot be
    used -- no anomaly to score against, or a detector missing entirely.
    """
    _, series_list, label_list = parser.load_timeseries(filename=[filename])
    labels = np.asarray(label_list[0]).ravel().astype(np.int8)
    if labels.sum() == 0 or labels.sum() == len(labels):
        return None

    scores, constant = [], []
    for detector in detectors:
        kept, loaded, _ = parser.load_scores(
            detectors=[detector], filenames=[filename],
            drop_missing=False, return_filenames=True,
        )
        if not loaded or len(loaded[0]) == 0:
            return None
        vector, is_constant = normalise(loaded[0][0])
        if len(vector) != len(labels):
            return None
        scores.append(vector)
        constant.append(is_constant)

    return labels, np.stack(scores), np.array(constant)


def combos_for_series(metric, labels, scores, constant, max_k):
    """VUS curve for every detector combination of size 1..max_k.

    The averaged score is built incrementally from a running sum so a triplet
    costs one extra add rather than a fresh mean over three vectors.
    """
    n_detectors = len(scores)
    rows, curves = [], []

    for k in range(1, max_k + 1):
        for combo in itertools.combinations(range(n_detectors), k):
            combined = scores[list(combo)].mean(axis=0)
            curves.append(vus_curve(metric, labels, combined))
            padded = list(combo) + [-1] * (MAX_K - k)
            rows.append((k, *padded[:MAX_K], int(constant[list(combo)].sum())))

    return rows, curves


def build_table(parser, filenames, detectors, metric, max_k):
    """One row per (series, combination). Returns (DataFrame, skipped)."""
    meta = parser.meta.set_index("filename")["dataset"].to_dict()
    frames, skipped = [], []

    for filename in tqdm(filenames, desc="Series"):
        loaded = load_series_scores(parser, filename, detectors)
        if loaded is None:
            skipped.append(filename)
            continue
        labels, scores, constant = loaded

        rows, curves = combos_for_series(metric, labels, scores, constant, max_k)
        frame = pd.DataFrame(rows, columns=["k", "d0", "d1", "d2", "n_constant"])
        frame.insert(0, "filename", filename)
        frame.insert(1, "dataset", meta.get(filename, "?"))

        # Built in one concat rather than 257 assignments: inserting columns one
        # at a time re-copies the block each time and fragments the frame.
        vus = pd.DataFrame(np.stack(curves),
                           columns=[f"vus_{b}" for b in range(N_BUFFERS)])
        frames.append(pd.concat([frame, vus], axis=1))

    if not frames:
        return pd.DataFrame(), skipped

    table = pd.concat(frames, ignore_index=True)
    for column in ["k", "d0", "d1", "d2", "n_constant"]:
        table[column] = table[column].astype(np.int8)
    for column in ["filename", "dataset"]:
        table[column] = table[column].astype("category")
    return table, skipped


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def run_tests(device: str) -> bool:
    """Synthetic checks on the parts that can silently produce plausible junk."""
    metric, _ = load_vus(device)
    checks, failures = [], []

    def check(name, condition, detail=""):
        checks.append((name, bool(condition), detail))
        if not condition:
            failures.append(name)

    rng = np.random.default_rng(0)
    T = 2000
    labels = np.zeros(T, dtype=np.int8)
    labels[500:530] = 1
    labels[1200:1210] = 1

    perfect = labels.astype(float) + rng.normal(0, 1e-3, T)
    random_score = rng.random(T)
    constant = np.zeros(T)

    v_perfect = vus_curve(metric, labels, perfect)
    v_random = vus_curve(metric, labels, random_score)

    check("curve length is 257", len(v_perfect) == N_BUFFERS, f"got {len(v_perfect)}")
    check("perfect detector scores high", v_perfect[0] > 0.9, f"{v_perfect[0]:.3f}")
    check("random detector scores low", v_random[0] < 0.2, f"{v_random[0]:.3f}")
    check("perfect beats random at every buffer",
          bool(np.all(v_perfect > v_random)))

    # A constant added to an average cannot change the ranking, so it cannot
    # change VUS. This is the POLY case and the reason for the n_constant flag.
    mixed = np.mean([normalise(random_score)[0], normalise(constant)[0]], axis=0)
    v_mixed = vus_curve(metric, labels, mixed)
    v_solo = vus_curve(metric, labels, normalise(random_score)[0])
    check("constant partner leaves VUS unchanged",
          np.allclose(v_mixed, v_solo, atol=1e-6),
          f"max diff {np.abs(v_mixed - v_solo).max():.2e}")

    # Re-normalisation must not change a detector's own VUS -- VUS is
    # rank-based, and an affine rescale preserves ranks.
    compressed = random_score * 0.3
    v_compressed = vus_curve(metric, labels, normalise(compressed)[0])
    check("re-normalisation preserves solo VUS",
          np.allclose(v_compressed, v_solo, atol=1e-6),
          f"max diff {np.abs(v_compressed - v_solo).max():.2e}")

    # ... but it does change the AVERAGE, which is the whole point of doing it.
    raw_avg = np.mean([random_score * 0.3, perfect], axis=0)
    norm_avg = np.mean([normalise(random_score * 0.3)[0], normalise(perfect)[0]], axis=0)
    check("re-normalisation changes the combined score",
          not np.allclose(raw_avg, norm_avg, atol=1e-6))

    check("normalise flags a constant vector", normalise(constant)[1])

    # Already spanning exactly [0, 1] -- the case for 26 of the 30 detectors.
    spanning = (random_score - random_score.min()) / np.ptp(random_score)
    check("normalise leaves [0,1] alone",
          np.allclose(normalise(spanning)[0], spanning, atol=1e-12),
          f"max diff {np.abs(normalise(spanning)[0] - spanning).max():.2e}")

    combos = list(itertools.combinations(range(30), 2))
    check("30 detectors give 435 pairs", len(combos) == 435, f"{len(combos)}")

    width = max(len(n) for n, _, _ in checks)
    for name, ok, detail in checks:
        print(f"  [{'ok' if ok else 'FAIL'}] {name:<{width}}  {detail}")
    print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
    return not failures


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"])
    ap.add_argument("--dataset", default=None, help="Restrict to one dataset (e.g. NAB).")
    ap.add_argument("--max-k", type=int, default=MAX_K,
                    help="Largest combination size (default 3).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Use only the first N series -- for timing runs.")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--test", action="store_true", help="Run sanity checks only.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.max_k > MAX_K:
        ap.error(f"--max-k above {MAX_K} needs wider d* columns; k=4 is a later step")

    if args.test:
        raise SystemExit(0 if run_tests(args.device) else 1)

    parser = get_parser(args.kind)
    detectors = get_detectors(parser)
    filenames = list_series(parser, args.dataset)
    if args.limit:
        filenames = filenames[:args.limit]

    n_combos = sum(len(list(itertools.combinations(range(len(detectors)), k)))
                   for k in range(1, args.max_k + 1))
    print(f"{len(filenames)} series x {n_combos:,} combinations "
          f"= {len(filenames) * n_combos:,} VUS computations")

    metric, device = load_vus(args.device)
    print(f"FF-VUS on {device}, buffers 0..{SLOPE_SIZE}")

    started = time.time()
    table, skipped = build_table(parser, filenames, detectors, metric, args.max_k)
    elapsed = time.time() - started

    if table.empty:
        print("No usable series.")
        raise SystemExit(1)

    suffix = f"_{args.dataset}" if args.dataset else ""
    out = Path(args.out) if args.out else OUT_ROOT / f"combos_{args.kind}{suffix}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out, index=False, compression="zstd")

    pd.Series(detectors).to_frame("detector").to_parquet(
        out.with_name(f"combos_{args.kind}_detectors.parquet"), index=True)

    print(f"\n{len(table):,} rows, {table.filename.nunique()} series "
          f"-> {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    print(f"{elapsed:.1f}s total, {elapsed / max(len(table), 1) * 1000:.2f} ms per combination")
    if skipped:
        print(f"skipped {len(skipped)} series: {', '.join(skipped[:5])}"
              f"{' ...' if len(skipped) > 5 else ''}")


if __name__ == "__main__":
    main()
