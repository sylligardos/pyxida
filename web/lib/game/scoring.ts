// Needle: the scoring rules, ported from game/scoring.py. That file stays
// the reference; tests/scoring.test.ts checks this port against its output.
//
// A range is a pair [a, b] of inclusive point indices.
//   hit           a labeled anomaly that at least one range overlaps (+1),
//                 counted per anomaly, not per range
//   false alarm   a range that overlaps no labeled anomaly (-1)
//   clean decoy   a series with no anomaly, left unmarked (+1)
// The detectors play by the same rules but decide on their own: the team
// average score, flagged wherever it is more than THRESHOLD_STD standard
// deviations above its mean (DETECTOR_RULE "average"), or every detector on
// its own threshold with all flags counted together ("pooled").

export type Range = [number, number];
export type Detector = { name: string; score: ArrayLike<number> };

export const THRESHOLD_STD = 3;
export const DETECTOR_RULE: "average" | "pooled" = "average";
// A range wider than this share of the window is too wide: a false alarm
// whatever it covers. Marking the whole series is not finding the anomaly.
export const MAX_RANGE_FRACTION = 0.10;
export const maxRangeLen = (n: number) => Math.max(1, Math.floor(n * MAX_RANGE_FRACTION));

// numpy's .round(d): scale, round half to even, unscale.
export function roundHalfEven(x: number, digits = 0): number {
  const m = Math.pow(10, digits);
  const v = x * m;
  const f = Math.floor(v), diff = v - f;
  let r: number;
  if (Math.abs(diff - 0.5) < 1e-9) r = f % 2 === 0 ? f : f + 1;
  else r = Math.round(v);
  return r / m;
}

// Python's built-in round(x, d): the correctly rounded decimal of the exact
// binary value (so 0.35 -> 0.3, because 0.35 is really 0.34999...), half to
// even only on an exact tie such as 1.25. toFixed does the first part.
export function pyRound(x: number, digits: number): number {
  const m = Math.pow(10, digits);
  const v = x * m;
  if (v - Math.floor(v) === 0.5) return roundHalfEven(x, digits);
  return Number(x.toFixed(digits));
}

// ---------------------------------------------------------------- ranges

export function cleanRanges(ranges: ArrayLike<ArrayLike<number>> | null | undefined, n: number): Range[] {
  const out: Range[] = [];
  for (const r of Array.from(ranges ?? [])) {
    const a = roundHalfEven(Math.min(r[0], r[1])), b = roundHalfEven(Math.max(r[0], r[1]));
    if (b < 0 || a > n - 1) continue;
    out.push([Math.max(0, a), Math.min(n - 1, b)]);
  }
  out.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  const merged: Range[] = [];
  for (const [a, b] of out) {
    if (merged.length && a <= merged[merged.length - 1][1] + 1) merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], b);
    else merged.push([a, b]);
  }
  return merged;
}

export function overlaps(r: Range, s: Range): boolean {
  return r[0] <= s[1] && r[1] >= s[0];
}

export function labelsToRanges(labels: ArrayLike<number>): Range[] {
  const out: Range[] = [];
  let start = -1;
  for (let i = 0; i < labels.length; i++) {
    const on = !!labels[i];
    if (on && start < 0) start = i;
    if (!on && start >= 0) { out.push([start, i - 1]); start = -1; }
  }
  if (start >= 0) out.push([start, labels.length - 1]);
  return out;
}

// ------------------------------------------------------------- detectors

function meanStd(s: ArrayLike<number>): [number, number] {
  const n = s.length;
  let sum = 0;
  for (let i = 0; i < n; i++) sum += s[i];
  const mean = sum / n;
  let sq = 0;
  for (let i = 0; i < n; i++) { const d = s[i] - mean; sq += d * d; }
  return [mean, Math.sqrt(sq / n)];
}

export function threshold(score: ArrayLike<number>, k = THRESHOLD_STD): number {
  const [m, s] = meanStd(score);
  return m + k * s;
}

