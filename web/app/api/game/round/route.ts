import { randomUUID } from "crypto";
import { NextResponse } from "next/server";
import { body, cleanNick, ctx, handle } from "@/lib/game/api";
import { pickRound } from "@/lib/game/pack";

export const POST = handle(async (req: Request) => {
  const { pack, store } = await ctx();
  const data = await body(req);
  const rid = randomUUID().replace(/-/g, "");
  const nick = cleanNick(data.nick);
  const series = pickRound(pack);
  store.newRound(rid, nick, pack.name, series);
  return NextResponse.json({ round_id: rid, nick, count: series.length, team_size: pack.detectors.length });
});
