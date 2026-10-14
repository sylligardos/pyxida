import { NextResponse } from "next/server";
import { ctx, getRound, getSeries, handle, idxParam } from "@/lib/game/api";

export const GET = handle(async (_req: Request, { params }: { params: Promise<{ rid: string; idx: string }> }) => {
  const { pack } = await ctx();
  const p = await params;
  const idx = idxParam(p.idx);
  const s = getSeries(pack, getRound(p.rid), idx);
  return NextResponse.json({ idx, label: `SERIES ${s.id}`, n: s.values.length, values: s.values });
});
