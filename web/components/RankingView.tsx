"use client";

// Rankings: which series does a single detector solve, and which does
// nobody solve. A detector "solves" a series when its score is within GAP
// of the best score on it; nobody does when the best score is under FLOOR.
//   1. Histogram  series by how many detectors solve them, plus "nobody".
//                 Click a bar to look at that group.
//   2. Detectors  a boxplot of every detector's scores (best median first),
//                 and under it how many series of the group each one solves.
//   3. The series of the group, best and runner-up, into the Workbench.

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSessionState } from "@/lib/session";
import type { Landscape, State } from "@/lib/model";
import { href } from "@/lib/model";

type Metric = "aucpr" | "vus";

const GAPS = [0.05, 0.1, 0.2, 0.3];       // solved: within this of the best score
const FLOORS = [0.1, 0.2, 0.3, 0.5];      // nobody: best score under this
const LIST_ROWS = 8;
const POINTS = 40;                        // series drawn per detector in the boxplot
const EPS = 1e-9;

// Boxplot geometry, as on the Landscape page; a band for the counts below.
const LEFT = 60, RIGHT = 1176, TOP = 16, BOTTOM = 330, LABEL_Y = 346, SPLIT = 446, CNT_TOP = 482, CNT_BOTTOM = 542, HEIGHT = 552;

type Series = {
  file: string; dataset: string;
  best: string; bs: number; second: string | null; ss: number; gap: number;
  k: number; key: string; solvers: number[];
};

