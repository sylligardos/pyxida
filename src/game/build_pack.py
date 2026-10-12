"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- build the content pack from a benchmark (univariate).

For each picked series: the values, the labels as ranges, and each team
member's score, min-max normalised over the window. Whether a detector
caught the anomaly is worked out at play time (scoring.py), from the same
scores the Reveal draws. Series longer than --max-len are
cut to a window that holds the first anomaly whole and, by default, no
other (--max-labels: every screen is designed around one anomaly); decoys
are label-free windows cut from the normal part of a series. Flat windows
are passed over.

Tiers. The game shows "easy / medium / unsolved". The right source is the
divergence study (oracle over single detectors and combinations); pass it as
a CSV with columns `filename,tier` via --tiers. Without it, a stand-in from
the metric files: a detector "solves" a series when its VUS-PR reaches
--solved; easy when at least half of all detectors solve it, unsolved when
none does, medium in between.

The team: pick_team.py ranks the detectors by Shapley value against the
oracle; pass the top five with --detectors.

Run:
    python src/game/make_tiers.py
    python src/game/pick_team.py
    python src/game/build_pack.py --detectors KShapeAD Sub_LOF MatrixProfile LOF MOMENT_FT \\
        --tiers data/divergence/tiers_uni.csv --out data/game/tsb-ad
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


def window_around_first(labels: np.ndarray, max_len: int, rng: random.Random,
                        max_labels: int = 1) -> tuple[int, int]:
    """[start, end) of at most max_len points holding the first anomaly run
    whole (or its first max_len points), at a random offset. With max_labels,
    the window ends before the (max_labels + 1)-th anomaly, so it holds at
    most that many; 0 means no limit."""
    n = len(labels)
    runs = labels_to_ranges(labels)
    a, b = runs[0]
    b = min(b, a + max_len - 1)
    end_limit = runs[max_labels][0] if max_labels and len(runs) > max_labels else n
    length = min(max_len, end_limit)
    lo, hi = max(0, b - length + 1), min(a, end_limit - length)
    start = rng.randint(lo, hi)
    return start, start + length


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


def usable(values) -> bool:
    """A window the player can look at: finite, and not a flat line."""
    v = np.asarray(values, dtype=float)
    return bool(np.isfinite(v).all() and np.ptp(v) > 0)


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


def load_batch(parser: TSBADParser, files: list[str], detectors: list[str]) -> dict:
    """{filename: (values, labels, scores)} for the files that load cleanly."""
    if not files:
        return {}
    names, values, labels = parser.load_timeseries(filename=files)
    data = {n: (v, y) for n, v, y in zip(names, values, labels)}
    kept, scores, _ = parser.load_scores(detectors=detectors, filenames=files, return_filenames=True)
    out = {}
    for f, s in zip(kept, scores):
        if f not in data or data[f][0].ndim != 1:
            continue
        v, y = data[f]
        out[f] = (v, (np.asarray(y) > 0).astype(np.int8), s)
    return out


class Picker:
    """Walks shuffled candidates, a batch at a time, until a tier has its
    quota. Counts why a candidate was passed over."""

    def __init__(self, parser, detectors, args, rng, ids):
        self.parser, self.detectors, self.args, self.rng, self.ids = parser, detectors, args, rng, ids
        self.source = {"benchmark": parser.benchmark}
        self.rejected = {}

    def reject(self, tier, why):
        self.rejected[(tier, why)] = self.rejected.get((tier, why), 0) + 1

    def cut(self, tier, v, y):
        """[start, end) for this tier, or None with the reason counted."""
        a = self.args
        if tier == "decoy":
            lo, hi = longest_clean_stretch(y)
            if hi - lo < a.min_len:
                return self.reject(tier, "no clean stretch")
            length = self.rng.randint(a.min_len, min(a.max_len, hi - lo))
            start = self.rng.randint(lo, hi - length)
            end = start + length
        else:
            if not y.any():
                return self.reject(tier, "no anomaly")
            start, end = window_around_first(y, a.max_len, self.rng, a.max_labels)
            if end - start < a.min_len:
                return self.reject(tier, "short")
        if not usable(v[start:end]):
            return self.reject(tier, "flat")
        return start, end

    def pick(self, tier, candidates, quota):
        candidates = sorted(candidates)
        self.rng.shuffle(candidates)
        out, tried = [], 0
        for i in range(0, len(candidates), self.args.batch):
            if len(out) >= quota:
                break
            batch = candidates[i:i + self.args.batch]
            loaded = load_batch(self.parser, batch, self.detectors)
            for f in batch:
                if len(out) >= quota:
                    break
                tried += 1
                if f not in loaded:
                    self.reject(tier, "missing scores")
                    continue
                v, y, s = loaded[f]
                window = self.cut(tier, v, y)
                if window is None:
                    continue
                out.append(make_series(self.ids.pop(), tier, v, y, s, self.detectors, *window,
                                       {**self.source, "filename": f}))
        print(f"{tier}: {len(out)} of {quota} from {tried} candidates")
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--benchmark", default="tsb-ad")
    ap.add_argument("--detectors", nargs="+", required=True, help="the detector team, in display order")
    ap.add_argument("--tiers", type=Path, help="CSV with columns filename,tier (easy|medium|unsolved)")
    ap.add_argument("--solved", type=float, default=0.5, help="VUS-PR that counts as solved, without --tiers")
    ap.add_argument("--per-tier", type=int, default=30, help="series per tier, decoys included")
    ap.add_argument("--min-len", type=int, default=1000)
    ap.add_argument("--max-len", type=int, default=10000)
    ap.add_argument("--max-labels", type=int, default=1,
                    help="most labeled anomalies in a window (the screens are designed for one); 0 = no limit")
    ap.add_argument("--batch", type=int, default=30, help="candidates loaded per batch")
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

    total = 4 * args.per_tier
    ids = rng.sample(range(10, 10 + total * 10), total)   # neutral, unrelated to the benchmark ids
    picker = Picker(parser, args.detectors, args, rng, ids)
    out = []
    for tier in ["easy", "medium", "unsolved"]:
        out += picker.pick(tier, tiers[tiers == tier].index, args.per_tier)
    # Decoys come from any series not already in the pack.
    used = {s.source["filename"] for s in out}
    out += picker.pick("decoy", set(parser.meta.filename) - used, args.per_tier)

    write_pack(args.out, f"{parser.benchmark} uni", args.detectors, out)
    counts = pd.Series([s.tier for s in out]).value_counts().to_dict()
    print(f"Wrote {len(out)} series to {args.out}: {counts}")
    if picker.rejected:
        print("Passed over:", ", ".join(f"{t} {why} x{n}" for (t, why), n in sorted(picker.rejected.items())))


if __name__ == "__main__":
    main()
