"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- the scoring rules, in one place.

A range is a pair [a, b] of inclusive point indices. The rules, from
references/GAME_BRIEF.md:

    hit           a labeled anomaly that at least one range overlaps (+1).
                  Counted per anomaly, not per range, so five ranges on the
                  same anomaly are one hit, not five.
    false alarm   a range that overlaps no labeled anomaly (-1).
    clean decoy   a series with no anomaly, left unmarked (+1).

The detectors play by the same rules but decide on their own, whatever the
player marked. A score flags every point more than THRESHOLD_STD standard
deviations above its mean, grouped into ranges. Which score is the
detectors' side is DETECTOR_RULE:

    average   the team average (each detector min-max normalised over the
              window, then averaged point by point): one score, one
              threshold, one opponent.
    pooled    every detector on its own score and threshold, all their flags
              together: an anomaly any detector flagged is a hit, every
              flagged stretch on no anomaly a false alarm.

Either way each detector's own threshold and flags are worked out too, for
the Reveal's lanes ("KShapeAD alone would have caught it").
"""

import numpy as np


# --------------------------------------------------------------------------
# Ranges
# --------------------------------------------------------------------------

def clean_ranges(ranges, n: int) -> list[list[int]]:
    """Clip to [0, n-1], order each pair, sort, and merge overlapping or
    touching ranges. Drops anything outside the series."""
    out = []
    for r in ranges or []:
        a, b = int(round(min(r[0], r[1]))), int(round(max(r[0], r[1])))
        if b < 0 or a > n - 1:
            continue
        out.append([max(0, a), min(n - 1, b)])
    out.sort()
    merged = []
    for a, b in out:
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def n_points(ranges) -> int:
    return sum(b - a + 1 for a, b in ranges)


def overlaps(r, s) -> bool:
    return r[0] <= s[1] and r[1] >= s[0]


def labels_to_ranges(labels) -> list[list[int]]:
    """Binary label vector -> inclusive [start, end] runs of ones."""
    y = np.asarray(labels).astype(bool).astype(np.int8)
    if not y.any():
        return []
    d = np.diff(np.concatenate([[0], y, [0]]))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1) - 1
    return [[int(a), int(b)] for a, b in zip(starts, ends)]


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------

THRESHOLD_STD = 3
DETECTOR_RULE = "average"      # average | pooled, see the top of the file


def threshold(score, k: float = THRESHOLD_STD) -> float:
    s = np.asarray(score, dtype=float)
    return float(s.mean() + k * s.std())


def threshold_ranges(score, k: float = THRESHOLD_STD, gap: int | None = None) -> list[list[int]]:
    """Points with score > mean + k * std, as ranges. Points closer than
    `gap` join the same range, so a score hovering around the threshold
    reads as one flag, not a dozen."""
    s = np.asarray(score, dtype=float)
    n = len(s)
    above = np.flatnonzero(s > threshold(s, k))
    if len(above) == 0:
        return []
    if gap is None:
        gap = max(1, n // 200)
    groups = []
    start = prev = int(above[0])
    for i in above[1:]:
        i = int(i)
        if i - prev > gap:
            groups.append([start, prev])
            start = i
        prev = i
    groups.append([start, prev])
    return groups


def detector_caught(score, labels: list[list[int]]) -> bool:
    """Did one detector catch the anomaly on its own: does its own
    threshold flag touch a labeled anomaly."""
    return any(overlaps(r, l) for r in threshold_ranges(score) for l in labels)


def team_average(detectors) -> list[float]:
    """The point-wise mean of the detectors' scores. The pack stores each
    score min-max normalised over the window, so they average as they are."""
    return np.mean([np.asarray(d["score"], dtype=float) for d in detectors], axis=0).round(1).tolist()


def detector_flags(detectors, labels, n: int, rule: str = DETECTOR_RULE) -> tuple[list[dict], dict]:
    """Each detector's threshold, flags and catch, and the detectors' side:
    {"flags", "score", "threshold"} (score and threshold only for the
    average). `detectors` is [{"name", "score"}]."""
    each = []
    for d in detectors:
        flags = threshold_ranges(d["score"])
        each.append({
            "name": d["name"],
            "threshold": round(threshold(d["score"]), 1),
            "flags": flags,
            "caught": any(overlaps(r, l) for r in flags for l in labels),
        })
    if rule == "pooled":
        return each, {"flags": clean_ranges([r for d in each for r in d["flags"]], n),
                      "score": None, "threshold": None}
    if rule != "average":
        raise ValueError(f"unknown DETECTOR_RULE {rule!r}")
    team = team_average(detectors)
    return each, {"flags": threshold_ranges(team), "score": team, "threshold": round(threshold(team), 1)}


# --------------------------------------------------------------------------
# One side's result on one series
# --------------------------------------------------------------------------

def evaluate(ranges, labels) -> dict:
    hit_mask = [any(overlaps(r, l) for r in ranges) for l in labels]
    false_alarms = sum(not any(overlaps(r, l) for l in labels) for r in ranges)
    hits = sum(hit_mask)
    clean = int(not labels and not ranges)
    return {
        "hits": hits,
        "false_alarms": false_alarms,
        "missed": len(labels) - hits,
        "clean": clean,
        "points": hits - false_alarms + clean,
        "label_hits": hit_mask,
    }


def result_key(ev: dict, n_labels: int) -> str:
    """found | partial | clean | missed | false alarm -- picks the mark on the
    summary card (filled diamond, hollow diamond, flat bar)."""
    if n_labels == 0:
        return "clean" if ev["clean"] else "false alarm"
    if ev["hits"] == n_labels:
        return "found"
    if ev["hits"] > 0:
        return "partial"
    return "false alarm" if ev["false_alarms"] else "missed"


def result_text(ev: dict, n_labels: int) -> str:
    key = result_key(ev, n_labels)
    text = {
        "found": "Found it" if n_labels == 1 else f"Found all {n_labels}",
        "partial": f"Found {ev['hits']} of {n_labels}",
        "clean": "Left it clean",
        "missed": "Missed",
        "false alarm": "False alarm" if ev["false_alarms"] == 1 else f"{ev['false_alarms']} false alarms",
    }[key]
    if key in ("found", "partial") and ev["false_alarms"]:
        text += f" · {ev['false_alarms']} false alarm" + ("s" if ev["false_alarms"] > 1 else "")
    return text


def outcome(you: dict, det: dict) -> str:
    """you | det | both | nobody -- the banner on the summary card."""
    if you["points"] > det["points"]:
        return "you"
    if det["points"] > you["points"]:
        return "det"
    return "both" if you["points"] > 0 else "nobody"


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------

def _count(k: int, word: str) -> str:
    if k == 0:
        return f"no {word}s"
    if k == 1:
        return f"one {word}"
    return f"{k} {word}s"


def _names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def verdict(you: dict, det: dict, n_labels: int, caught: list[str], team_size: int,
            rule: str = DETECTOR_RULE) -> tuple[str, str]:
    """Headline and sub-line for the Reveal screen. `caught` names the
    detectors whose own flags touch an anomaly. Under the average rule the
    team can miss what one of them caught alone; the sub-line says so rather
    than contradict the lit lanes."""
    if n_labels == 0:
        you_clean, det_clean = bool(you["clean"]), det["false_alarms"] == 0
        if you_clean and det_clean:
            tail = "Nobody took the bait."
        elif you_clean:
            tail = "You said so. The detectors took the bait."
        elif det_clean:
            tail = "The detectors left it alone. You took the bait."
        else:
            tail = "Everyone took the bait."
        return "NOTHING TO FIND", f"This window had no anomaly. {tail}"

    you_hit, det_hit = you["hits"] > 0, det["hits"] > 0
    if you_hit and not det_hit:
        head = "YOU FOUND IT. THE DETECTORS DIDN’T."
    elif det_hit and not you_hit:
        head = "THE DETECTORS FOUND IT. YOU DIDN’T."
    elif you_hit and det_hit:
        head = "EVERYONE GOT THIS ONE"
    else:
        head = "NOBODY FOUND THIS ONE"

    you_part = (f"{_count(you['hits'], 'hit')}, {_count(you['false_alarms'], 'false alarm')}"
                .capitalize() + ".")
    who = _names(caught) if len(caught) <= 2 else f"{len(caught)} of {team_size} detectors"
    fa = f"; they raised {_count(det['false_alarms'], 'false alarm')}" if det["false_alarms"] else ""
    if det_hit:
        det_part = f"The detectors: {_count(det['hits'], 'hit')}, {_count(det['false_alarms'], 'false alarm')}."
        if rule == "pooled":
            det_part = f"{who} caught it. " + det_part
    elif caught:
        det_part = f"The detectors missed it{fa}, though {who} alone crossed {'its' if len(caught) == 1 else 'their'} line."
    else:
        det_part = f"Not one detector flagged it{fa}."
    if n_labels > 1:
        you_part = f"{n_labels} labeled anomalies. " + you_part
    return head, f"{you_part} {det_part}"


def score_series(ranges, labels, detectors, n: int) -> dict:
    """Everything the Reveal and the log need for one series. `detectors` is
    [{"name", "score"}], the team in display order."""
    ranges = clean_ranges(ranges, n)
    each, side = detector_flags(detectors, labels, n)
    det_flags = side["flags"]
    you = evaluate(ranges, labels)
    det = evaluate(det_flags, labels)
    caught = [d["name"] for d in each if d["caught"]]
    head, sub = verdict(you, det, len(labels), caught, len(each))
    return {
        "ranges": ranges,
        "det_ranges": det_flags,
        "detectors": each,
        "team_score": side["score"],
        "team_threshold": side["threshold"],
        "you": you,
        "det": det,
        "outcome": outcome(you, det),
        "you_result": result_key(you, len(labels)),
        "det_result": result_key(det, len(labels)),
        "you_text": result_text(you, len(labels)),
        "det_text": result_text(det, len(labels)),
        "verdict": head,
        "verdict_sub": sub,
    }
