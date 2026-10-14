import { NextResponse } from "next/server";
import { boardPayload, ctx, handle } from "@/lib/game/api";

export const dynamic = "force-dynamic";

export const GET = handle(async () => {
  const { pack } = await ctx();
  return NextResponse.json(boardPayload(pack));
});
