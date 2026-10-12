"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- the play log and the leaderboard, in one SQLite file.

Three tables, all anonymous (the nickname is the only thing a player types):

    rounds     one row per round of six: nickname, totals, finished or not
    plays      one row per series played: the player's ranges, the
               detectors' flags, both results, time spent, and which labeled
               anomalies each side hit (for the "humans found X%" line)
    feedback   the answer to "Now that you've seen it"

The analysis reads this file directly; nothing here is needed to play.
"""

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS rounds (
    id          TEXT PRIMARY KEY,
    nick        TEXT NOT NULL,
    pack        TEXT NOT NULL,
    series      TEXT NOT NULL,          -- JSON list of series ids, in play order
    created     REAL NOT NULL,
    finished    REAL,
    you_total   INTEGER,
    det_total   INTEGER,
    results     TEXT                    -- one letter per series: W, T or L
);
CREATE TABLE IF NOT EXISTS plays (
    round_id     TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    series_id    INTEGER NOT NULL,
    tier         TEXT NOT NULL,
    said_nothing INTEGER NOT NULL,      -- pressed "Nothing here"
    ranges       TEXT NOT NULL,         -- JSON, player's ranges after cleaning
    det_ranges   TEXT NOT NULL,         -- JSON, the team's flags
    n_labels     INTEGER NOT NULL,
    you_hits     INTEGER NOT NULL,
    you_fa       INTEGER NOT NULL,
    you_points   INTEGER NOT NULL,
    det_hits     INTEGER NOT NULL,
    det_fa       INTEGER NOT NULL,
    det_points   INTEGER NOT NULL,
    label_hits   TEXT NOT NULL,         -- JSON [[you_hit, det_hit], ...] per label
    outcome      TEXT NOT NULL,
    elapsed_ms   INTEGER,
    view         TEXT,                  -- JSON, zoom/pan activity from the browser
    created      REAL NOT NULL,
    PRIMARY KEY (round_id, idx)
);
CREATE TABLE IF NOT EXISTS feedback (
    round_id   TEXT NOT NULL,
    idx        INTEGER NOT NULL,
    series_id  INTEGER NOT NULL,
    answer     TEXT NOT NULL,           -- see | cannot | else
    created    REAL NOT NULL,
    PRIMARY KEY (round_id, idx)
);
"""

LETTER = {"you": "W", "det": "L", "both": "T", "nobody": "T"}


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ---------------------------------------------------------------- writes

    def new_round(self, round_id: str, nick: str, pack: str, series: list[int]):
        self.db.execute(
            "INSERT INTO rounds (id, nick, pack, series, created) VALUES (?, ?, ?, ?, ?)",
            (round_id, nick, pack, json.dumps(series), time.time()))
        self.db.commit()

    def log_play(self, round_id: str, idx: int, series_id: int, tier: str, nothing: bool,
                 result: dict, elapsed_ms: int | None, view: dict | None):
        you, det = result["you"], result["det"]
        self.db.execute(
            "INSERT OR REPLACE INTO plays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (round_id, idx, series_id, tier, int(nothing),
             json.dumps(result["ranges"]), json.dumps(result["det_ranges"]),
             len(you["label_hits"]),
             you["hits"], you["false_alarms"], you["points"],
             det["hits"], det["false_alarms"], det["points"],
             json.dumps([[int(a), int(b)] for a, b in zip(you["label_hits"], det["label_hits"])]),
             result["outcome"], elapsed_ms, json.dumps(view) if view else None, time.time()))
        self.db.commit()

    def log_feedback(self, round_id: str, idx: int, series_id: int, answer: str):
        self.db.execute("INSERT OR REPLACE INTO feedback VALUES (?, ?, ?, ?, ?)",
                        (round_id, idx, series_id, answer, time.time()))
        self.db.commit()

    def finish_round(self, round_id: str) -> dict:
        rows = self.db.execute(
            "SELECT you_points, det_points, outcome FROM plays WHERE round_id = ? ORDER BY idx",
            (round_id,)).fetchall()
        you = sum(r["you_points"] for r in rows)
        det = sum(r["det_points"] for r in rows)
        results = "".join(LETTER[r["outcome"]] for r in rows)
        self.db.execute(
            "UPDATE rounds SET finished = ?, you_total = ?, det_total = ?, results = ? WHERE id = ?",
            (time.time(), you, det, results, round_id))
        self.db.commit()
        return {"you_total": you, "det_total": det, "results": results}

    # ----------------------------------------------------------------- reads

    def _since(self, today_only: bool) -> float:
        if not today_only:
            return 0.0
        t = time.localtime()
        return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))

    def leaderboard(self, limit: int = 8, today_only: bool = True) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, nick, you_total, results FROM rounds WHERE finished IS NOT NULL "
            "AND finished >= ? ORDER BY you_total DESC, finished ASC LIMIT ?",
            (self._since(today_only), limit)).fetchall()
        return [{"round_id": r["id"], "name": r["nick"], "score": r["you_total"],
                 "results": r["results"]} for r in rows]

    def stats(self, today_only: bool = True) -> dict:
        since = self._since(today_only)
        r = self.db.execute(
            "SELECT COUNT(*) AS plays, MAX(you_total) AS hi, AVG(det_total) AS det_avg "
            "FROM rounds WHERE finished IS NOT NULL AND finished >= ?", (since,)).fetchone()

        # Of the labeled anomalies the detectors missed, how many did a human
        # find. Counted over every series played, finished round or not.
        missed = found = 0
        for (hits,) in self.db.execute("SELECT label_hits FROM plays WHERE created >= ?", (since,)):
            for you_hit, det_hit in json.loads(hits):
                if not det_hit:
                    missed += 1
                    found += you_hit
        return {
            "plays": r["plays"],
            "hi_score": r["hi"],
            "det_avg": None if r["det_avg"] is None else round(r["det_avg"], 1),
            "humans_found_pct": None if missed == 0 else round(100 * found / missed),
        }
