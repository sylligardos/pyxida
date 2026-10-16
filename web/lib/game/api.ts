// Shared by the game's route handlers: the pack, the store, the round
// lookups and the board payload.

import { NextResponse } from "next/server";
import { datasets, DIFFICULTIES, loadPacks, type Pack, type PackSeries, readSeries, ROUND_MIX } from "./pack";
import { getStore } from "./store";

export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const TODAY_ONLY = process.env.PYXIDA_ALL_TIME !== "1";

export async function ctx() {
  return { packs: await loadPacks(), store: getStore() };
}

// The pack a request names, else the first one.
export function packFor(packs: Map<string, Pack>, id: unknown): Pack {
  if (typeof id === "string" && packs.has(id)) return packs.get(id)!;
  return packs.values().next().value!;
}

export function getRound(packs: Map<string, Pack>, id: string) {
  const r = getStore().getRound(id);
  if (!r) throw new HttpError(404, "No such round");
  const pack = packs.get(r.pack);
  if (!pack) throw new HttpError(404, `The pack of this round (${r.pack}) is not loaded`);
  return { ...r, pack };
}

export function getSeries(round: { pack: Pack; series: number[] }, idx: number): Promise<PackSeries> {
  if (!(idx >= 0 && idx < round.series.length)) throw new HttpError(404, "No such series in this round");
  return readSeries(round.pack, round.series[idx]);
}

export async function body(req: Request): Promise<Record<string, unknown>> {
  let data: unknown;
  try { data = await req.json(); } catch { throw new HttpError(400, "Expected a JSON body"); }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new HttpError(400, "Expected a JSON object");
  return data as Record<string, unknown>;
}

export function cleanNick(nick: unknown): string {
  const s = String(nick ?? "").toUpperCase().replace(/[^A-Z0-9 _.\-]/g, "").trim().slice(0, 12);
  return s || "ANON";
}

export function boardPayload(packs: Map<string, Pack>) {
  const store = getStore();
  const first = packs.values().next().value!;
  return {
    stats: store.stats(TODAY_ONLY),
    leaderboard: store.leaderboard(8, TODAY_ONLY),
    team_size: first.detectors.length,
    round_size: ROUND_MIX.length,
    packs: Array.from(packs.values(), (p) => ({ id: p.id, name: p.name, team: p.detectors, datasets: datasets(p) })),
    difficulties: Object.fromEntries(Object.entries(DIFFICULTIES).map(([k, v]) => [k, { count: v.mix.length, time_s: v.time_s }])),
  };
}

export function idxParam(s: string): number {
  if (!/^\d+$/.test(s)) throw new HttpError(404, "No such series in this round");
  return Number(s);
}

// Wraps a handler so an HttpError becomes a response with its status.
export function handle<T extends unknown[]>(fn: (...args: T) => Promise<Response>) {
  return async (...args: T): Promise<Response> => {
    try { return await fn(...args); } catch (e) {
      if (e instanceof HttpError) return NextResponse.json({ error: e.message }, { status: e.status });
      console.error(e);
      return NextResponse.json({ error: "Game server error" }, { status: 500 });
    }
  };
}
