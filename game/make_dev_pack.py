"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- a synthetic content pack, to build and test the game without
the benchmark.

Same generator as the design comps (references/needle-design/project/
Chart.dc.html): a noisy periodic signal with drift, and anomalies of a few
kinds. Five fake detectors per series fire either on the anomaly or somewhere
else, so the tiers behave like the real ones: on "easy" most of them catch
it, on "medium" one or two, on "unsolved" none, and a decoy has nothing to
catch. Every number is made up; never show this pack at the booth.

Run:
    python game/make_dev_pack.py                 # -> data/game/dev
    python game/make_dev_pack.py --out /tmp/pack
"""

import argparse
import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pack import Series, quantize, round_values, write_pack  # noqa: E402
from scoring import n_points  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "game" / "dev"

DETECTORS = ["Sub_PCA", "KShapeAD", "POLY", "Series2Graph", "MOMENT_FT"]

# (tier, kind, length, anomalies as fractions of the length). Several
# anomalies in one series exercise the "2 of 3" result.
PLAN = [
    ("easy", "shift", 2400, [(0.40, 0.47)]),
    ("easy", "point", 1800, [(0.70, 0.70)]),
    ("easy", "flat", 3000, [(0.33, 0.37)]),
    ("easy", "point", 5200, [(0.21, 0.21), (0.66, 0.66)]),
    ("easy", "noise", 4000, [(0.58, 0.62)]),
    ("easy", "shift", 7000, [(0.81, 0.86)]),
    ("medium", "freq", 3600, [(0.30, 0.36)]),
    ("medium", "freq", 6800, [(0.74, 0.80)]),
    ("medium", "subtle", 4200, [(0.45, 0.52)]),
    ("medium", "noise", 2600, [(0.15, 0.19), (0.62, 0.65)]),
    ("medium", "flat", 9000, [(0.52, 0.53)]),
    ("medium", "freq", 1500, [(0.48, 0.58)]),
    ("unsolved", "freq", 4800, [(0.52, 0.58)]),
    ("unsolved", "subtle", 6000, [(0.27, 0.31)]),
    ("unsolved", "freq", 9800, [(0.12, 0.15), (0.44, 0.47), (0.88, 0.90)]),
    ("unsolved", "subtle", 2200, [(0.69, 0.76)]),
    ("decoy", "none", 5200, []),
    ("decoy", "none", 3300, []),
    ("decoy", "none", 8000, []),
    ("decoy", "none", 1200, []),
]

# How many of the five detectors fire on the anomaly, per tier.
ON_TARGET = {"easy": (4, 5), "medium": (1, 2), "unsolved": (0, 0), "decoy": (0, 0)}


def signal(rng: random.Random, n: int, kind: str, anomalies, period: float):
    spans = [(round(a * (n - 1)), round(b * (n - 1))) for a, b in anomalies]
    inside = lambda i: any(a <= i <= b for a, b in spans)  # noqa: E731
    v = []
    ph, drift, ar = rng.random() * 6.28, 0.0, 0.0
    for i in range(n):
        anom = kind != "none" and inside(i)
        ph += 2 * math.pi * (1.55 if kind == "freq" and anom else 1) / period
        drift = drift * 0.998 + (rng.random() - 0.5) * 0.03
        ar = ar * 0.6 + (rng.random() - 0.5) * 0.3
        y = math.sin(ph) + 0.32 * math.sin(ph * 3 + 0.7) + drift + ar
        if anom:
            if kind == "shift":
                y += 0.6
            elif kind == "noise":
                y += (rng.random() - 0.5) * 1.6
            elif kind == "subtle":
                y = 0.82 * y
        if kind == "point" and any(i == a for a, _ in spans):
            y += 2.6 * (1 if rng.random() < 0.7 else -1)
        # A flatline holds the last value before the anomaly.
        v.append(v[-1] if kind == "flat" and anom else 40 + 9 * y)
    return v, [[a, b] for a, b in spans]


def fake_detector(rng: random.Random, n: int, targets) -> np.ndarray:
    """A smooth noise floor plus bumps on the target ranges."""
    t = np.arange(n) / n
    s = 0.16 + 0.07 * (np.sin(t * rng.uniform(100, 200) + rng.random() * 6)
                       + np.sin(t * rng.uniform(40, 80) + rng.random() * 6))
    s += np.abs(np.random.default_rng(rng.randrange(1 << 30)).normal(0, 0.03, n))
    for a, b in targets:
        c, w = (a + b) / 2, max((b - a) / 2, n * 0.004)
        s += 0.75 * np.exp(-(((np.arange(n) - c) / (w * 1.3)) ** 2))
    return s


def build(seed: int = 7) -> list[Series]:
    rng = random.Random(seed)
    out = []
    ids = rng.sample(range(10, 99), len(PLAN))
    for sid, (tier, kind, n, anomalies) in zip(ids, PLAN):
        values, labels = signal(rng, n, kind, anomalies, period=rng.uniform(90, 180))

        lo, hi = ON_TARGET[tier]
        k_on = rng.randint(lo, hi)
        scores = []
        for d in range(len(DETECTORS)):
            if d < k_on:
                targets = labels
            else:
                # Somewhere plausible but wrong: one or two spots away from
                # every label.
                targets = []
                for _ in range(rng.randint(1, 2)):
                    while True:
                        c = rng.randrange(n)
                        if all(abs(c - (a + b) / 2) > n * 0.08 for a, b in labels):
                            break
                    # At least as wide as the labels, so the detector's top
                    # points all land here rather than in its noise floor.
                    w = max(rng.randint(max(2, n // 400), max(3, n // 60)),
                            n_points(labels) // 2 + n // 100)
                    targets.append([max(0, c - w), min(n - 1, c + w)])
            scores.append(fake_detector(rng, n, targets))
        order = list(range(len(DETECTORS)))
        rng.shuffle(order)     # so the lit chips are not always the first ones
        scores = [scores[k] for k in order]

        out.append(Series(
            id=sid, tier=tier,
            values=round_values(values),
            labels=labels,
            detectors=[{"name": name, "score": quantize(s.tolist())}
                       for name, s in zip(DETECTORS, scores)],
            source={"synthetic": True, "kind": kind},
        ))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    series = build(args.seed)
    write_pack(args.out, "dev (synthetic)", DETECTORS, series)
    print(f"Wrote {len(series)} series to {args.out}")


if __name__ == "__main__":
    main()
