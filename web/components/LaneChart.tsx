"use client";

// The Workbench chart: the series on top (one lane per channel), then one
// lane per detector, all sharing the x axis. Each lane is a canvas with the
// line min-max decimated to one column per pixel, so a 900k-point series
// draws as fast as a 1k one. Drag to zoom, double-click to reset.
//
// Positions are point indices: point i owns [i - 0.5, i + 0.5].

import { useCallback, useEffect, useRef, useState } from "react";

export type Lane = {
  id: string;
  kind: "series" | "score" | "lucky";   // lucky: a one-liner computed in the browser
  title: string;
  lines?: string[];   // drawn stacked and smaller in place of the title (an averaged stack's detectors)
  sub?: string;
  pinned?: boolean;
  values: ArrayLike<number>;
};

const LABEL_W = 132;
const SERIES_H = 200;      // one channel; more channels share SERIES_BUDGET, down to SERIES_MIN_H each
const SERIES_BUDGET = 320;
const SERIES_MIN_H = 56;
const SCORE_H = 78;
const AXIS_H = 26;
const COLORS = { line: "#C9C3E6", score: "#22D3EE", lucky: "#FB923C", grid: "#1F1B45", sep: "#2C2754", label: "#FFE14D", text: "#A9A2D4" };

type View = [number, number];

