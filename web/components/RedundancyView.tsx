"use client";

// Redundancy: many detectors flag the same points. Top to bottom:
//   1. Heatmap   how much every pair of detectors agrees, lower triangle,
//                leaderboard order. Click a square to pick that pair.
//   2. Pairs     the closest pairs, and where they are closest: the datasets
//                (all datasets) or the series (one dataset) with a link
//                into the Workbench.
//   3. Stacking  the top k by rank, averaged, against the single best and
//                the best k-set found by trying every one: mean scores,
//                mean gain by how good the best single already is, and one
//                scatter per stack. Then the series where the top k falls
//                short by the most.
// Everything is computed here from the Redundancy file.

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSessionState } from "@/lib/session";
import type { Redundancy, State } from "@/lib/model";
import { href } from "@/lib/model";

const PAIRS = 8;             // closest pairs listed
const WHERE = 3;             // datasets named per pair
const EX_MIN_SERIES = 5;     // a dataset needs this many series to be named there
const LIST_ROWS = 8;         // series listed before "show all"
const BAR_FROM = 0.70;       // the mean bars start here
const BINS = [0, 0.2, 0.4, 0.6, 0.8, 1.0001];
const GAIN_MAX = 0.2;        // the gain chart's top

// Heatmap ramp on a fixed 0 to 1 scale: navy, teal, cyan, yellow, orange,
// pink, white. A new hue every step, so 0.6 and 0.8 read apart.
const RAMP: [number, [number, number, number]][] = [
  [0.00, [14, 26, 46]], [0.15, [21, 94, 117]], [0.30, [34, 211, 238]], [0.50, [253, 224, 71]],
  [0.70, [251, 146, 60]], [0.85, [255, 61, 154]], [1.00, [255, 240, 248]],
];
function ramp(t: number) {
  const i = Math.max(1, RAMP.findIndex(([p]) => p >= t));
  const [p0, c0] = RAMP[i - 1], [p1, c1] = RAMP[i];
  const f = (t - p0) / (p1 - p0);
  return `rgb(${c0.map((c, j) => Math.round(c + f * (c1[j] - c))).join(",")})`;
}
const RAMP_CSS = `linear-gradient(90deg, ${RAMP.map(([p, c]) => `rgb(${c.join(",")}) ${100 * p}%`).join(", ")})`;

// Scatter geometry: a square plot, both axes 0 to 1.
const SX0 = 44, SX1 = 332, SY0 = 304, SY1 = 16;
const sx = (v: number) => SX0 + (SX1 - SX0) * v;
const sy = (v: number) => SY0 - (SY0 - SY1) * Math.max(0, Math.min(1, v));

// Below this many detectors the matrix leaves no empty corner for the key,
// so the key goes under it.
const SMALL_HM = 20;

function mean(xs: number[]) { return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0; }
const fmt = (v: number) => v.toFixed(2);
const signed = (v: number) => `${v >= 0.005 ? "+" : v <= -0.005 ? "−" : ""}${Math.abs(v).toFixed(2)}`;
const Chip = ({ children }: { children: React.ReactNode }) => <span className="dchip det">{children}</span>;

