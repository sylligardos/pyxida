import { NextResponse } from "next/server";
import { ctx, getRound, getSeries, handle, idxParam } from "@/lib/game/api";
import { opponentOf } from "@/lib/game/pack";

export const GET = handle(async (_req: Request, { params }: { params: Promise<{ rid: string; idx: string }> }) => {
  const { packs } = await ctx();
  const p = await params;
  const idx = idxParam(p.idx);
  const s = await getSeries(getRound(packs, p.rid), idx);
  return NextResponse.json({ idx, label: `SERIES ${s.id}`, n: s.values.length, values: s.values, opponent: opponentOf(s) });
});
