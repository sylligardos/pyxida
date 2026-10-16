import { NextResponse } from "next/server";
import { boardPayload, ctx, getRound, handle } from "@/lib/game/api";

export const POST = handle(async (_req: Request, { params }: { params: Promise<{ rid: string }> }) => {
  const { packs, store } = await ctx();
  const round = getRound(packs, (await params).rid);
  const totals = store.finishRound(round.id);
  const board = boardPayload(packs);
  const k = board.leaderboard.findIndex((r) => r.round_id === round.id);
  return NextResponse.json({ ...totals, rank: k < 0 ? null : k, ...board });
});
