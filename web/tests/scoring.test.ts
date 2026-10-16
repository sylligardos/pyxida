// The TypeScript scoring must give what scripts/needle/scoring.py gives. The golden
// file comes from scripts/scoring_golden.py on the synthetic dev pack.

import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "fs";
import path from "path";
import { scoreSeries, type SeriesResult } from "../lib/game/scoring";

const REPO = path.join(__dirname, "..", "..");
const GOLDEN = path.join(__dirname, "scoring_golden.json");
const PACK = path.join(REPO, "data", "game", "dev");
// Both are generated: python scripts/needle/make_dev_pack.py && python scripts/scoring_golden.py
const ready = existsSync(GOLDEN) && existsSync(path.join(PACK, "manifest.json"));
const golden = ready ? (JSON.parse(readFileSync(GOLDEN, "utf8")) as { id: number; case: string; ranges: number[][]; solo?: boolean; result: SeriesResult }[]) : [];
const series = new Map<number, { values: number[]; labels: [number, number][]; detectors: { name: string; score: number[] }[] }>(
  ready ? JSON.parse(readFileSync(path.join(PACK, "manifest.json"), "utf8")).series
    .map((e: { id: number; file: string }) => [e.id, JSON.parse(readFileSync(path.join(PACK, e.file), "utf8"))]) : []);


describe.skipIf(!ready)("scoring port", () => {
  it("has cases", () => { expect(golden.length).toBeGreaterThan(50); });
  for (const g of golden) {
    it(`series ${g.id} · ${g.case}`, () => {
      const s = series.get(g.id)!;
      const r = scoreSeries(g.ranges, s.labels, g.solo ? s.detectors.slice(0, 1) : s.detectors, s.values.length);
      expect(r).toEqual(g.result);
    });
  }
});
