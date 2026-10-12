"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- look at a content pack before putting it in front of players.

For every series: the window, the labels in it, and how the detectors do
under the game's own rules (scoring.py), with no player. Printed per tier:
how many series, their length, labels per window, how often the detectors
find the anomaly, their false alarms, and their points. Then each detector's
own catch rate, and the decoys the detectors take the bait on.

Run:
    python game/check_pack.py                    # data/game/dev
    python game/check_pack.py data/game/tsb-ad --list
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pack import TIERS, load_pack  # noqa: E402
from scoring import detector_flags, evaluate, result_key  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def rows(pack) -> pd.DataFrame:
    out = []
    for s in pack.series.values():
        each, side = detector_flags(s.detectors, s.labels, s.n)
        det = evaluate(side["flags"], s.labels)
        out.append({
            "id": s.id, "tier": s.tier, "n": s.n, "labels": len(s.labels),
            "label_points": sum(b - a + 1 for a, b in s.labels),
            "first_label_at": round(s.labels[0][0] / s.n, 2) if s.labels else None,
            "det_result": result_key(det, len(s.labels)),
            "det_hits": det["hits"], "det_fa": det["false_alarms"], "det_points": det["points"],
            "caught_by": sum(d["caught"] for d in each),
            **{f"caught_{d['name']}": d["caught"] for d in each},
            "file": s.source.get("filename", ""), "window": f"{s.source.get('start')}-{s.source.get('end')}",
        })
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack", nargs="?", type=Path, default=REPO_ROOT / "data" / "game" / "dev")
    ap.add_argument("--list", action="store_true", help="also print every series")
    args = ap.parse_args()

    pack = load_pack(args.pack)
    r = rows(pack)
    tiers = [t for t in TIERS if t in set(r.tier)]
    print(f"{pack.name}: {len(r)} series, team {pack.detectors}\n")

    g = r.groupby("tier")
    summary = pd.DataFrame({
        "series": g.size(),
        "len_min": g.n.min(), "len_median": g.n.median().astype(int), "len_max": g.n.max(),
        "labels/window": g.labels.mean().round(2),
        "label_pts_median": g.label_points.median().astype(int),
        "det_found": g.det_result.apply(lambda s: s.isin(["found", "partial"]).mean()).round(2),
        "det_clean": g.det_result.apply(lambda s: (s == "clean").mean()).round(2),
        "det_fa_mean": g.det_fa.mean().round(2),
        "det_points_mean": g.det_points.mean().round(2),
    }).reindex(tiers)
    print("Per tier (det_found: the team's flags touch an anomaly; det_clean: a decoy left alone)")
    print(summary.to_string(), "\n")

    with_labels = r[r.labels > 0]
    caught = {d: with_labels[f"caught_{d}"].mean() for d in pack.detectors}
    print("Each detector alone, share of labeled series it catches:")
    print(pd.Series(caught).round(2).to_string(), "\n")
    print("Labeled series caught by how many detectors alone:")
    print(with_labels.caught_by.value_counts().sort_index().to_string(), "\n")

    multi = r[r.labels > 1]
    print(f"{len(multi)} windows hold more than one labeled anomaly (the Reveal draws them all; "
          f"the summary card has no partial mark yet)")
    if args.list:
        with pd.option_context("display.width", 200, "display.max_rows", None):
            cols = ["id", "tier", "n", "labels", "label_points", "first_label_at", "det_result",
                    "det_fa", "caught_by", "file", "window"]
            print(r.sort_values(["tier", "id"])[cols].to_string(index=False))


if __name__ == "__main__":
    main()
