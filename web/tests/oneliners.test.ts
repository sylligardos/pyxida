// Reference values come from sklearn.metrics.average_precision_score.

import { describe, expect, it } from "vitest";
import { ONE_LINERS, averagePrecision } from "../lib/oneliners";

describe("averagePrecision", () => {
  it("matches sklearn on a random case", () => {
    const y: [number, number][] = [[10, 13], [30, 30]];
    const s = [0.51, 0.95, 0.14, 0.95, 0.31, 0.42, 0.83, 0.41, 0.55, 0.03, 0.75, 1.04, 0.8300000000000001, 0.79, 0.3, 0.45, 0.13, 0.4, 0.2, 0.26, 0.75, 0.28, 0.49, 0.98, 0.96, 0.72, 0.54, 0.28, 0.16, 0.97, 1.02, 0.12, 0.62, 0.78, 0.61, 0.92, 0.04, 0.53, 0.46, 0.06];
    expect(averagePrecision(s, y)).toBeCloseTo(0.6108225108225108, 12);
  });
  it("groups ties like sklearn", () => {
    expect(averagePrecision([0.2, 0.9, 0.9, 0.1, 0.5], [[1, 1], [4, 4]])).toBeCloseTo(0.5833333333333333, 12);
  });
  it("is 1 for a perfect ranking and NaN without labels", () => {
    expect(averagePrecision([0, 0, 1, 1, 0], [[2, 3]])).toBe(1);
    expect(averagePrecision([0, 1], [])).toBeNaN();
  });
});

describe("one-liners", () => {
  const x = Array.from({ length: 500 }, (_, i) => Math.sin(i / 8) + (i % 7) / 50);
  x[200] += 4;                                   // a spike
  for (let i = 350; i < 380; i++) x[i] = x[350]; // a flat segment
  for (const o of ONE_LINERS) {
    it(`${o.title} gives a 0..1 score of the right length`, () => {
      const s = o.run(x, 20);
      expect(s.length).toBe(x.length);
      let lo = Infinity, hi = -Infinity;
      for (const v of s) { if (v < lo) lo = v; if (v > hi) hi = v; }
      expect(lo).toBe(0); expect(hi).toBe(1);
    });
  }
  it("abs(diff) and movstd put the spike first; flat puts the flat segment on top", () => {
    const by = (id: string) => ONE_LINERS.find((o) => o.id === id)!.run(x, 20);
    expect(averagePrecision(by("absdiff"), [[200, 200]])).toBeGreaterThan(0.4);
    expect(averagePrecision(by("movstd"), [[200, 200]])).toBeGreaterThan(0.05);
    expect(averagePrecision(by("flat"), [[351, 379]])).toBeGreaterThan(0.9);
  });
  it("movmin equals a brute-force rolling min", () => {
    const m = ONE_LINERS.find((o) => o.id === "movmin")!;
    const r = Array.from({ length: 97 }, (_, i) => Math.sin(i * 1.3) * (i % 5));
    const got = m.run(r, 9);
    const half = 4, mins = r.map((_, i) => Math.min(...r.slice(Math.max(0, i - half), Math.min(r.length, i - half + 9))));
    const med = [...mins].sort((a, b) => a - b)[48];
    const want = mins.map((v) => Math.abs(v - med)); const lo = Math.min(...want), hi = Math.max(...want);
    want.forEach((v, i) => expect(got[i]).toBeCloseTo((v - lo) / (hi - lo), 5));
  });
});
