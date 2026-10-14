// A series as an SVG line with its labeled anomalies as yellow dashed bands,
// or, with mark="line", drawn in red on the line itself.
// Server-rendered: the values are min-max decimated to the drawing width,
// so a long series costs the same as a short one.

const W = 640, H = 240, TOP = 24, PLOT_H = 190;

export function decimate(values: number[], columns: number): [number, number][] {
  const n = values.length;
  if (n <= columns) return values.map((v, i) => [i, v]);
  const out: [number, number][] = [];
  for (let c = 0; c < columns; c++) {
    const a = Math.floor((c * n) / columns), b = Math.max(a + 1, Math.floor(((c + 1) * n) / columns));
    let lo = Infinity, hi = -Infinity, iLo = a, iHi = a;
    for (let i = a; i < b; i++) {
      const v = values[i];
      if (v < lo) { lo = v; iLo = i; }
      if (v > hi) { hi = v; iHi = i; }
    }
    if (iLo <= iHi) out.push([iLo, lo], [iHi, hi]); else out.push([iHi, hi], [iLo, lo]);
  }
  return out;
}

export function SeriesPlot({ values, labels, title, mark = "bands" }: { values: number[]; labels: [number, number][]; title: string; mark?: "bands" | "line" }) {
  const n = values.length;
  let min = Infinity, max = -Infinity;
  for (const v of values) { if (v < min) min = v; if (v > max) max = v; }
  const span = max - min || 1;
  const x = (i: number) => (i / Math.max(1, n - 1)) * W;
  const y = (v: number) => TOP + (1 - (v - min) / span) * PLOT_H;
  const dec = decimate(values, W);
  const pts = dec.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  // The decimated points inside each anomaly, with one neighbour on each
  // side so the red joins the grey; a short anomaly becomes a red dot.
  const red = mark === "line" ? labels.map(([a, b]) => {
    let lo = dec.findIndex(([i]) => i >= a);
    if (lo < 0) lo = dec.length - 1;
    let hi = lo;
    while (hi + 1 < dec.length && dec[hi + 1][0] <= b) hi++;
    const seg = dec.slice(Math.max(0, lo - 1), Math.min(dec.length, hi + 2));
    const mid = values[Math.min(values.length - 1, Math.floor((a + b) / 2))];
    return { seg, cx: x((a + b) / 2), cy: y(mid) };
  }) : [];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", height: "auto" }} role="img" aria-label={title}>
      {[20, 70, 120, 170, 220].map((gy) => (
        <line key={gy} x1="0" y1={gy} x2={W} y2={gy} stroke="#1F1B45" strokeWidth="1" />
      ))}
      {mark === "bands" && labels.map(([a, b], k) => {
        const x0 = x(a), w = Math.max(3, x(b + 1) - x0);
        return (
          <rect key={k} x={x0.toFixed(1)} y="8" width={w.toFixed(1)} height="224"
            fill="rgba(255,225,77,0.16)" stroke="#FFE14D" strokeWidth="1.5" strokeDasharray="4 3" rx="2" />
        );
      })}
      <polyline points={pts} fill="none" stroke="#C9C3E6" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      {red.map(({ seg, cx, cy }, k) => seg.length >= 3
        ? <polyline key={k} points={seg.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} fill="none" stroke="#F43F5E" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        : <circle key={k} cx={cx.toFixed(1)} cy={cy.toFixed(1)} r="3" fill="#F43F5E" />)}
    </svg>
  );
}
