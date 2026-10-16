// Needle: the play log and the leaderboard. Three tables (rounds, plays,
// feedback), in SQLite while the demo runs locally. The Store interface is
// what the routes use, so a Postgres store can take its place online.

import { appendFileSync, existsSync, mkdirSync } from "fs";
import path from "path";
import Database from "better-sqlite3";
import type { SeriesResult } from "./scoring";

export type BoardRow = { round_id: string; name: string; score: number; results: string };
export type Stats = {
  plays: number; hi_score: number | null; det_avg: number | null;
  humans_found_pct: number | null; beat_pct: number | null;
};

export interface Store {
  newRound(id: string, nick: string, pack: string, series: number[], difficulty: string): void;
  getRound(id: string): { id: string; nick: string; pack: string; series: number[] } | null;
  logPlay(roundId: string, idx: number, seriesId: number, tier: string, nothing: boolean, result: SeriesResult, elapsedMs: number | null, view: Record<string, unknown> | null): void;
  logFeedback(roundId: string, idx: number, seriesId: number, answer: string): void;
  finishRound(roundId: string): { you_total: number; det_total: number; results: string };
  leaderboard(limit: number, todayOnly: boolean): BoardRow[];
  stats(todayOnly: boolean): Stats;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS rounds (
    id TEXT PRIMARY KEY, nick TEXT NOT NULL, pack TEXT NOT NULL, series TEXT NOT NULL,
    created REAL NOT NULL, finished REAL, you_total INTEGER, det_total INTEGER, results TEXT, difficulty TEXT);
CREATE TABLE IF NOT EXISTS plays (
    round_id TEXT NOT NULL, idx INTEGER NOT NULL, series_id INTEGER NOT NULL, tier TEXT NOT NULL,
    said_nothing INTEGER NOT NULL, ranges TEXT NOT NULL, det_ranges TEXT NOT NULL, n_labels INTEGER NOT NULL,
    you_hits INTEGER NOT NULL, you_fa INTEGER NOT NULL, you_points INTEGER NOT NULL,
    det_hits INTEGER NOT NULL, det_fa INTEGER NOT NULL, det_points INTEGER NOT NULL,
    label_hits TEXT NOT NULL, outcome TEXT NOT NULL, elapsed_ms INTEGER, view TEXT, created REAL NOT NULL,
    PRIMARY KEY (round_id, idx));
CREATE TABLE IF NOT EXISTS feedback (
    round_id TEXT NOT NULL, idx INTEGER NOT NULL, series_id INTEGER NOT NULL, answer TEXT NOT NULL,
    created REAL NOT NULL, PRIMARY KEY (round_id, idx));
`;

const LETTER: Record<string, string> = { you: "W", det: "L", both: "T", nobody: "T" };
const now = () => Date.now() / 1000;

function sinceOf(todayOnly: boolean): number {
  if (!todayOnly) return 0;
  const d = new Date(); d.setHours(0, 0, 0, 0);
  return d.getTime() / 1000;
}

export class SqliteStore implements Store {
  db: Database.Database;
  csvPath: string;
  constructor(file: string) {
    mkdirSync(path.dirname(file), { recursive: true });
    this.csvPath = path.join(path.dirname(file), "plays.csv");
    this.db = new Database(file);
    this.db.exec(SCHEMA);
    // Logs from before difficulties existed: add the column.
    const cols = (this.db.prepare("PRAGMA table_info(rounds)").all() as { name: string }[]).map((c) => c.name);
    if (!cols.includes("difficulty")) this.db.exec("ALTER TABLE rounds ADD COLUMN difficulty TEXT");
  }
  newRound(id: string, nick: string, pack: string, series: number[], difficulty: string) {
    this.db.prepare("INSERT INTO rounds (id, nick, pack, series, difficulty, created) VALUES (?, ?, ?, ?, ?, ?)").run(id, nick, pack, JSON.stringify(series), difficulty, now());
  }
  getRound(id: string) {
    const r = this.db.prepare("SELECT id, nick, pack, series FROM rounds WHERE id = ?").get(id) as { id: string; nick: string; pack: string; series: string } | undefined;
    return r ? { id: r.id, nick: r.nick, pack: r.pack, series: JSON.parse(r.series) as number[] } : null;
  }
  logPlay(roundId: string, idx: number, seriesId: number, tier: string, nothing: boolean, result: SeriesResult, elapsedMs: number | null, view: Record<string, unknown> | null) {
    const { you, det } = result;
    this.db.prepare("INSERT OR REPLACE INTO plays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(
      roundId, idx, seriesId, tier, nothing ? 1 : 0,
      JSON.stringify(result.ranges), JSON.stringify(result.det_ranges), you.label_hits.length,
      you.hits, you.false_alarms, you.points, det.hits, det.false_alarms, det.points,
      JSON.stringify(you.label_hits.map((a, i) => [a ? 1 : 0, det.label_hits[i] ? 1 : 0])),
      result.outcome, elapsedMs, view ? JSON.stringify(view) : null, now());
  }
  logFeedback(roundId: string, idx: number, seriesId: number, answer: string) {
    this.db.prepare("INSERT OR REPLACE INTO feedback VALUES (?, ?, ?, ?, ?)").run(roundId, idx, seriesId, answer, now());
  }
  // A series adds +1, 0 or -1 to the round: the sign of its points.
  finishRound(roundId: string) {
    const rows = this.db.prepare("SELECT * FROM plays WHERE round_id = ? ORDER BY idx").all(roundId) as Record<string, number | string | null>[];
    const you = rows.reduce((s, r) => s + Math.sign(r.you_points as number), 0), det = rows.reduce((s, r) => s + Math.sign(r.det_points as number), 0);
    const results = rows.map((r) => LETTER[r.outcome as string]).join("");
    const finished = now();
    this.db.prepare("UPDATE rounds SET finished = ?, you_total = ?, det_total = ?, results = ? WHERE id = ?").run(finished, you, det, results, roundId);
    this.appendCsv(roundId, finished, rows);
    return { you_total: you, det_total: det, results };
  }
  // Every finished round also goes to plays.csv next to the database: one
  // line per series, readable without sqlite, kept across restarts.
  appendCsv(roundId: string, finished: number, rows: Record<string, number | string | null>[]) {
    const round = this.db.prepare("SELECT nick, pack, difficulty FROM rounds WHERE id = ?").get(roundId) as { nick: string; pack: string; difficulty: string | null } | undefined;
    if (!round) return;
    const cols = ["finished", "round_id", "nick", "pack", "difficulty", "idx", "series_id", "tier", "said_nothing", "you_hits", "you_fa", "you_points", "det_hits", "det_fa", "det_points", "outcome", "elapsed_ms"];
    const q = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = rows.map((r) => [new Date(finished * 1000).toISOString(), roundId, round.nick, round.pack, round.difficulty ?? "",
      r.idx, r.series_id, r.tier, r.said_nothing, r.you_hits, r.you_fa, r.you_points, r.det_hits, r.det_fa, r.det_points, r.outcome, r.elapsed_ms].map(q).join(","));
    const file = this.csvPath;
    try {
      if (!existsSync(file)) appendFileSync(file, cols.join(",") + "\n");
      appendFileSync(file, lines.join("\n") + "\n");
    } catch (e) { console.error("plays.csv:", e); }
  }
  leaderboard(limit: number, todayOnly: boolean): BoardRow[] {
    return (this.db.prepare("SELECT id, nick, you_total, results FROM rounds WHERE finished IS NOT NULL AND finished >= ? ORDER BY you_total DESC, finished ASC LIMIT ?")
      .all(sinceOf(todayOnly), limit) as { id: string; nick: string; you_total: number; results: string }[])
      .map((r) => ({ round_id: r.id, name: r.nick, score: r.you_total, results: r.results }));
  }
  stats(todayOnly: boolean): Stats {
    const since = sinceOf(todayOnly);
    const r = this.db.prepare("SELECT COUNT(*) AS plays, MAX(you_total) AS hi, AVG(det_total) AS det_avg, SUM(CASE WHEN instr(results, 'W') > 0 THEN 1 ELSE 0 END) AS beat FROM rounds WHERE finished IS NOT NULL AND finished >= ?").get(since) as { plays: number; hi: number | null; det_avg: number | null; beat: number | null };
    let missed = 0, found = 0;
    for (const { label_hits } of this.db.prepare("SELECT label_hits FROM plays WHERE created >= ?").all(since) as { label_hits: string }[]) {
      for (const [youHit, detHit] of JSON.parse(label_hits) as [number, number][]) {
        if (!detHit) { missed += 1; found += youHit; }
      }
    }
    return {
      plays: r.plays, hi_score: r.hi,
      det_avg: r.det_avg === null ? null : Math.round(r.det_avg * 10) / 10,
      humans_found_pct: missed === 0 ? null : Math.round((100 * found) / missed),
      beat_pct: r.plays === 0 ? null : Math.round((100 * (r.beat ?? 0)) / r.plays),
    };
  }
}

export const DB_PATH = process.env.PYXIDA_GAME_DB ?? path.join(process.cwd(), "..", "data", "game", "plays.sqlite");

let store: Store | null = null;
export function getStore(): Store {
  if (!store) store = new SqliteStore(DB_PATH);
  return store;
}
