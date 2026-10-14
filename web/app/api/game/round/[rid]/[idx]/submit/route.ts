import { NextResponse } from "next/server";
import { body, ctx, getRound, getSeries, handle, HttpError, idxParam } from "@/lib/game/api";
import { TIER_NOTE } from "@/lib/game/pack";
import { DETECTOR_RULE, scoreSeries } from "@/lib/game/scoring";

export const POST = handle(async (req: Request, { params }: { params: Promise<{ rid: string; idx: string }> }) => {
  const { pack, store } = await ctx();
  const p = await params;
  const idx = idxParam(p.idx);
  const round = getRound(p.rid);
  const s = getSeries(pack, round, idx);
  const data = await body(req);
  const nothing = !!data.nothing;
  let ranges: [number, number][] = [];
  if (!nothing) {
    const raw = data.ranges ?? [];
    const num = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
    if (!Array.isArray(raw) || !raw.every((r) => Array.isArray(r) && r.length >= 2 && num(r[0]) && num(r[1]))) {
      throw new HttpError(400, "ranges must be a list of [start, end] pairs");
    }
    ranges = raw.slice(0, 5).map((r) => [r[0], r[1]]);
  }
  const n = s.values.length;
  const result = scoreSeries(ranges, s.labels, s.detectors, n);
  const elapsed = typeof data.elapsed_ms === "number" ? Math.round(data.elapsed_ms) : null;
  const view = data.view && typeof data.view === "object" && !Array.isArray(data.view) ? (data.view as Record<string, unknown>) : {};
  store.logPlay(round.id, idx, s.id, s.tier, nothing, result, elapsed, { ...view, det_rule: DETECTOR_RULE });

  const pick = (e: typeof result.you) => ({ hits: e.hits, false_alarms: e.false_alarms, missed: e.missed, clean: e.clean, points: e.points });
  const team = result.detectors.map((d, i) => ({ ...d, score: s.detectors[i].score }));
  return NextResponse.json({
    idx, label: `SERIES ${s.id}`, n,
    tier: s.tier, tier_note: TIER_NOTE[s.tier],
    labels: s.labels,
    team_score: result.team_score, team_threshold: result.team_threshold,
    ranges: result.ranges, det_ranges: result.det_ranges,
    you: pick(result.you), det: pick(result.det),
    you_hits: result.you.label_hits, det_hits: result.det.label_hits,
    outcome: result.outcome,
    you_result: result.you_result, det_result: result.det_result,
    you_text: result.you_text, det_text: result.det_text,
    verdict: result.verdict, verdict_sub: result.verdict_sub,
    detectors: team, caught: team.filter((d) => d.caught).length,
  });
});