function quantile(sorted: number[], p: number) {
  if (!sorted.length) return 0;
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

function jitter(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000 - 0.5;
}

const fmt = (v: number) => v.toFixed(2);

// Best, runner-up and solvers of every series. A missing score counts as zero.
function classify(rows: Landscape["rows"], detectors: string[], metric: Metric, gap: number, floor: number): Series[] {
  const out: Series[] = [];
  for (const r of rows) {
    if (!r[metric].some((v) => v !== null)) continue;
    const raw = r[metric].map((v) => v ?? 0);
    let b1 = -1, b2 = -1;
    raw.forEach((v, i) => { if (b1 < 0 || v > raw[b1]) { b2 = b1; b1 = i; } else if (b2 < 0 || v > raw[b2]) b2 = i; });
    const bs = raw[b1], ss = b2 >= 0 ? raw[b2] : 0;
    const solvers: number[] = [];
    raw.forEach((v, i) => { if (v >= bs - gap - EPS) solvers.push(i); });
    const k = solvers.length;
    out.push({ file: r.file, dataset: r.dataset, best: detectors[b1], bs, second: b2 >= 0 ? detectors[b2] : null, ss, gap: bs - ss, k, key: bs < floor ? "nobody" : String(k), solvers });
  }
  return out;
}

export function RankingView({ data, state }: { data: Landscape; state: State }) {
  const scopeKey = `${state.benchmark}:${state.kind}`;
  const [metric, setMetric] = useSessionState<Metric>("rankings.metric", "vus");
  const [dataset, setDataset] = useSessionState(`rankings.dataset:${scopeKey}`, "");
  const [gap, setGap] = useSessionState("rankings.gap", 0.2);
  const [floor, setFloor] = useSessionState("rankings.floor", 0.2);
  const [group, setGroup] = useSessionState(`rankings.group:${scopeKey}`, "1");
  const [all, setAll] = useState(false);

  const detectors = data.detectors, nd = detectors.length;
  const datasets = useMemo(() => Array.from(new Set(data.rows.map((r) => r.dataset))).sort(), [data]);
  const rows = useMemo(() => (dataset ? data.rows.filter((r) => r.dataset === dataset) : data.rows), [data, dataset]);
  const series = useMemo(() => classify(rows, detectors, metric, gap, floor), [rows, detectors, metric, gap, floor]);

  const groups = useMemo(() => {
    const m = new Map<string, Series[]>();
    for (const s of series) { const l = m.get(s.key); if (l) l.push(s); else m.set(s.key, [s]); }
    return m;
  }, [series]);
  const selected = groups.get(group) ?? [];
  const nmax = Math.max(1, ...Array.from(groups.values(), (l) => l.length));

  // Every detector's scores, best median first; up to POINTS real series as points.
  const boxes = useMemo(() => detectors.map((name, d) => {
    const pts = rows.map((r) => ({ file: r.file, v: r[metric][d] })).filter((x): x is { file: string; v: number } => x.v !== null).sort((a, b) => a.v - b.v);
    const vals = pts.map((x) => x.v);
    const step = Math.max(1, pts.length / POINTS);
    const sample: { file: string; v: number }[] = [];
    for (let i = 0; i < pts.length; i += step) sample.push(pts[Math.floor(i)]);
    return { name, d, n: vals.length, med: quantile(vals, 0.5), q1: quantile(vals, 0.25), q3: quantile(vals, 0.75), mn: vals[0] ?? 0, mx: vals[vals.length - 1] ?? 0, sample };
  }).filter((b) => b.n).sort((a, b) => b.med - a.med), [rows, detectors, metric]);

  // How many series of the group each detector solves.
  const counts = useMemo(() => {
    const c = new Array<number>(nd).fill(0);
    if (group !== "nobody") for (const s of selected) for (const j of s.solvers) c[j]++;
    return c;
  }, [selected, group, nd]);
  const cmax = Math.max(1, ...counts);

  const listed = useMemo(() => selected.slice().sort((a, b) => (group === "1" ? b.gap - a.gap : b.bs - a.bs)), [selected, group]);
  const shown = all ? listed : listed.slice(0, LIST_ROWS);

  const metricLabel = data.metrics[metric].label;
  const n = selected.length;
  const who = group === "nobody" ? `the ${n} series nobody solves` : `the ${n} series solved by ${group === "1" ? "exactly one detector" : `${group} detectors`}`;
  const listTitle = group === "nobody"
    ? `${n} series nobody solves · best score under ${fmt(floor)}`
    : `${n} series solved by ${group === "1" ? "one detector only · biggest lead first" : `${group} detectors · best score first`}`;

  const cw = (RIGHT - LEFT) / Math.max(1, boxes.length), bw = Math.min(30, cw - 16);
  const y = (v: number) => BOTTOM - v * (BOTTOM - TOP);
  const pick = (key: string) => { setGroup(key); setAll(false); };

  return (
    <>
      <section className="wrap" style={{ paddingBottom: 28 }}>
        <div className="panel ls-controls">
          <div className="ctl">
            <span className="lbl" id="rk-metric">Metric</span>
            <div className="seg tall" role="group" aria-labelledby="rk-metric">
              <button type="button" aria-pressed={metric === "aucpr"} onClick={() => setMetric("aucpr")}>{data.metrics.aucpr.label}</button>
              <button type="button" aria-pressed={metric === "vus"} onClick={() => setMetric("vus")}>{data.metrics.vus.label}</button>
            </div>
          </div>
          <div className="ctl ls-datasets">
            <label className="lbl" htmlFor="rk-ds">Dataset</label>
            <div className="select">
              <select id="rk-ds" value={dataset} onChange={(e) => { setDataset(e.target.value); setAll(false); }}>
                <option value="">All {datasets.length} datasets</option>
                {datasets.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><polyline points="2,4 6,8 10,4" /></svg>
            </div>
          </div>
          <div className="ctl">
            <span className="lbl" id="rk-gap">Solved: within … of the best</span>
            <div className="seg tall mono" role="group" aria-labelledby="rk-gap" style={{ fontSize: 13 }}>
              {GAPS.map((g) => <button key={g} type="button" aria-pressed={g === gap} onClick={() => { setGap(g); setAll(false); }}>{fmt(g)}</button>)}
            </div>
          </div>
          <div className="ctl">
            <span className="lbl" id="rk-floor">Nobody: best score under …</span>
            <div className="seg tall mono" role="group" aria-labelledby="rk-floor" style={{ fontSize: 13 }}>
              {FLOORS.map((f) => <button key={f} type="button" aria-pressed={f === floor} onClick={() => { setFloor(f); setAll(false); }}>{fmt(f)}</button>)}
            </div>
          </div>
        </div>
      </section>

      {/* 1. series by how many detectors solve them */}
      <section className="wrap" style={{ paddingBottom: 40, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="rk-title">How many detectors solve each series? <span>A detector solves a series when it is within {fmt(gap)} of the best {metricLabel} on it. Nobody does when the best score is under {fmt(floor)}.</span></p>
        <figure className="surface rk-fig">
          <div className="rk-scroll">
            <div className="rk-hist bars" style={{ gridTemplateColumns: `repeat(${nd}, minmax(0, 1fr)) 24px minmax(0, 1.6fr)` }}>
              {Array.from({ length: nd }, (_, i) => String(i + 1)).map((key) => {
                const c = groups.get(key)?.length ?? 0;
                return (
                  <button key={key} type="button" className="rk-hbar" aria-pressed={group === key} onClick={() => pick(key)}
                    aria-label={`${c} series solved by ${key} ${key === "1" ? "detector" : "detectors"}`}>
                    <span className="n">{c || ""}</span>
                    <i aria-hidden="true" style={{ height: Math.round(180 * c / nmax) }} />
                  </button>
                );
              })}
              <span className="rk-divider" aria-hidden="true" />
              <button type="button" className="rk-hbar nobody" aria-pressed={group === "nobody"} onClick={() => pick("nobody")}
                aria-label={`${groups.get("nobody")?.length ?? 0} series nobody solves`}>
                <span className="n">{groups.get("nobody")?.length || ""}</span>
                <i aria-hidden="true" style={{ height: Math.round(180 * (groups.get("nobody")?.length ?? 0) / nmax) }} />
              </button>
            </div>
            <div className="rk-hist ticks" style={{ gridTemplateColumns: `repeat(${nd}, minmax(0, 1fr)) 24px minmax(0, 1.6fr)` }}>
              {Array.from({ length: nd }, (_, i) => <span key={i} className={group === String(i + 1) ? "on" : undefined}>{i + 1}</span>)}
              <span />
              <span className={group === "nobody" ? "on" : undefined}>nobody</span>
            </div>
            <div className="rk-xlabel">Detectors that solve the series · click a bar to look at that group</div>
          </div>
        </figure>
      </section>

      {/* 2. the detectors: boxplot, and how many series of the group each solves */}
      <section className="wrap" style={{ paddingBottom: 40, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="rk-title">Who solves {who}?</p>
        <figure className="surface rk-fig rk-chart">
          <div className="rk-scroll">
            <svg viewBox={`0 0 ${RIGHT + 24} ${HEIGHT}`} width="100%" style={{ height: "auto" }} role="img"
              aria-label="One box per detector, best median first; under it, how many series of the selected group each detector solves.">
              {[1, 0.75, 0.5, 0.25].map((v) => <line key={v} x1={LEFT} y1={y(v)} x2={RIGHT + 16} y2={y(v)} stroke="var(--grid)" />)}
              <line x1={LEFT} y1={y(0)} x2={RIGHT + 16} y2={y(0)} stroke="var(--border)" />
              <text transform={`rotate(-90 14 ${(TOP + BOTTOM) / 2})`} x={14} y={(TOP + BOTTOM) / 2} textAnchor="middle" fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">{metricLabel}</text>
              {[1, 0.5, 0].map((v) => <text key={v} x={LEFT - 8} y={y(v) + 4} textAnchor="end" fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">{v === 0 ? "0" : v.toFixed(1)}</text>)}
              <line x1={LEFT} y1={SPLIT} x2={RIGHT + 16} y2={SPLIT} stroke="var(--border)" />
              <text x={RIGHT + 16} y={SPLIT + 15} textAnchor="end" fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">
                {group === "nobody" ? `No detector reaches ${fmt(floor)} on these series.` : "Series of this group each detector solves"}
              </text>
              {boxes.map((b, i) => {
                const cx = LEFT + cw * (i + 0.5), cnt = counts[b.d], top = i < 5;
                const ch = cnt ? Math.max(3, Math.round((CNT_BOTTOM - CNT_TOP) * cnt / cmax)) : 0;
                return (
                  <a key={b.name} href={href("/workbench", state, { pin: b.name, m: metric })} className="box">
                    <title>{`${b.name}: median ${b.med.toFixed(3)}, ${b.n} series${cnt ? `, solves ${cnt} of this group` : ""}`}</title>
                    <rect x={cx - cw / 2} y={TOP} width={cw} height={HEIGHT - TOP} fill="transparent" />
                    <line x1={cx} y1={y(b.q3)} x2={cx} y2={y(b.mx)} stroke="#22D3EE" strokeWidth="1.2" />
                    <line x1={cx} y1={y(b.q1)} x2={cx} y2={y(b.mn)} stroke="#22D3EE" strokeWidth="1.2" />
                    <rect className="boxfill" x={cx - bw / 2} y={y(b.q3)} width={bw} height={Math.max(1, y(b.q1) - y(b.q3))} fill="rgba(34,211,238,0.14)" stroke="#22D3EE" strokeWidth="1.4" />
                    <line x1={cx - bw / 2} y1={y(b.med)} x2={cx + bw / 2} y2={y(b.med)} stroke="var(--text)" strokeWidth="2" />
                    {b.sample.map((p) => <circle key={p.file} cx={cx + jitter(p.file) * (bw - 6)} cy={y(p.v)} r={2.2} fill="var(--text-3)" />)}
                    <text transform={`rotate(-40 ${cx + 8} ${LABEL_Y})`} x={cx + 8} y={LABEL_Y} textAnchor="end" fontFamily="var(--mono)" fontSize="11" fontWeight={top ? 700 : 400} fill={top ? "var(--text)" : "var(--text-2)"}>{b.name}</text>
                    {cnt > 0 && (
                      <>
                        <rect x={cx - bw * 0.3} y={CNT_BOTTOM - ch} width={bw * 0.6} height={ch} fill="var(--yellow)" />
                        <text x={cx} y={CNT_BOTTOM - ch - 5} textAnchor="middle" fontFamily="var(--mono)" fontSize="11" fontWeight={700} fill="var(--yellow)">{cnt}</text>
                      </>
                    )}
                  </a>
                );
              })}
            </svg>
          </div>
          <figcaption className="rk-xlabel">Detectors, best median first · click a detector to open a series with it pinned in the Workbench</figcaption>
        </figure>
      </section>

      {/* 3. the series of the group */}
      <section className="wrap" style={{ paddingBottom: 72, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="rk-title">{listTitle}</p>
        <div className="panel" style={{ padding: "20px 10px 12px", display: "flex", flexDirection: "column", gap: 2 }}>
          <div className="rk-scroll">
            <div className="rk-list">
              <div className="rk-srow th">
                <span>Series</span><span>Dataset</span><span>Best</span><span style={{ textAlign: "right" }}>Score</span><span>Runner-up</span><span style={{ textAlign: "right" }}>Score</span><span style={{ textAlign: "right" }}>Gap</span>
              </div>
              {shown.map((s) => (
                <Link key={s.file} className="rk-srow" href={href("/workbench", state, { s: s.file, pin: s.second ? `${s.best},${s.second}` : s.best, top: "0", m: metric })}>
                  <span className="mono" style={{ fontSize: 12, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.file.replace(/\.csv$/, "")}</span>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{s.dataset}</span>
                  <span><span className="dchip det">{s.best}</span></span>
                  <span className="mono" style={{ fontSize: 13, textAlign: "right", color: "var(--det-soft)" }}>{fmt(s.bs)}</span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{s.second ?? "–"}</span>
                  <span className="mono" style={{ fontSize: 13, textAlign: "right", color: "var(--text-3)" }}>{fmt(s.ss)}</span>
                  <span className="mono" style={{ fontSize: 13, fontWeight: 700, textAlign: "right", color: s.gap >= gap - EPS ? "var(--yellow)" : "var(--text-3)" }}>{s.gap >= 0.005 ? "+" : ""}{fmt(s.gap)}</span>
                </Link>
              ))}
            </div>
          </div>
          {n > LIST_ROWS
            ? <button type="button" className="rk-more" onClick={() => setAll((a) => !a)}>{all ? `Show the first ${LIST_ROWS}` : `Show all ${n} series`}</button>
            : <p className="rk-xlabel" style={{ textAlign: "left", padding: "10px 12px 0" }}>{n ? "That is all of them." : "No series in this group at these thresholds."}</p>}
        </div>
      </section>
    </>
  );
}