export function thresholdRanges(score: ArrayLike<number>, k = THRESHOLD_STD, gap: number | null = null): Range[] {
  const n = score.length;
  const t = threshold(score, k);
  const above: number[] = [];
  for (let i = 0; i < n; i++) if (score[i] > t) above.push(i);
  if (!above.length) return [];
  if (gap === null) gap = Math.max(1, Math.floor(n / 200));
  const groups: Range[] = [];
  let start = above[0], prev = above[0];
  for (let j = 1; j < above.length; j++) {
    const i = above[j];
    if (i - prev > gap) { groups.push([start, prev]); start = i; }
    prev = i;
  }
  groups.push([start, prev]);
  return groups;
}

export function teamAverage(detectors: Detector[]): number[] {
  const n = detectors[0].score.length;
  const out = new Array<number>(n);
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (const d of detectors) s += d.score[i];
    out[i] = roundHalfEven(s / detectors.length, 1);
  }
  return out;
}

export type DetectorResult = { name: string; threshold: number; flags: Range[]; caught: boolean };
export type Side = { flags: Range[]; score: number[] | null; threshold: number | null };

export function detectorFlags(detectors: Detector[], labels: Range[], n: number, rule = DETECTOR_RULE): [DetectorResult[], Side] {
  const each: DetectorResult[] = detectors.map((d) => {
    const flags = thresholdRanges(d.score);
    return { name: d.name, threshold: pyRound(threshold(d.score), 1), flags, caught: flags.some((r) => labels.some((l) => overlaps(r, l))) };
  });
  if (rule === "pooled") return [each, { flags: cleanRanges(each.flatMap((d) => d.flags), n), score: null, threshold: null }];
  const team = teamAverage(detectors);
  return [each, { flags: thresholdRanges(team), score: team, threshold: pyRound(threshold(team), 1) }];
}

// ------------------------------------------------- one side, one series

// round_points: what the series adds to the round, the sign of points. A
// detector with fifty false alarms loses the series, not the round.
export type Evaluation = { hits: number; false_alarms: number; missed: number; clean: number; points: number; round_points: number; label_hits: boolean[]; too_wide: number };

export function evaluate(ranges: Range[], labels: Range[], n: number | null = null): Evaluation {
  const limit = n ? maxRangeLen(n) : null;
  const wide = ranges.filter((r) => limit !== null && r[1] - r[0] + 1 > limit);
  const fair = ranges.filter((r) => !wide.includes(r));
  const label_hits = labels.map((l) => fair.some((r) => overlaps(r, l)));
  const false_alarms = fair.filter((r) => !labels.some((l) => overlaps(r, l))).length + wide.length;
  const hits = label_hits.filter(Boolean).length;
  const clean = !labels.length && !ranges.length ? 1 : 0;
  const points = hits - false_alarms + clean;
  return { hits, false_alarms, missed: labels.length - hits, clean, points, round_points: Math.sign(points), label_hits, too_wide: wide.length };
}

export type ResultKey = "found" | "partial" | "clean" | "missed" | "false alarm";

export function resultKey(ev: Evaluation, nLabels: number): ResultKey {
  if (nLabels === 0) return ev.clean ? "clean" : "false alarm";
  if (ev.hits === nLabels) return "found";
  if (ev.hits > 0) return "partial";
  return ev.false_alarms ? "false alarm" : "missed";
}

export function resultText(ev: Evaluation, nLabels: number): string {
  const key = resultKey(ev, nLabels);
  let text = {
    found: nLabels === 1 ? "Found it" : `Found all ${nLabels}`,
    partial: `Found ${ev.hits} of ${nLabels}`,
    clean: "Left it clean",
    missed: "Missed",
    "false alarm": ev.false_alarms === 1 ? "False alarm" : `${ev.false_alarms} false alarms`,
  }[key];
  if ((key === "found" || key === "partial") && ev.false_alarms) text += ` · ${ev.false_alarms} false alarm${ev.false_alarms > 1 ? "s" : ""}`;
  if (ev.too_wide) text += ` · ${ev.too_wide} too wide`;
  return text;
}

export type Outcome = "you" | "det" | "both" | "nobody";

// By what the series adds to the round, so two negative scores tie.
export function outcome(you: Evaluation, det: Evaluation): Outcome {
  const a = you.round_points, b = det.round_points;
  if (a > b) return "you";
  if (b > a) return "det";
  return a > 0 ? "both" : "nobody";
}

