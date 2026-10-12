"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- the content pack: the series the game plays, read and written.

A pack is a folder, built offline (build_pack.py from the benchmark,
make_dev_pack.py for synthetic data), so the game server never touches the
benchmark and runs on a booth laptop with nothing else installed:

    <pack>/manifest.json      name, detector team, one entry per series
    <pack>/series/<id>.json   one series, the fields of Series below

The source (benchmark file and window) is kept in the pack for the analysis,
and never sent to the browser.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

TIERS = ["easy", "medium", "unsolved", "decoy"]

# Integer resolution of the stored detector scores. 0..SCORE_SCALE keeps a
# 10k series to ~40 kB of JSON per detector, and the mean + 3 std threshold
# does not move under min-max scaling.
SCORE_SCALE = 1000


@dataclass
class Series:
    id: int                      # the neutral number shown as "Series 14"
    tier: str                    # easy | medium | unsolved | decoy
    values: list[float]
    labels: list[list[int]]      # inclusive [start, end] runs; [] on a decoy
    detectors: list[dict]        # [{"name": ..., "score": [int]}], team order;
                                 # score min-max normalised to 0..SCORE_SCALE
    source: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.values)


@dataclass
class Pack:
    name: str
    detectors: list[str]
    series: dict[int, Series]

    def by_tier(self) -> dict[str, list[int]]:
        out = {t: [] for t in TIERS}
        for s in self.series.values():
            out.setdefault(s.tier, []).append(s.id)
        return out


def load_pack(path: str | Path) -> Pack:
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text())
    series = {}
    for entry in manifest["series"]:
        raw = json.loads((path / entry["file"]).read_text())
        s = Series(**raw)
        if s.tier not in TIERS:
            raise ValueError(f"{entry['file']}: unknown tier {s.tier!r}")
        for d in s.detectors:
            if len(d["score"]) != s.n:
                raise ValueError(f"{entry['file']}: {d['name']} score has {len(d['score'])} points, values {s.n}")
        series[s.id] = s
    if not series:
        raise ValueError(f"{path}: the pack has no series")
    return Pack(name=manifest.get("name", path.name), detectors=manifest["detectors"], series=series)


def write_pack(path: str | Path, name: str, detectors: list[str], series: list[Series]) -> Path:
    path = Path(path)
    (path / "series").mkdir(parents=True, exist_ok=True)
    entries = []
    for s in series:
        file = f"series/{s.id}.json"
        (path / file).write_text(json.dumps(asdict(s), separators=(",", ":")))
        entries.append({"id": s.id, "tier": s.tier, "n": s.n, "file": file})
    manifest = {"name": name, "created": date.today().isoformat(),
                "detectors": detectors, "series": entries}
    (path / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return path


def quantize(score) -> list[int]:
    """Min-max normalise a score vector to integers 0..SCORE_SCALE."""
    lo, hi = min(score), max(score)
    if hi <= lo:
        return [0] * len(score)
    return [int(round((x - lo) / (hi - lo) * SCORE_SCALE)) for x in score]


def round_values(values, digits: int = 5) -> list[float]:
    """Keep `digits` significant digits: the chart cannot show more, and it
    halves the JSON."""
    return [float(f"{float(v):.{digits}g}") for v in values]
