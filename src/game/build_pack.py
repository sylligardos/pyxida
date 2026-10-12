"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- build the content pack from a benchmark (univariate).

For each picked series: the values, the labels as ranges, and each team
member's score, min-max normalised over the window. Whether a detector
caught the anomaly is worked out at play time (scoring.py), from the same
scores the Reveal draws. Series longer than --max-len are
cut to a window that holds the first anomaly whole; decoys are label-free
windows cut from the normal part of a series.

Tiers. The game shows "easy / medium / unsolved". The right source is the
divergence study (oracle over single detectors and combinations); pass it as
a CSV with columns `filename,tier` via --tiers. Without it, a stand-in from
the metric files: a detector "solves" a series when its VUS-PR reaches
--solved; easy when at least half of all detectors solve it, unsolved when
none does, medium in between.

The team is not decided yet (Shapley top five against the oracle, or the
per-series best); pass it with --detectors.

Run:
    python src/game/build_pack.py --detectors Sub_PCA KShapeAD POLY Series2Graph MOMENT_FT
    python src/game/build_pack.py --detectors ... --tiers data/divergence/tiers_uni.csv \\
        --per-tier 40 --out data/game/tsb-ad
"""

import argparse
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pack import Series, quantize, round_values, write_pack  # noqa: E402
from scoring import labels_to_ranges  # noqa: E402
from tsbadparser import TSBADParser  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def tiers_from_metrics(parser: TSBADParser, solved: float) -> pd.Series:
    m = parser.load_metrics()
    if m.empty:
        raise SystemExit(f"No metric files under {parser.metrics_path}; pass --tiers instead.")
    good = (m.assign(ok=m["VUS-PR"] >= solved)
            .groupby("File Name")["ok"].agg(["sum", "count"]))
    share = good["sum"] / good["count"]
    return pd.Series(np.where(good["sum"] == 0, "unsolved",
                              np.where(share >= 0.5, "easy", "medium")), index=good.index)


def window_around_first(labels: np.ndarray, max_len: int, rng: random.Random) -> tuple[int, int]:
    """[start, end) of at most max_len points holding the first anomaly run
    whole (or its first max_len points), at a random offset."""
    n = len(labels)
    if n <= max_len:
        return 0, n
    a, b = labels_to_ranges(labels)[0]
    b = min(b, a + max_len - 1)
    lo, hi = max(0, b - max_len + 1), min(a, n - max_len)
    start = rng.randint(lo, hi)
    return start, start + max_len


def longest_clean_stretch(labels: np.ndarray) -> tuple[int, int]:
    """[start, end) of the longest run of normal points."""
    best, start = (0, 0), None
    for i, y in enumerate(np.append(labels, 1)):
        if not y and start is None:
            start = i
        elif y and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    return best


def make_series(sid, tier, values, labels, scores, detectors, a, b, source):
    v, y = values[a:b], labels[a:b]
    norm = []
    for s in scores[:, a:b]:
        lo, hi = s.min(), s.max()
        norm.append((s - lo) / (hi - lo) if hi > lo else np.zeros_like(s))
    return Series(
        id=sid, tier=tier, values=round_values(v), labels=labels_to_ranges(y),
        detectors=[{"name": d, "score": quantize(s.tolist())} for d, s in zip(detectors, norm)],
        source={**source, "start": int(a), "end": int(b)},
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--benchmark", default="tsb-ad")
    ap.add_argument("--detectors", nargs="+", required=True, help="the detector team, in display order")
    ap.add_argument("--tiers", type=Path, help="CSV with columns filename,tier (easy|medium|unsolved)")
    ap.add_argument("--solved", type=float, default=0.5, help="VUS-PR that counts as solved, without --tiers")
    ap.add_argument("--per-tier", type=int, default=30, help="series per tier, decoys included")
    ap.add_argument("--min-len", type=int, default=1000)
    ap.add_argument("--max-len", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "game" / "tsb-ad")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    parser = TSBADParser(benchmark=args.benchmark, kind="uni")
    missing = set(args.detectors) - set(parser.get_detectors())
    if missing:
        raise SystemExit(f"Unknown detectors for {parser.benchmark}: {sorted(missing)}")

    if args.tiers:
        t = pd.read_csv(args.tiers)
        tiers = pd.Series(t["tier"].values, index=t["filename"].values)
    else:
        tiers = tiers_from_metrics(parser, args.solved)
    tiers = tiers[tiers.index.isin(set(parser.meta.filename))]
    print("Tiers available:", tiers.value_counts().to_dict())

    picks = {}
    for tier in ["easy", "medium", "unsolved"]:
        files = sorted(tiers[tiers == tier].index)
        picks[tier] = rng.sample(files, min(args.per_tier, len(files)))
    # Decoys come from any series long enough to hold a clean window.
    decoy_pool = sorted(set(parser.meta.filename) - {f for fs in picks.values() for f in fs})
    picks["decoy"] = rng.sample(decoy_pool, min(len(decoy_pool), args.per_tier * 3))

    wanted = sorted({f for fs in picks.values() for f in fs})
    names, values, labels = parser.load_timeseries(filename=wanted)
    data = {n: (v, l) for n, v, l in zip(names, values, labels)}
    kept, scores, bad = parser.load_scores(detectors=args.detectors, filenames=wanted, return_filenames=True)
    scores = dict(zip(kept, scores))
    if bad:
        print(f"Skipping {len(bad)} series with missing or broken scores")

    total = sum(len(fs) for t, fs in picks.items() if t != "decoy") + args.per_tier
    ids = rng.sample(range(10, 10 + total * 10), total)   # neutral, unrelated to the benchmark ids
    out = []

    for tier in ["easy", "medium", "unsolved"]:
        for f in picks[tier]:
            if f not in scores:
                continue
            v, y = data[f]
            y = (np.asarray(y) > 0).astype(np.int8)
            if v.ndim != 1 or not y.any():
                continue
            a, b = window_around_first(y, args.max_len, rng)
            if b - a < args.min_len:
                continue
            s = make_series(ids.pop(), tier, v, y, scores[f], args.detectors, a, b,
                            {"benchmark": parser.benchmark, "filename": f})
            out.append(s)

    n_decoys = 0
    for f in picks["decoy"]:
        if n_decoys >= args.per_tier or f not in scores:
            continue
        v, y = data[f]
        y = (np.asarray(y) > 0).astype(np.int8)
        a, b = longest_clean_stretch(y)
        if v.ndim != 1 or b - a < args.min_len:
            continue
        length = rng.randint(args.min_len, min(args.max_len, b - a))
        a = rng.randint(a, b - length)
        out.append(make_series(ids.pop(), "decoy", v, y, scores[f], args.detectors, a, a + length,
                               {"benchmark": parser.benchmark, "filename": f}))
        n_decoys += 1

    write_pack(args.out, f"{parser.benchmark} uni", args.detectors, out)
    counts = pd.Series([s.tier for s in out]).value_counts().to_dict()
    print(f"Wrote {len(out)} series to {args.out}: {counts}")


if __name__ == "__main__":
    main()
