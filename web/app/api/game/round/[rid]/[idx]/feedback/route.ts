import { NextResponse } from "next/server";
import { body, ctx, getRound, getSeries, handle, HttpError, idxParam } from "@/lib/game/api";

const ANSWERS = new Set(["see", "cannot", "else"]);

export const POST = handle(async (req: Request, { params }: { params: Promise<{ rid: string; idx: string }> }) => {
  const { packs, store } = await ctx();
  const p = await params;
  const idx = idxParam(p.idx);
  const round = getRound(packs, p.rid);
  const s = await getSeries(round, idx);
  const answer = (await body(req)).answer;
  if (typeof answer !== "string" || !ANSWERS.has(answer)) throw new HttpError(400, "answer must be one of cannot, else, see");
  store.logFeedback(round.id, idx, s.id, answer);
  return NextResponse.json({ ok: true });
});
