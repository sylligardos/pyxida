import { randomUUID } from "crypto";
import { NextResponse } from "next/server";
import { body, cleanNick, ctx, handle, HttpError, packFor } from "@/lib/game/api";
import { cleanDifficulty, datasets, DIFFICULTIES, pickRound } from "@/lib/game/pack";

export const POST = handle(async (req: Request) => {
  const { packs, store } = await ctx();
  const data = await body(req);
  const pack = packFor(packs, data.pack);
  // A dataset is only offered when it has enough series for a round.
  const dataset = typeof data.dataset === "string" && data.dataset ? data.dataset : null;
  if (dataset && !datasets(pack).some((d) => d.id === dataset)) throw new HttpError(400, `No dataset ${dataset} in ${pack.id}`);
  const rid = randomUUID().replace(/-/g, "");
  const nick = cleanNick(data.nick);
  const difficulty = cleanDifficulty(data.difficulty);
  const series = pickRound(pack, DIFFICULTIES[difficulty].mix, dataset);
  store.newRound(rid, nick, pack.id, series, difficulty);
  return NextResponse.json({ round_id: rid, nick, count: series.length, team_size: pack.detectors.length, difficulty, time_limit_s: DIFFICULTIES[difficulty].time_s, pack: pack.id, dataset });
});