function drawLine(ctx: CanvasRenderingContext2D, values: ArrayLike<number>, view: View, w: number, h: number, color: string, pad: number) {
  const n = values.length;
  const [v0, v1] = view;
  const i0 = Math.max(0, Math.floor(v0)), i1 = Math.min(n - 1, Math.ceil(v1));
  if (i1 < i0) return;
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i <= i1; i++) { const v = values[i]; if (v < lo) lo = v; if (v > hi) hi = v; }
  if (!isFinite(lo)) return;
  const span = hi - lo || 1;
  const xOf = (i: number) => ((i - v0) / (v1 - v0)) * w;
  const yOf = (v: number) => pad + (1 - (v - lo) / span) * (h - 2 * pad);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.4;
  ctx.lineJoin = "round";
  ctx.beginPath();
  const perPx = (i1 - i0) / w;
  if (perPx <= 1.5) {
    for (let i = i0; i <= i1; i++) {
      const x = xOf(i), y = yOf(values[i]);
      if (i === i0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
  } else {
    let first = true;
    for (let px = 0; px < w; px++) {
      const a = Math.max(i0, Math.floor(v0 + (px / w) * (v1 - v0)));
      const b = Math.min(i1, Math.floor(v0 + ((px + 1) / w) * (v1 - v0)));
      if (b < a) continue;
      let mn = Infinity, mx = -Infinity, iMn = a, iMx = a;
      for (let i = a; i <= b; i++) { const v = values[i]; if (v < mn) { mn = v; iMn = i; } if (v > mx) { mx = v; iMx = i; } }
      const p1 = iMn < iMx ? [mn, mx] : [mx, mn];
      if (first) { ctx.moveTo(px, yOf(p1[0])); first = false; } else ctx.lineTo(px, yOf(p1[0]));
      ctx.lineTo(px, yOf(p1[1]));
    }
  }
  ctx.stroke();
}

function fmtTick(v: number) {
  return (Math.round(v) + 0).toLocaleString("en-US");   // + 0 turns -0 into 0
}

export function LaneChart({ n, lanes, labels, highlight }: {
  n: number; lanes: Lane[]; labels: [number, number][]; highlight: number | null;
}) {
  const [view, setView] = useState<View>([-0.5, n - 0.5]);
  const [width, setWidth] = useState(0);
  const [drag, setDrag] = useState<[number, number] | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const canvases = useRef<Map<string, HTMLCanvasElement>>(new Map());

  useEffect(() => { setView([-0.5, n - 0.5]); }, [n]);

  // Measured on the whole chart, not on a lane: lanes come and go (a channel
  // unselected), and an observed lane that leaves would read width 0 for good.
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(0, el.clientWidth - LABEL_W));
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  }, []);

  const nSeries = lanes.filter((l) => l.kind === "series").length;
  const seriesH = Math.round(Math.max(SERIES_MIN_H, Math.min(SERIES_H, SERIES_BUDGET / Math.max(1, nSeries))));
  const laneH = (lane: Lane) => lane.kind === "series" ? seriesH : SCORE_H;
  const roomy = seriesH >= 120;   // tall series lanes keep the finer grid and padding

  const render = useCallback(() => {
    if (!width) return;
    const dpr = window.devicePixelRatio || 1;
    for (const lane of lanes) {
      const c = canvases.current.get(lane.id);
      if (!c) continue;
      const h = lane.kind === "series" ? seriesH : SCORE_H;
      c.width = Math.round(width * dpr); c.height = Math.round(h * dpr);
      c.style.width = `${width}px`; c.style.height = `${h}px`;
      const ctx = c.getContext("2d");
      if (!ctx) continue;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, h);
      ctx.strokeStyle = COLORS.grid; ctx.lineWidth = 1;
      const rows = lane.kind === "series" && roomy ? 4 : 2;
      for (let r = 1; r < rows; r++) { const y = (h * r) / rows; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
      drawLine(ctx, lane.values, view, width, h, lane.kind === "series" ? COLORS.line : lane.kind === "lucky" ? COLORS.lucky : COLORS.score, lane.kind === "series" && roomy ? 10 : 6);
    }
  }, [lanes, view, width, seriesH, roomy]);

  useEffect(() => { render(); }, [render]);

  const xOf = (i: number) => ((i - view[0]) / (view[1] - view[0])) * width;
  const idxOf = (px: number) => view[0] + (px / width) * (view[1] - view[0]);

  const onDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const r = e.currentTarget.getBoundingClientRect();
    setDrag([e.clientX - r.left, e.clientX - r.left]);
  };
  const onMove = (e: React.MouseEvent) => {
    if (!drag) return;
    const r = e.currentTarget.getBoundingClientRect();   // every lane's plot starts at the same x
    setDrag([drag[0], Math.max(0, Math.min(width, e.clientX - r.left))]);
  };
  const onUp = () => {
    if (!drag) return;
    const [a, b] = [Math.min(...drag), Math.max(...drag)];
    setDrag(null);
    if (b - a < 6) return;
    const v0 = idxOf(a), v1 = idxOf(b);
    if (v1 - v0 < 8) return;
    setView([v0, v1]);
  };
  const reset = () => setView([-0.5, n - 0.5]);

  const ticks: number[] = [];
  if (width) {
    const span = view[1] - view[0];
    const raw = span / Math.max(2, Math.floor(width / 140));
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 5, 10].map((x) => x * mag).find((x) => x >= raw) ?? raw;
    for (let t = Math.ceil(view[0] / step) * step; t <= view[1]; t += step) ticks.push(t);
  }

  const zoomed = view[1] - view[0] < n - 0.01;

  return (
    <div ref={rootRef} className="lanes" style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {lanes.map((lane, k) => {
        const h = laneH(lane);
        return (
          <div key={lane.id} className="lane" style={{ display: "flex", height: h, borderBottom: `1px solid ${COLORS.sep}` }}>
            <div className="lane-label" style={{ width: LABEL_W, flex: "none", paddingTop: lane.kind === "series" && roomy ? 14 : 10, paddingRight: 10, minWidth: 0 }}>
              {lane.lines ? (
                <div title={lane.title} style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.25, color: "var(--text)" }}>
                  {lane.lines.map((l, i) => <div key={i} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i ? `+ ${l}` : l}</div>)}
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {lane.pinned && (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFE14D" strokeWidth="2.4" strokeLinecap="round" aria-label="pinned"><path d="M12 17v5M8 3h8l-1 7 3 3H6l3-3z" /></svg>
                  )}
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{lane.title}</span>
                </div>
              )}
              {lane.sub && <div className="mono" style={{ fontSize: 11, color: lane.kind === "series" ? COLORS.label : lane.kind === "lucky" ? COLORS.lucky : "var(--det-soft)", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{lane.sub}</div>}
            </div>
            <div style={{ flex: "1 1 auto", minWidth: 0, position: "relative" }}
              onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp} onDoubleClick={reset}
              title="Drag to zoom, double-click to reset"
            >
              {width > 0 && labels.map(([a, b], i) => {
                const x0 = Math.max(0, xOf(a - 0.5)), x1 = Math.min(width, xOf(b + 0.5));
                if (x1 < 0 || x0 > width) return null;
                const w = Math.max(3, x1 - x0);
                const dim = highlight !== null && highlight !== i;
                const strong = lane.kind === "series";
                // The labeled anomaly: a yellow band with solid edges, strongest on the series lane.
                const edge = `1px solid rgba(255,225,77,${dim ? 0.25 : strong ? 0.9 : 0.55})`;
                return (
                  <div key={i} style={{
                    position: "absolute", top: 0, bottom: 0, left: x0, width: w, pointerEvents: "none", boxSizing: "border-box",
                    background: strong ? `rgba(255,225,77,${dim ? 0.08 : 0.3})` : `rgba(255,225,77,${dim ? 0.04 : 0.16})`,
                    borderLeft: edge, borderRight: edge,
                  }} />
                );
              })}
              <canvas ref={(el) => { if (el) canvases.current.set(lane.id, el); else canvases.current.delete(lane.id); }}
                style={{ display: "block", position: "relative" }} />
              {drag && k === 0 && (
                <div style={{ position: "absolute", top: 0, bottom: 0, left: Math.min(...drag), width: Math.abs(drag[1] - drag[0]), background: "rgba(244,241,255,0.10)", borderLeft: "1px solid #F4F1FF", borderRight: "1px solid #F4F1FF", pointerEvents: "none" }} />
              )}
            </div>
          </div>
        );
      })}
      <div style={{ display: "flex", height: AXIS_H, fontFamily: "var(--mono)", fontSize: 11, color: COLORS.text }}>
        <div style={{ width: LABEL_W, flex: "none", display: "flex", alignItems: "center" }}>
          {zoomed && <button type="button" className="btn-sm" style={{ height: 22, padding: "0 8px", fontSize: 11 }} onClick={reset}>Reset view</button>}
        </div>
        <div style={{ flex: "1 1 auto", position: "relative" }}>
          {ticks.map((t) => (
            <span key={t} style={{ position: "absolute", left: xOf(t), top: 6, transform: "translateX(-50%)" }}>{fmtTick(t)}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
