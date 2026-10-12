"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- the difficulty tiers, from the divergence study's oracle.

One line per series, `filename,tier`, for build_pack.py --tiers. A detector
"solves" a series when its VUS-PR at buffer L reaches --solved. The default
is 0.5, the same bar build_pack.py uses without a tiers file; at the demo's
0.9 (the Landscape page) only 19 series are easy, too few for a pack. Then:

    easy        at least half of the detectors solve it on their own
    medium      at least one detector, or one combination of up to three
                averaged (the study's oracle), solves it
    unsolved    nothing in the study reaches the bar

The study's tables are data/divergence/combos_uni_<dataset>.parquet (one row
per detector combination, k = 1..3, VUS-PR at every buffer); the k = 1 rows
are the single detectors. The extra columns in the CSV are for reading, not
for the game.

Run:
    python game/make_tiers.py                       # data/divergence/tiers_uni.csv
    python game/make_tiers.py --solved 0.7 --buffer 64 --out /tmp/tiers.csv
"""

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DIVERGENCE = REPO_ROOT / "data" / "divergence"


def load_combos(kind: str, buffer: int) -> pd.DataFrame:
    """filename, k, vus for every combination in the study."""
    files = sorted(DIVERGENCE.glob(f"combos_{kind}_*.parquet"))
    files = [f for f in files if not f.name.endswith("_detectors.parquet")]
    if not files:
        raise SystemExit(f"No combos_{kind}_*.parquet under {DIVERGENCE}")
    col = f"vus_{buffer}"
    parts = [pd.read_parquet(f, columns=["filename", "k", col]).rename(columns={col: "vus"})
             for f in files]
    out = pd.concat(parts, ignore_index=True)
    out["filename"] = out["filename"].astype(str)
    return out


def tiers(combos: pd.DataFrame, solved: float) -> pd.DataFrame:
    solo = combos[combos.k == 1].groupby("filename").vus
    per_file = pd.DataFrame({
        "n_solved": solo.apply(lambda v: int((v >= solved).sum())),
        "n_detectors": solo.size(),
        "best_single": solo.max(),
        "best_combo": combos[combos.k > 1].groupby("filename").vus.max(),
    })
    share = per_file.n_solved / per_file.n_detectors
    any_solo = per_file.n_solved > 0
    any_combo = per_file.best_combo.fillna(0) >= solved
    per_file["tier"] = "unsolved"
    per_file.loc[any_solo | any_combo, "tier"] = "medium"
    per_file.loc[share >= 0.5, "tier"] = "easy"
    per_file.index.name = "filename"
    return per_file.reset_index()[["filename", "tier", "n_solved", "n_detectors", "best_single", "best_combo"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", default="uni")
    ap.add_argument("--buffer", type=int, default=128, help="VUS buffer L")
    ap.add_argument("--solved", type=float, default=0.5, help="VUS-PR that counts as solved")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    out = args.out or DIVERGENCE / f"tiers_{args.kind}.csv"

    t = tiers(load_combos(args.kind, args.buffer), args.solved)
    t.round(4).to_csv(out, index=False)
    print(f"Wrote {len(t)} series to {out} (solved = VUS-PR >= {args.solved} at L={args.buffer})")
    print(t.tier.value_counts().reindex(["easy", "medium", "unsolved"]).to_string())
    only_combo = t[(t.n_solved == 0) & (t.tier == "medium")]
    print(f"{len(only_combo)} medium series are solved only by a combination")


if __name__ == "__main__":
    main()
