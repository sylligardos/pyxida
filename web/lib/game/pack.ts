// Needle: the content packs, read from disk (scripts/needle/pack.py writes them). One
// pack per benchmark, under data/game/<pack>/; the manifest is read once,
// a series when a round needs it (a pack holds hundreds of 10k-point
// series). Later the same series live in a database table; only this file
// changes.

import { promises as fs } from "fs";
import path from "path";
import type { Range } from "./scoring";

export const TIERS = ["easy", "medium", "unsolved", "decoy"] as const;
export type Tier = (typeof TIERS)[number];

export type Opponent = { name: string; vus_pr: number; rank: number; pool: number };
export type PackSeries = {
  id: number; tier: Tier; values: number[]; labels: Range[];
  detectors: { name: string; score: number[] }[];     // one entry: the opponent
  source?: { opponent?: Opponent } & Record<string, unknown>;
};
// The opponent card: from the pack when the builder wrote it, else the first detector.
export const opponentOf = (s: PackSeries): Opponent =>
  s.source?.opponent ?? { name: s.detectors[0]?.name ?? "Detectors", vus_pr: NaN, rank: 0, pool: s.detectors.length };
export type PackEntry = { id: number; tier: Tier; n: number; file: string; dataset: string };
export type Pack = {
  id: string; name: string; dir: string; detectors: string[];
  entries: Map<number, PackEntry>;
  cache: Map<number, Promise<PackSeries>>;
};

const REPO = path.join(process.cwd(), "..");
// PYXIDA_PACKS: the pack folders, comma separated; else every pack under data/game but dev.
const PACKS_ROOT = path.join(REPO, "data", "game");
export const ROUND_SIZE = 10;

let loaded: Promise<Map<string, Pack>> | null = null;

export function loadPacks(): Promise<Map<string, Pack>> {
  if (!loaded) loaded = readPacks().catch((e) => { loaded = null; throw e; });
  return loaded;
}

async function packDirs(): Promise<string[]> {
  if (process.env.PYXIDA_PACKS) return process.env.PYXIDA_PACKS.split(",").map((s) => s.trim()).filter(Boolean);
  if (process.env.PYXIDA_PACK) return [process.env.PYXIDA_PACK];
  // TSB-AD first: the first pack is the default when a round names none.
  const names = (await fs.readdir(PACKS_ROOT, { withFileTypes: true })).filter((d) => d.isDirectory() && d.name !== "dev").map((d) => d.name)
    .sort((x, y) => (x === "tsb-ad" ? -1 : y === "tsb-ad" ? 1 : x.localeCompare(y)));
  const dirs: string[] = [];
  for (const n of names) { try { await fs.access(path.join(PACKS_ROOT, n, "manifest.json")); dirs.push(path.join(PACKS_ROOT, n)); } catch { /* not a pack */ } }
  return dirs;
}

async function readPacks(): Promise<Map<string, Pack>> {
  const packs = new Map<string, Pack>();
  for (const dir of await packDirs()) {
    const manifest = JSON.parse(await fs.readFile(path.join(dir, "manifest.json"), "utf8"));
    const entries = new Map<number, PackEntry>();
    for (const e of manifest.series as PackEntry[]) {
      if (!TIERS.includes(e.tier)) throw new Error(`${dir}: ${e.file} has unknown tier ${e.tier}`);
      entries.set(e.id, { ...e, dataset: e.dataset ?? "" });
    }
    if (!entries.size) throw new Error(`${dir}: the pack has no series`);
    const id = path.basename(dir);
    packs.set(id, { id, name: manifest.name ?? id, dir, detectors: manifest.detectors, entries, cache: new Map() });
  }
  if (!packs.size) throw new Error(`No pack under ${PACKS_ROOT}`);
  return packs;
}

export function readSeries(pack: Pack, id: number): Promise<PackSeries> {
  const e = pack.entries.get(id);
  if (!e) throw new Error(`${pack.id}: no series ${id}`);
  if (!pack.cache.has(id)) {
    pack.cache.set(id, fs.readFile(path.join(pack.dir, e.file), "utf8").then((t) => {
      const s = JSON.parse(t) as PackSeries;
      for (const d of s.detectors) {
        if (d.score.length !== s.values.length) throw new Error(`${e.file}: ${d.name} score has ${d.score.length} points, values ${s.values.length}`);
      }
      return s;
    }).catch((err) => { pack.cache.delete(id); throw err; }));
  }
  return pack.cache.get(id)!;
}

// The datasets of a pack with enough series for a round, biggest first.
export function datasets(pack: Pack): { id: string; n: number }[] {
  const n = new Map<string, number>();
  for (const e of pack.entries.values()) if (e.dataset) n.set(e.dataset, (n.get(e.dataset) ?? 0) + 1);
  return Array.from(n, ([id, n]) => ({ id, n })).filter((d) => d.n >= ROUND_SIZE).sort((a, b) => b.n - a.n || a.id.localeCompare(b.id));
}

export function byTier(pack: Pack, dataset: string | null = null): Record<string, number[]> {
  const out: Record<string, number[]> = Object.fromEntries(TIERS.map((t) => [t, []]));
  for (const e of pack.entries.values()) if (!dataset || e.dataset === dataset) (out[e.tier] ??= []).push(e.id);
  return out;
}

// A round is ten series in random order; the difficulty sets the mix of
// tiers and the seconds per series.
export const DIFFICULTIES = {
  easy: { mix: ["easy", "easy", "easy", "easy", "easy", "easy", "medium", "medium", "decoy", "decoy"] as Tier[], time_s: 60 },
  normal: { mix: ["easy", "easy", "easy", "medium", "medium", "medium", "unsolved", "unsolved", "decoy", "decoy"] as Tier[], time_s: 45 },
  hard: { mix: ["medium", "medium", "unsolved", "unsolved", "unsolved", "unsolved", "unsolved", "unsolved", "decoy", "decoy"] as Tier[], time_s: 30 },
};
export type Difficulty = keyof typeof DIFFICULTIES;
export const DEFAULT_DIFFICULTY: Difficulty = "normal";
export const cleanDifficulty = (d: unknown): Difficulty => (typeof d === "string" && d in DIFFICULTIES ? d as Difficulty : DEFAULT_DIFFICULTY);
export const ROUND_MIX: Tier[] = DIFFICULTIES[DEFAULT_DIFFICULTY].mix;

// One series per slot of the mix, no repeats, from one dataset when asked.
// A tier that runs short is filled from whatever is left, so a small pack
// (or dataset) still plays.
export function pickRound(pack: Pack, mix = ROUND_MIX, dataset: string | null = null, rnd = Math.random): number[] {
  const shuffle = <T,>(xs: T[]) => { const a = [...xs]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const pool = Object.fromEntries(Object.entries(byTier(pack, dataset)).map(([t, ids]) => [t, shuffle(ids)]));
  const chosen: number[] = [];
  for (const tier of mix) if (pool[tier]?.length) chosen.push(pool[tier].pop()!);
  const rest = shuffle(Object.values(pool).flat());
  while (chosen.length < mix.length && rest.length) chosen.push(rest.pop()!);
  return shuffle(chosen);
}

export const TIER_NOTE: Record<Tier, string> = {
  easy: "Most detectors catch this one.",
  medium: "Only some detectors catch this one.",
  unsolved: "No detector in the benchmark gets this one. You face the best of them.",
  decoy: "Some series are clean on purpose.",
};