export function RedundancyView({ data, state }: { data: Redundancy; state: State }) {
  const scopeKey = `${state.benchmark}:${state.kind}`;
  const [k, setK] = useSessionState<2 | 3>("redundancy.k", 2);
  const [scope, setScope] = useSessionState<string>(`redundancy.scope:${scopeKey}`, "global");
  const [picked, setPicked] = useState<[number, number] | null>(null);
  const [all, setAll] = useState(false);

  // Detectors in leaderboard order, for the heatmap axes.
  const order = useMemo(() => data.detectors.map((_, i) => i).sort((a, b) => (data.mean_vus[b] ?? -1) - (data.mean_vus[a] ?? -1)), [data]);
  const datasets = useMemo(() => Object.keys(data.agree.datasets).sort(), [data]);
  const matrix = scope === "global" ? data.agree.global : data.agree.datasets[scope];

  // The closest pairs in scope; a picked square joins the list if it is not there.
  const pairs = useMemo(() => {
    const all: { a: number; b: number; v: number }[] = [];
    matrix.forEach((row, a) => row.forEach((v, b) => { if (v !== null && a < b) all.push({ a, b, v }); }));
    all.sort((x, y) => y.v - x.v);
    const top = all.slice(0, PAIRS);
    if (picked) {
      const [a, b] = picked[0] < picked[1] ? picked : [picked[1], picked[0]];
      if (!top.some((p) => p.a === a && p.b === b)) { const v = matrix[a]?.[b]; if (v != null) top.unshift({ a, b, v }); }
    }
    return top;
  }, [matrix, picked]);

  // A series to open for a pair: in scope, where one of the two is the best detector, the highest-scoring one.
  const seriesFor = (a: string, b: string) => {
    const pool = (scope === "global" ? data.series : data.series.filter((s) => s.dataset === scope)).filter((s) => s.best1_det === a || s.best1_det === b);
    return pool.sort((x, y) => y.best1 - x.best1)[0]?.file;
  };
  // The datasets where a pair is closest, among those with enough series.
  const topDatasets = (a: number, b: number) => Object.entries(data.agree.datasets)
    .filter(([ds, m]) => (data.agree.n[ds] ?? 0) >= EX_MIN_SERIES && m[a]?.[b] != null)
    .map(([ds, m]) => ({ ds, v: m[a][b]! }))
    .sort((x, y) => y.v - x.v).slice(0, WHERE);
  // The series in the scoped dataset where a pair agrees most.
  const topSeries = (a: number, b: number) => {
    const ex = data.examples[scope];
    return (ex?.pairs[`${Math.min(a, b)}-${Math.max(a, b)}`] ?? []).slice(0, WHERE).map(([i, v]) => ({ file: ex.files[i], v }));
  };

  // Stacking the top k: only where the exhaustive search over pairs and
  // triplets was run (TSB-AD univariate).
  const stacking = useMemo(() => data.series.some((s) => s.k2 || s.k3), [data]);
  const key = `k${k}` as const;
  const setName = k === 2 ? "pair" : "triplet";
  const rows = useMemo(() => data.series.filter((s) => s[key] && s[key]!.top !== null), [data, key]);
  const m1 = mean(rows.map((s) => s.best1)), mTop = mean(rows.map((s) => s[key]!.top!)), mBest = mean(rows.map((s) => s[key]!.best));
  const bar = (v: number) => `${(100 * Math.max(0, Math.min(1, (v - BAR_FROM) / (1 - BAR_FROM)))).toFixed(1)}%`;
  const bins = useMemo(() => BINS.slice(0, -1).map((lo, i) => {
    const hi = BINS[i + 1], sub = rows.filter((s) => s.best1 >= lo && s.best1 < hi);
    return { lo, hi: Math.min(1, hi), n: sub.length, top: mean(sub.map((s) => s[key]!.top! - s.best1)), best: mean(sub.map((s) => s[key]!.best - s.best1)) };
  }), [rows, key]);
  const gh = (v: number) => Math.max(2, Math.round(110 * Math.max(0, v) / GAIN_MAX));
  const short = useMemo(() => rows.map((s) => ({ ...s, gap: s[key]!.best - s[key]!.top! })).sort((a, b) => b.gap - a.gap), [rows, key]);
  const shown = all ? short : short.slice(0, LIST_ROWS);

  const cell = (a: number, b: number) => {
    const v = a === b ? null : matrix[a]?.[b] ?? null;
    return { v, bg: a === b ? "var(--panel)" : v === null ? "var(--bg)" : ramp(Math.max(0, v)) };
  };
  const isPicked = (a: number, b: number) => picked !== null && ((picked[0] === a && picked[1] === b) || (picked[0] === b && picked[1] === a));

  const Scatter = ({ title, pick, color, fill }: { title: string; pick: (s: typeof rows[number]) => number; color: string; fill: string }) => (
    <figure className="surface rd-fig" style={{ flex: "1 1 300px", padding: "18px 18px 12px" }}>
      <span className="lbl" style={{ fontSize: 11, color }}>{title}</span>
      <svg viewBox="0 0 340 350" width="100%" style={{ height: "auto", display: "block" }} role="img"
        aria-label={`Every series as a point: the best single detector's VUS-PR against the ${title}'s. Above the diagonal the stack is better.`}>
        {[0.25, 0.5, 0.75, 1].map((v) => <line key={v} x1={SX0} y1={sy(v)} x2={SX1} y2={sy(v)} stroke="var(--grid)" />)}
        <line x1={SX0} y1={SY0} x2={SX1} y2={SY0} stroke="var(--border)" />
        <line x1={SX0} y1={SY0} x2={SX0} y2={SY1} stroke="var(--border)" />
        <line x1={SX0} y1={SY0} x2={SX1} y2={SY1} stroke="var(--text-3)" strokeDasharray="4 4" />
        {[0, 0.5, 1].map((v) => <text key={v} x={SX0 - 8} y={sy(v) + 4} textAnchor="end" fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">{v === 0 ? "0" : v === 1 ? "1" : "0.5"}</text>)}
        {[0, 0.5, 1].map((v) => <text key={v} x={sx(v)} y={SY0 + 18} textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"} fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">{v === 0 ? "0" : v === 1 ? "1" : "0.5"}</text>)}
        <text x={(SX0 + SX1) / 2} y={342} textAnchor="middle" fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">Best single detector, VUS-PR</text>
        <text transform={`rotate(-90 12 ${(SY0 + SY1) / 2})`} x={12} y={(SY0 + SY1) / 2} textAnchor="middle" fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">{title}, VUS-PR</text>
        {rows.map((s) => <circle key={s.file} cx={sx(s.best1)} cy={sy(pick(s))} r={2.4} fill={fill}><title>{`${s.file.replace(/\.csv$/, "")}\nbest single ${fmt(s.best1)} · ${title} ${fmt(pick(s))}`}</title></circle>)}
      </svg>
    </figure>
  );

  return (
    <>
      <section className="wrap" style={{ paddingBottom: 28 }}>
        <div className="panel ls-controls">
          <div className="ctl ls-datasets">
            <label className="lbl" htmlFor="rd-scope">Dataset</label>
            <div className="select">
              <select id="rd-scope" value={scope} onChange={(e) => { setScope(e.target.value); setPicked(null); }}>
                <option value="global">All {datasets.length} datasets</option>
                {datasets.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><polyline points="2,4 6,8 10,4" /></svg>
            </div>
          </div>
          {stacking && <div className="ctl">
            <span className="lbl" id="rd-k">Stack</span>
            <div className="seg tall" role="group" aria-labelledby="rd-k">
              <button type="button" aria-pressed={k === 2} onClick={() => { setK(2); setAll(false); }}>Top 2</button>
              <button type="button" aria-pressed={k === 3} onClick={() => { setK(3); setAll(false); }}>Top 3</button>
            </div>
          </div>}
        </div>
      </section>

      {/* 1. the heatmap */}
      <section className="wrap" style={{ paddingBottom: 40, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="rk-title">Do two detectors flag the same points? <span>Agreement of their rankings on a series, averaged over {scope === "global" ? `${data.series.length} series` : `the ${data.agree.n[scope] ?? 0} series of ${scope}`}. 0 is unrelated, 1 is identical.</span></p>
        <figure className="surface rd-fig" style={{ padding: "22px 24px 18px" }}>
          <div className="rk-scroll">
            <div className={data.detectors.length < SMALL_HM ? "rd-hm rd-hm-small" : "rd-hm"}>
              {order.map((a) => (
                <div key={a} className="rd-hm-row">
                  <span className="rd-hm-lbl rd-hm-rowlbl">{data.detectors[a]}</span>
                  {order.map((b, rb) => {
                    if (rb > order.indexOf(a)) return <div key={b} className="rd-hm-gap" />;
                    const c = cell(a, b);
                    if (a === b) return <div key={b} className="rd-hm-cell" style={{ background: c.bg }} title={data.detectors[a]} />;
                    return (
                      <button key={b} type="button" className="rd-hm-cell" aria-pressed={isPicked(a, b)} style={{ background: c.bg }}
                        onClick={() => setPicked(isPicked(a, b) ? null : [a, b])}
                        title={`${data.detectors[a]} and ${data.detectors[b]}: ${c.v === null ? "no score" : c.v.toFixed(2)}`} />
                    );
                  })}
                </div>
              ))}
              <div className="rd-hm-cols">
                {order.map((di) => <div key={di} className="rd-hm-col"><span className="rd-hm-lbl">{data.detectors[di]}</span></div>)}
              </div>
              <div className="rd-hm-key">
                <div className="mono" style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11, color: "var(--text-3)" }}>
                  <span aria-hidden="true" style={{ display: "block", width: 200, height: 10, borderRadius: 5, background: RAMP_CSS }} />
                  <span style={{ display: "flex", justifyContent: "space-between", width: 200 }}><span>0 unrelated</span><span>0.5</span><span>1 identical</span></span>
                </div>
                <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: "var(--text-2)" }}>Detectors in leaderboard order, best first. The bright squares are the pairs listed below. Click a square to add its pair.</p>
                <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--text-3)" }}>Agreement is the weighted Kendall tau of two detectors&apos; scores on a series: the points they rank on top count most.</p>
              </div>
            </div>
          </div>
        </figure>
      </section>

      {/* 2. the closest pairs, and where */}
      <section className="wrap" style={{ paddingBottom: 40, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="rk-title">The closest pairs, and where they are closest</p>
        <div className="panel" style={{ padding: "20px 10px 12px", display: "flex", flexDirection: "column", gap: 2 }}>
          <div className="rk-scroll">
            <div className="rd-list">
              <div className="rd-prow th"><span>Pair</span><span>Agreement</span><span style={{ textAlign: "right" }}>Value</span><span>{scope === "global" ? "Closest on" : "Closest series"}</span></div>
              {pairs.map((p) => {
                const a = data.detectors[p.a], b = data.detectors[p.b], s = seriesFor(a, b);
                return (
                  <div key={`${p.a}-${p.b}`} className="rd-prow" aria-current={isPicked(p.a, p.b) ? "true" : undefined}>
                    <Link className="rd-pair" href={href("/workbench", state, { pin: `${a},${b}`, top: "0", ...(s ? { s } : {}) })}>
                      <Chip>{a}</Chip><span style={{ color: "var(--text-3)", fontSize: 13 }}>and</span><Chip>{b}</Chip>
                    </Link>
                    <span className="rd-bar"><span style={{ width: `${(100 * Math.max(0, p.v)).toFixed(1)}%`, background: "var(--det)" }} /></span>
                    <span className="mono" style={{ textAlign: "right", fontSize: 14, color: "var(--det-soft)" }}>{p.v.toFixed(2)}</span>
                    <span className="rd-where">
                      {scope === "global"
                        ? topDatasets(p.a, p.b).map((d) => (
                          <button key={d.ds} type="button" className="rd-ex-ds" onClick={() => setScope(d.ds)}>{d.ds} <span className="mono">{d.v.toFixed(2)}</span></button>
                        ))
                        : topSeries(p.a, p.b).map((e) => (
                          <Link key={e.file} className="rd-ex-ds" href={href("/workbench", state, { s: e.file, pin: `${a},${b}`, top: "0" })}>{e.file.replace(/\.csv$/, "")} <span className="mono">{e.v.toFixed(2)}</span></Link>
                        ))}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          <p className="rk-xlabel" style={{ textAlign: "left", padding: "10px 12px 0" }}>
            {scope === "global"
              ? "Click a pair to open both on a series where one of them is the best. Click a dataset to see the series where the pair agrees most."
              : "Click a pair to open both on a series where one of them is the best, or a series to open both on it."}
          </p>
        </div>
      </section>

      {/* 3. stacking the top k */}
      {stacking && <section className="wrap" style={{ paddingBottom: 72, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="rk-title">So does stacking the top {k} help? <span>The {k} best by rank, averaged, against the single best and against the best {setName} found by trying every {setName}.</span></p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "stretch" }}>
          <div style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
            <figure className="surface rd-fig" style={{ padding: "22px 24px 16px" }}>
              <span className="lbl" style={{ fontSize: 11 }}>Mean VUS-PR over {rows.length} series</span>
              {[
                { label: "Best single", v: m1, fill: "var(--text-3)", color: "var(--text-2)", bold: false },
                { label: `Top ${k}, averaged`, v: mTop, fill: "var(--det)", color: "var(--text)", bold: true },
                { label: `Best ${setName}`, v: mBest, fill: "var(--yellow)", color: "var(--yellow)", bold: true },
              ].map((r) => (
                <div key={r.label} className="rd-ladder">
                  <span style={{ fontSize: 14, color: r.color, fontWeight: r.bold ? 600 : 400 }}>{r.label}</span>
                  <span className="rd-bar tall"><span style={{ width: bar(r.v), background: r.fill }} /></span>
                  <span className="mono" style={{ fontSize: 14, fontWeight: 700, textAlign: "right", color: r.color }}>{r.v.toFixed(3)}</span>
                </div>
              ))}
              <figcaption className="rk-xlabel" style={{ textAlign: "left", padding: "4px 0 0" }}>Bars start at {BAR_FROM.toFixed(2)}. The best {setName} is picked with the labels in hand: an upper bound.</figcaption>
            </figure>
            <figure className="surface rd-fig" style={{ flex: "1 1 auto", padding: "18px 20px 14px" }}>
              <div className="mono" style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "6px 16px", fontSize: 11, color: "var(--text-3)" }}>
                <span className="lbl" style={{ fontSize: 11 }}>Mean gain, by the best single&apos;s score</span>
                <span style={{ display: "inline-flex", gap: 12 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><i aria-hidden="true" style={{ width: 10, height: 9, background: "var(--det)", display: "inline-block" }} />top {k}</span>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><i aria-hidden="true" style={{ width: 10, height: 9, background: "var(--yellow)", display: "inline-block" }} />best {setName}</span>
                </span>
              </div>
              <div className="rd-gain">
                {bins.map((g) => (
                  <div key={g.lo} className="rd-gain-bin">
                    <span className="rd-gain-bar"><span className="mono" style={{ color: g.top >= 0 ? "var(--det-soft)" : "var(--human-soft)" }}>{signed(g.top)}</span><i style={{ height: gh(g.top), background: "var(--det)" }} /></span>
                    <span className="rd-gain-bar"><span className="mono" style={{ fontWeight: 700, color: "var(--yellow)" }}>{signed(g.best)}</span><i style={{ height: gh(g.best), background: "var(--yellow)" }} /></span>
                  </div>
                ))}
              </div>
              <div className="rd-gain ticks">
                {bins.map((g) => <span key={g.lo}><span style={{ color: "var(--text-2)" }}>{g.lo.toFixed(1)} to {g.hi.toFixed(1)}</span><span>{g.n} series</span></span>)}
              </div>
              <figcaption className="rk-xlabel" style={{ padding: 0 }}>Best single detector&apos;s VUS-PR on the series</figcaption>
            </figure>
          </div>
          <Scatter title={`Top ${k}, averaged`} pick={(s) => s[key]!.top!} color="var(--det-soft)" fill="rgba(34,211,238,0.55)" />
          <Scatter title={`Best ${setName}`} pick={(s) => s[key]!.best} color="var(--yellow)" fill="rgba(255,225,77,0.6)" />
        </div>

        <p className="rk-title" style={{ marginTop: 14 }}>Where the top {k} falls short <span>The series where the best {setName} beats it by the most.</span></p>
        <div className="panel" style={{ padding: "20px 10px 12px", display: "flex", flexDirection: "column", gap: 2 }}>
          <div className="rk-scroll">
            <div className="rd-list">
              <div className="rd-brow th">
                <span>Series</span><span>Dataset</span><span>Top {k}</span><span style={{ textAlign: "right" }}>Score</span><span>Best {setName}</span><span style={{ textAlign: "right" }}>Score</span><span style={{ textAlign: "right" }}>Gap</span>
              </div>
              {shown.map((s) => {
                const pins = Array.from(new Set([...s[key]!.top_dets, ...s[key]!.best_dets])).join(",");
                const avg = Array.from(new Set([s[key]!.top_dets.join(","), s[key]!.best_dets.join(",")])).join("|");
                return (
                  <Link key={s.file} className="rd-brow" href={href("/workbench", state, { s: s.file, pin: pins, top: "0", avg })}>
                    <span className="mono" style={{ fontSize: 12, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.file.replace(/\.csv$/, "")}</span>
                    <span style={{ fontSize: 13, fontWeight: 500 }}>{s.dataset}</span>
                    <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s[key]!.top_dets.join(" + ")}</span>
                    <span className="mono" style={{ fontSize: 13, textAlign: "right", color: "var(--text-3)" }}>{fmt(s[key]!.top!)}</span>
                    <span className="mono" style={{ fontSize: 12, color: "var(--det-soft)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s[key]!.best_dets.join(" + ")}</span>
                    <span className="mono" style={{ fontSize: 13, textAlign: "right", color: "var(--det-soft)" }}>{fmt(s[key]!.best)}</span>
                    <span className="mono" style={{ fontSize: 13, fontWeight: 700, textAlign: "right", color: "var(--yellow)" }}>+{fmt(s.gap)}</span>
                  </Link>
                );
              })}
            </div>
          </div>
          {short.length > LIST_ROWS && (
            <button type="button" className="rk-more" onClick={() => setAll((a) => !a)}>{all ? `Show the first ${LIST_ROWS}` : `Show all ${short.length} series`}</button>
          )}
        </div>
      </section>}
    </>
  );
}