// ----------------------------------------------------------------- words

const count = (k: number, word: string) => (k === 0 ? `no ${word}s` : k === 1 ? `one ${word}` : `${k} ${word}s`);
const names = (xs: string[]) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

// With `opponent` (the single detector the player faces) the words name it;
// without, they say "the detectors" and `caught` names the team members.
export function verdict(you: Evaluation, det: Evaluation, nLabels: number, caught: string[], teamSize: number, rule = DETECTOR_RULE, opponent: string | null = null): [string, string] {
  const name = opponent ?? "The detectors";
  const they = opponent ? "it" : "they";
  if (nLabels === 0) {
    const youClean = !!you.clean, detClean = det.false_alarms === 0;
    const tail = youClean && detClean ? "Nobody took the bait."
      : youClean ? `You said so. ${name} took the bait.`
        : detClean ? `${name} left it alone. You took the bait.`
          : "Everyone took the bait.";
    return ["NOTHING TO FIND", `This window had no anomaly. ${tail}`];
  }
  const youHit = you.hits > 0, detHit = det.hits > 0;
  const head = youHit && !detHit ? `YOU FOUND IT. ${name.toUpperCase()} DIDN’T.`
    : detHit && !youHit ? `${name.toUpperCase()} FOUND IT. YOU DIDN’T.`
      : youHit && detHit ? (opponent ? "YOU BOTH GOT THIS ONE" : "EVERYONE GOT THIS ONE") : "NOBODY FOUND THIS ONE";

  let youPart = `${capitalize(`${count(you.hits, "hit")}, ${count(you.false_alarms, "false alarm")}`)}.`;
  const who = caught.length <= 2 ? names(caught) : `${caught.length} of ${teamSize} detectors`;
  const fa = det.false_alarms ? `; ${they} raised ${count(det.false_alarms, "false alarm")}` : "";
  let detPart: string;
  if (detHit) {
    detPart = `${name}: ${count(det.hits, "hit")}, ${count(det.false_alarms, "false alarm")}.`;
    if (rule === "pooled" && !opponent) detPart = `${who} caught it. ${detPart}`;
  } else if (caught.length && !opponent) {
    detPart = `${name} missed it${fa}, though ${who} alone crossed ${caught.length === 1 ? "its" : "their"} line.`;
  } else if (opponent) {
    detPart = det.false_alarms ? `${name} missed it${fa}.` : `${name} never crossed its line.`;
  } else {
    detPart = `Not one detector flagged it${fa}.`;
  }
  if (nLabels > 1) youPart = `${nLabels} labeled anomalies. ${youPart}`;
  return [head, `${youPart} ${detPart}`];
}

export type SeriesResult = {
  ranges: Range[]; det_ranges: Range[]; detectors: DetectorResult[];
  team_score: number[] | null; team_threshold: number | null;
  you: Evaluation; det: Evaluation; outcome: Outcome;
  you_result: ResultKey; det_result: ResultKey; you_text: string; det_text: string;
  verdict: string; verdict_sub: string;
};

export function scoreSeries(rawRanges: ArrayLike<ArrayLike<number>>, labels: Range[], detectors: Detector[], n: number): SeriesResult {
  const ranges = cleanRanges(rawRanges, n);
  const [each, side] = detectorFlags(detectors, labels, n);
  const you = evaluate(ranges, labels, n);
  const det = evaluate(side.flags, labels, n);
  const caught = each.filter((d) => d.caught).map((d) => d.name);
  // One detector in the pack means a single named opponent.
  const opponent = each.length === 1 ? each[0].name : null;
  const [head, sub] = verdict(you, det, labels.length, caught, each.length, DETECTOR_RULE, opponent);
  return {
    ranges, det_ranges: side.flags, detectors: each,
    team_score: side.score, team_threshold: side.threshold,
    you, det, outcome: outcome(you, det),
    you_result: resultKey(you, labels.length), det_result: resultKey(det, labels.length),
    you_text: resultText(you, labels.length), det_text: resultText(det, labels.length),
    verdict: head, verdict_sub: sub,
  };
}
