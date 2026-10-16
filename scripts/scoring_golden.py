"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Golden results of scripts/needle/scoring.py on the dev pack, for the TypeScript
port in web/lib/game/scoring.ts (checked by web/tests/scoring.test.ts).

Run, from the repo root, after `python scripts/needle/make_dev_pack.py`:
    python scripts/scoring_golden.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "needle"))

from pack import load_pack  # noqa: E402
from scoring import score_series  # noqa: E402

OUT = REPO / "web" / "tests" / "scoring_golden.json"


def cases(s):
    n = s.n
    yield "nothing", []
    yield "edges", [[10, 20], [n - 30, n - 5]]
    if s.labels:
        a, b = s.labels[0]
        yield "label", [[a, b]]
        yield "label+fa", [[max(0, a - 3), b + 3], [n // 2, n // 2 + 5], [1, 2]]
        yield "near", [[b + 20, b + 60]]
    yield "overlap", [[0, 5], [3, 9], [9.4, 12.6]]
    yield "whole", [[0, n - 1]]
    yield "just wide", [[0, n // 10]]
    yield "just fits", [[0, n // 10 - 1]]


def main():
    pack = load_pack(REPO / "data" / "game" / "dev")
    out = []
    for sid in sorted(pack.series):
        s = pack.series[sid]
        for name, ranges in cases(s):
            out.append({"id": sid, "case": name, "ranges": ranges,
                        "result": score_series(ranges, s.labels, s.detectors, s.n)})
            # The real packs hold one opponent per series: the same case, solo.
            out.append({"id": sid, "case": name + " solo", "ranges": ranges, "solo": True,
                        "result": score_series(ranges, s.labels, s.detectors[:1], s.n)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(out)} cases -> {OUT}")


if __name__ == "__main__":
    main()
