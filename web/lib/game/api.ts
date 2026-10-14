// Shared by the game's route handlers: the pack, the store, the round
// lookups and the board payload.

import { NextResponse } from "next/server";
import { loadPack, type Pack, type PackSeries, ROUND_MIX } from "./pack";
import { getStore } from "./store";

export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const TODAY_ONLY = process.env.PYXIDA_ALL_TIME !== "1";

export async function ctx() {
  return { pack: await loadPack(), store: getStore() };
}

export function getRound(id: string) {
  const r = getStore().getRound(id);
  if (!r) throw new HttpError(404, "No such round");
  return r;
}

export function getSeries(pack: Pack, round: { series: number[] }, idx: number): PackSeries {
  if (!(idx >= 0 && idx < round.series.length)) throw new HttpError(404, "No such series in this round");
  return pack.series.get(round.series[idx])!;
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

export function boardPayload(pack: Pack) {
  const store = getStore();
  return {
    stats: store.stats(TODAY_ONLY),
    leaderboard: store.leaderboard(8, TODAY_ONLY),
    team_size: pack.detectors.length,
    round_size: ROUND_MIX.length,
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
