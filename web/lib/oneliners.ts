// Keogh's one-liners, as continuous scores. Wu & Keogh (TKDE 2023, "Current
// time series anomaly detection benchmarks are flawed") argue that most
// benchmark anomalies yield to one line of MATLAB. Each one-liner there is a
// score compared to a hand-picked threshold; here the threshold is dropped,
// the score is min-max scaled to 0..1, and AUC-PR does the thresholding.
// k is the window of the windowed ones (centred, clipped at the edges).

export type OneLiner = { id: string; title: string; windowed: boolean; run: (x: ArrayLike<number>, k: number) => Float32Array };

const EPS = 1e-9;

function diff(x: ArrayLike<number>): Float64Array {
  const n = x.length, d = new Float64Array(n);
  for (let i = 1; i < n; i++) d[i] = x[i] - x[i - 1];
  return d;
}

function absOf(v: Float64Array): Float64Array {
  const out = new Float64Array(v.length);
  for (let i = 0; i < v.length; i++) out[i] = Math.abs(v[i]);
  return out;
}

// Window bounds of point i: [i - floor(k/2), i - floor(k/2) + k - 1], clipped.
function bounds(i: number, k: number, n: number): [number, number] {
  const a = Math.max(0, i - Math.floor(k / 2));
  return [a, Math.min(n - 1, i - Math.floor(k / 2) + k - 1)];
}

// Rolling mean and std from prefix sums, O(n).
function rollingMeanStd(x: ArrayLike<number>, k: number): [Float64Array, Float64Array] {
  const n = x.length, s1 = new Float64Array(n + 1), s2 = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) { s1[i + 1] = s1[i] + x[i]; s2[i + 1] = s2[i] + x[i] * x[i]; }
  const mean = new Float64Array(n), std = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const [a, b] = bounds(i, k, n), m = b - a + 1;
    const mu = (s1[b + 1] - s1[a]) / m;
    const v = Math.max(0, (s2[b + 1] - s2[a]) / m - mu * mu);
    mean[i] = mu; std[i] = Math.sqrt(v);
  }
  return [mean, std];
}

// Rolling min with a monotonic deque, O(n).
function rollingMin(x: ArrayLike<number>, k: number): Float64Array {
  const n = x.length, out = new Float64Array(n), dq: number[] = [];
  let head = 0, next = 0;    // dq[head..] holds indices with increasing values; next = first index not yet pushed
  for (let i = 0; i < n; i++) {
    const [a, b] = bounds(i, k, n);
    while (next <= b) {
      while (dq.length > head && x[dq[dq.length - 1]] >= x[next]) dq.pop();
      dq.push(next++);
    }
    while (dq[head] < a) head++;
    out[i] = x[dq[head]];
  }
  return out;
}

function median(v: Float64Array): number {
  const s = Float64Array.from(v).sort();
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export function minMax(v: Float64Array): Float32Array {
  let lo = Infinity, hi = -Infinity;
  for (const a of v) { if (a < lo) lo = a; if (a > hi) hi = a; }
  const out = new Float32Array(v.length);
  if (!(hi > lo)) return out;
  for (let i = 0; i < v.length; i++) out[i] = (v[i] - lo) / (hi - lo);
  return out;
}

export const ONE_LINERS: OneLiner[] = [
  { id: "absdiff", title: "abs(diff(x))", windowed: false, run: (x) => minMax(absOf(diff(x))) },
  { id: "absdiff-z", title: "z_k(abs(diff(x)))", windowed: true, run: (x, k) => {
    const d = absOf(diff(x)), [mu, sd] = rollingMeanStd(d, k), out = new Float64Array(d.length);
    for (let i = 0; i < d.length; i++) out[i] = (d[i] - mu[i]) / (sd[i] + EPS);
    return minMax(out);
  } },
  { id: "movstd", title: "movstd(x, k)", windowed: true, run: (x, k) => minMax(rollingMeanStd(x, k)[1]) },
  { id: "raw", title: "x", windowed: false, run: (x) => minMax(Float64Array.from(x)) },
  { id: "abs-z", title: "abs(z(x))", windowed: false, run: (x) => {
    const n = x.length; let s = 0; for (let i = 0; i < n; i++) s += x[i];
    const mu = s / n, out = new Float64Array(n);
    for (let i = 0; i < n; i++) out[i] = Math.abs(x[i] - mu);
    return minMax(out);
  } },
  { id: "abs-local-z", title: "abs(z_k(x))", windowed: true, run: (x, k) => {
    const [mu, sd] = rollingMeanStd(x, k), out = new Float64Array(x.length);
    for (let i = 0; i < x.length; i++) out[i] = Math.abs(x[i] - mu[i]) / (sd[i] + EPS);
    return minMax(out);
  } },
  { id: "movmin", title: "movmin(x, k)", windowed: true, run: (x, k) => {
    const m = rollingMin(x, k), med = median(m), out = new Float64Array(m.length);
    for (let i = 0; i < m.length; i++) out[i] = Math.abs(m[i] - med);
    return minMax(out);
  } },
  { id: "flat", title: "-abs(diff(diff(x)))", windowed: false, run: (x) => {
    const d2 = diff(diff(x)), out = new Float64Array(d2.length);
    for (let i = 0; i < d2.length; i++) out[i] = -Math.abs(d2[i]);
    return minMax(out);
  } },
];

// Average precision, as sklearn.metrics.average_precision_score: the sum
// over score thresholds (ties grouped) of precision times the gain in recall.
// Labels are inclusive [start, end] ranges. NaN when nothing is labeled.
export function averagePrecision(score: ArrayLike<number>, labels: [number, number][]): number {
  const n = score.length, pos = new Uint8Array(n);
  let P = 0;
  for (const [a, b] of labels) for (let i = Math.max(0, a); i <= Math.min(n - 1, b); i++) if (!pos[i]) { pos[i] = 1; P++; }
  if (!P) return NaN;
  const order = Array.from({ length: n }, (_, i) => i).sort((i, j) => score[j] - score[i]);
  let tp = 0, seen = 0, ap = 0, prevRecall = 0;
  for (let s = 0; s < n;) {
    let e = s;
    while (e < n && score[order[e]] === score[order[s]]) { tp += pos[order[e]]; seen++; e++; }
    const recall = tp / P;
    ap += (recall - prevRecall) * (tp / seen);
    prevRecall = recall;
    s = e;
  }
  return ap;
}
