"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- rank the detectors by what they add to the oracle, to pick the team.

The oracle on a series is the best single detector's VUS-PR. A detector's
worth to it is its Shapley value for the "max" game, which has a closed
form: sort the detectors on a series by VUS-PR, v(1) >= ... >= v(n); the
one at rank r gets

    sum over j = r..n of (v(j) - v(j+1)) / j,   with v(n+1) = 0

so each slice of the ceiling is shared equally by the detectors that reach
it. Averaged over series. Also printed: the mean VUS-PR (the usual
leaderboard), the drop in the oracle's mean when the detector is left out,
and the series it alone solves (VUS-PR >= --solved while no other does).

Reads the k = 1 rows of data/divergence/combos_uni_<dataset>.parquet, like
make_tiers.py.

Run:
    python scripts/needle/pick_team.py                # table, and the top five by Shapley
    python scripts/needle/pick_team.py --size 5 --by loo
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DIVERGENCE = REPO_ROOT / "data" / "divergence"


def solo_table(kind: str, buffer: int) -> pd.DataFrame:
    """series x detector VUS-PR at buffer L, from the study's k = 1 rows."""
    names = pd.read_parquet(DIVERGENCE / f"combos_{kind}_detectors.parquet").detector.tolist()
    col = f"vus_{buffer}"
    parts = []
    for f in sorted(DIVERGENCE.glob(f"combos_{kind}_*.parquet")):
        if f.name.endswith("_detectors.parquet"):
            continue
        d = pd.read_parquet(f, columns=["filename", "k", "d0", col])
        d = d[d.k == 1]
        parts.append(pd.DataFrame({"filename": d.filename.astype(str),
                                   "detector": [names[i] for i in d.d0], "vus": d[col].values}))
    return pd.concat(parts).pivot(index="filename", columns="detector", values="vus")


def shapley_max(v: np.ndarray) -> np.ndarray:
    """Shapley values of the max game, one row of VUS-PR per series."""
    order = np.argsort(-v, axis=1)
    s = np.take_along_axis(v, order, axis=1)
    n = v.shape[1]
    slices = s - np.concatenate([s[:, 1:], np.zeros((len(v), 1))], axis=1)   # v(j) - v(j+1)
    shares = slices / np.arange(1, n + 1)                                     # / j
    phi_sorted = np.cumsum(shares[:, ::-1], axis=1)[:, ::-1]                  # sum over j >= r
    phi = np.empty_like(v)
    np.put_along_axis(phi, order, phi_sorted, axis=1)
    return phi


def leaderboard(table: pd.DataFrame, solved: float) -> pd.DataFrame:
    v = table.fillna(0).to_numpy(dtype=float)
    ceiling = v.max(axis=1).mean()
    loo = []
    for j in range(v.shape[1]):
        without = np.delete(v, j, axis=1).max(axis=1).mean()
        loo.append(ceiling - without)
    ok = v >= solved
    alone = ok & (ok.sum(axis=1, keepdims=True) == 1)
    out = pd.DataFrame({
        "mean_vus": v.mean(axis=0),
        "shapley": shapley_max(v).mean(axis=0),
        "loo_drop": loo,
        "solves": ok.sum(axis=0),
        "alone": alone.sum(axis=0),
    }, index=table.columns)
    out["rank_mean"] = out.mean_vus.rank(ascending=False).astype(int)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", default="uni")
    ap.add_argument("--buffer", type=int, default=128)
    ap.add_argument("--solved", type=float, default=0.9)
    ap.add_argument("--size", type=int, default=5)
    ap.add_argument("--by", choices=["shapley", "loo_drop", "mean_vus", "alone"], default="shapley")
    args = ap.parse_args()

    table = solo_table(args.kind, args.buffer)
    board = leaderboard(table, args.solved).sort_values(args.by, ascending=False)
    print(f"{table.shape[0]} series, {table.shape[1]} detectors, L={args.buffer}, "
          f"oracle mean {table.fillna(0).max(axis=1).mean():.4f}, solved = VUS-PR >= {args.solved}")
    with pd.option_context("display.float_format", "{:.4f}".format, "display.width", 120):
        print(board.to_string())
    team = board.index[:args.size].tolist()
    print(f"\nTeam by {args.by}: {' '.join(team)}")


if __name__ == "__main__":
    main()
