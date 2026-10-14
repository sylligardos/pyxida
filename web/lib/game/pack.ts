// Needle: the content pack, read from disk (game/pack.py writes it). Later
// the same series live in a database table; only this file changes.

import { promises as fs } from "fs";
import path from "path";
import type { Range } from "./scoring";

export const TIERS = ["easy", "medium", "unsolved", "decoy"] as const;
export type Tier = (typeof TIERS)[number];

export type PackSeries = {
  id: number; tier: Tier; values: number[]; labels: Range[];
  detectors: { name: string; score: number[] }[]; source?: Record<string, unknown>;
};
export type Pack = { name: string; detectors: string[]; series: Map<number, PackSeries> };

const REPO = path.join(process.cwd(), "..");
export const PACK_PATH = process.env.PYXIDA_PACK ?? path.join(REPO, "data", "game", "tsb-ad");

let loaded: Promise<Pack> | null = null;

export function loadPack(dir = PACK_PATH): Promise<Pack> {
  if (!loaded) loaded = readPack(dir).catch((e) => { loaded = null; throw e; });
  return loaded;
}

async function readPack(dir: string): Promise<Pack> {
  const manifest = JSON.parse(await fs.readFile(path.join(dir, "manifest.json"), "utf8"));
  const series = new Map<number, PackSeries>();
  for (const entry of manifest.series as { file: string }[]) {
    const s = JSON.parse(await fs.readFile(path.join(dir, entry.file), "utf8")) as PackSeries;
    if (!TIERS.includes(s.tier)) throw new Error(`${entry.file}: unknown tier ${s.tier}`);
    for (const d of s.detectors) {
      if (d.score.length !== s.values.length) throw new Error(`${entry.file}: ${d.name} score has ${d.score.length} points, values ${s.values.length}`);
    }
    series.set(s.id, s);
  }
  if (!series.size) throw new Error(`${dir}: the pack has no series`);
  return { name: manifest.name ?? path.basename(dir), detectors: manifest.detectors, series };
}

export function byTier(pack: Pack): Record<string, number[]> {
  const out: Record<string, number[]> = Object.fromEntries(TIERS.map((t) => [t, []]));
  for (const s of pack.series.values()) (out[s.tier] ??= []).push(s.id);
  return out;
}

// One round: two easy, two medium, one unsolved, one decoy, in random order.
export const ROUND_MIX: Tier[] = ["easy", "easy", "medium", "medium", "unsolved", "decoy"];

export function pickRound(pack: Pack, mix = ROUND_MIX, rnd = Math.random): number[] {
  const shuffle = <T,>(xs: T[]) => { const a = [...xs]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const pool = Object.fromEntries(Object.entries(byTier(pack)).map(([t, ids]) => [t, shuffle(ids)]));
  const chosen: number[] = [];
  for (const tier of mix) if (pool[tier]?.length) chosen.push(pool[tier].pop()!);
  const rest = shuffle(Object.values(pool).flat());
  while (chosen.length < mix.length && rest.length) chosen.push(rest.pop()!);
  return shuffle(chosen);
}

export const TIER_NOTE: Record<Tier, string> = {
  easy: "Most of the detector team catches this one.",
  medium: "Only some detectors catch this one.",
  unsolved: "Even the best detector in the benchmark misses this one.",
  decoy: "Some series are clean on purpose.",
};
