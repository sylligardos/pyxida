"use client";

// Landscape: one point per series, scored by the best detector on it or by
// the average of the top five. One box per dataset (or entity type), sorted
// hardest first. Click a box to scope the tables, click a table row to
// open the series in the Workbench.

import { useMemo } from "react";
import { useSessionState } from "@/lib/session";
import Link from "next/link";
import type { Landscape, State } from "@/lib/model";
import { href } from "@/lib/model";

type Unit = "best" | "top5";
type Metric = "aucpr" | "vus";
type Group = "dataset" | "type";

type Row = {
  file: string; dataset: string; type: string; n: number | null; anomalies: number | null;
  score: number; best: string;
};

const TABLE_ROWS = 10;
const LEFT = 60, RIGHT = 1176, TOP = 16, BOTTOM = 330, LABEL_Y = 346, HEIGHT = 420;

function scoreRows(data: Landscape, unit: Unit, metric: Metric): Row[] {
  const out: Row[] = [];
  for (const r of data.rows) {
    const vals = r[metric].map((v, i) => [v, i] as const).filter((x): x is readonly [number, number] => x[0] !== null);
    if (!vals.length) continue;
    vals.sort((a, b) => b[0] - a[0]);
    const score = unit === "best" ? vals[0][0] : vals.slice(0, 5).reduce((s, x) => s + x[0], 0) / Math.min(5, vals.length);
    out.push({ file: r.file, dataset: r.dataset, type: r.type, n: r.n, anomalies: r.anomalies, score, best: data.detectors[vals[0][1]] });
  }
  return out;
}

function quantile(sorted: number[], p: number) {
  if (!sorted.length) return 0;
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

// Deterministic jitter, so a point stays where it is across re-renders.
function jitter(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000 - 0.5;
}

export function LandscapeView({ data, state }: { data: Landscape; state: State }) {
  const scopeKey = `${state.benchmark}:${state.kind}`;
  const [unit, setUnit] = useSessionState<Unit>("landscape.unit", "best");
  const [metric, setMetric] = useSessionState<Metric>("landscape.metric", "vus");
  const [group, setGroup] = useSessionState<Group>("landscape.group", "dataset");
  const [datasets, setDatasets] = useSessionState<string[]>(`landscape.datasets:${scopeKey}`, []);
  const [scope, setScope] = useSessionState<{ group: Group; value: string } | null>(`landscape.scope:${scopeKey}`, null);

  const rows = useMemo(() => scoreRows(data, unit, metric), [data, unit, metric]);
  const allDatasets = useMemo(() => Array.from(new Set(rows.map((r) => r.dataset))).sort(), [rows]);
  const visible = datasets.length ? rows.filter((r) => datasets.includes(r.dataset)) : rows;

  const groups = useMemo(() => {
    const by = new Map<string, Row[]>();
    for (const r of visible) {
      const k = r[group];
      if (!by.has(k)) by.set(k, []);
      by.get(k)!.push(r);
    }
    return Array.from(by.entries())
      .map(([name, rs]) => {
        const sorted = rs.map((r) => r.score).sort((a, b) => a - b);
        return { name, rows: rs, sorted, med: quantile(sorted, 0.5), q1: quantile(sorted, 0.25), q3: quantile(sorted, 0.75) };
      })
      .sort((a, b) => a.med - b.med);
  }, [visible, group]);

  const scoped = scope ? visible.filter((r) => r[scope.group] === scope.value) : visible;
  const hardest = [...scoped].sort((a, b) => a.score - b.score).slice(0, TABLE_ROWS);

  const metricLabel = data.metrics[metric].label;
  const y = (v: number) => TOP + (1 - v) * (BOTTOM - TOP);
  const cw = (RIGHT - LEFT) / Math.max(1, groups.length);
  const width = RIGHT + 40;

  return (
    <>
      <section className="wrap" style={{ paddingBottom: 20 }}>
        <div className="panel ls-controls">
          <div className="ctl">
            <span className="lbl" id="ls-unit">Score each series by</span>
            <div className="seg tall" role="group" aria-labelledby="ls-unit">
              <button type="button" aria-pressed={unit === "best"} onClick={() => setUnit("best")}>Best detector</button>
              <button type="button" aria-pressed={unit === "top5"} onClick={() => setUnit("top5")}>Average of the top 5</button>
            </div>
          </div>
          <div className="ctl">
            <span className="lbl" id="ls-metric">Metric</span>
            <div className="seg tall" role="group" aria-labelledby="ls-metric">
              <button type="button" aria-pressed={metric === "aucpr"} onClick={() => setMetric("aucpr")}>{data.metrics.aucpr.label}</button>
              <button type="button" aria-pressed={metric === "vus"} onClick={() => setMetric("vus")}>{data.metrics.vus.label}</button>
            </div>
          </div>
          <div className="ctl ls-datasets">
            <label className="lbl" htmlFor="ls-ds">Datasets</label>
            <div className="select">
              <select id="ls-ds" value={datasets.length === 1 ? datasets[0] : ""} onChange={(e) => { setDatasets(e.target.value ? [e.target.value] : []); setScope(null); }}>
                <option value="">All {allDatasets.length}</option>
                {allDatasets.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><polyline points="2,4 6,8 10,4" /></svg>
            </div>
          </div>
        </div>
      </section>

      <section className="wrap" style={{ paddingBottom: 40, display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="tabs" role="tablist" aria-label="Group series by">
          <button type="button" role="tab" aria-selected={group === "dataset"} onClick={() => { setGroup("dataset"); setScope(null); }}>By dataset</button>
          <button type="button" role="tab" aria-selected={group === "type"} onClick={() => { setGroup("type"); setScope(null); }}>By entity type</button>
        </div>
        <figure className="surface ls-chart">
          <div className="head">
            <span className="key">
              <span><i style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--text-2)" }} aria-hidden="true" />a series</span>
              <span><i style={{ width: 14, height: 9, border: "1.5px solid var(--det)", background: "rgba(34,211,238,0.14)" }} aria-hidden="true" />spread of the {group === "dataset" ? "dataset" : "entity type"}</span>
            </span>
          </div>
          <div>
            <svg viewBox={`0 0 ${width} ${HEIGHT}`} width="100%" style={{ height: "auto" }} role="img"
              aria-label={`One box per ${group}, every series a point, sorted hardest first.`}>
              {[1, 0.75, 0.5, 0.25].map((v) => <line key={v} x1={LEFT} y1={y(v)} x2={width - 8} y2={y(v)} stroke="var(--grid)" />)}
              <line x1={LEFT} y1={y(0)} x2={width - 8} y2={y(0)} stroke="var(--border)" />
              <text transform={`rotate(-90 14 ${(TOP + BOTTOM) / 2})`} x={14} y={(TOP + BOTTOM) / 2} textAnchor="middle"
                fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">{metricLabel}</text>
              {[1, 0.5, 0].map((v) => (
                <text key={v} x={LEFT - 8} y={y(v) + 4} textAnchor="end" fontFamily="var(--mono)" fontSize="11" fill="var(--text-3)">{v === 0 ? "0" : v.toFixed(1)}</text>
              ))}
              {groups.map((g, i) => {
                const cx = LEFT + cw * (i + 0.5), bw = Math.min(30, cw - 16);
                const isScoped = scope?.group === group && scope.value === g.name;
                const mn = g.sorted[0], mx = g.sorted[g.sorted.length - 1];
                return (
                  <g key={g.name} className={`box${isScoped ? " scoped" : ""}`} onClick={() => setScope(isScoped ? null : { group, value: g.name })}>
                    <rect x={cx - cw / 2} y={TOP} width={cw} height={BOTTOM - TOP} fill="transparent" />
                    <line x1={cx} y1={y(g.q3)} x2={cx} y2={y(mx)} stroke="#22D3EE" strokeWidth="1.2" />
                    <line x1={cx} y1={y(g.q1)} x2={cx} y2={y(mn)} stroke="#22D3EE" strokeWidth="1.2" />
                    <rect className="boxfill" x={cx - bw / 2} y={y(g.q3)} width={bw} height={Math.max(1, y(g.q1) - y(g.q3))}
                      fill="rgba(34,211,238,0.14)" stroke="#22D3EE" strokeWidth="1.4" />
                    <line x1={cx - bw / 2} y1={y(g.med)} x2={cx + bw / 2} y2={y(g.med)} stroke="var(--text)" strokeWidth="2" />
                    {g.rows.map((r) => {
                      return (
                        <circle key={r.file} className="pt" cx={cx + jitter(r.file) * (bw - 6)} cy={y(r.score)} r={2.2}
                          fill="var(--text-3)">
                          <title>{`${r.file}\n${metricLabel} ${r.score.toFixed(3)}`}</title>
                        </circle>
                      );
                    })}
                    <text transform={`rotate(-40 ${cx + 8} ${LABEL_Y})`} x={cx + 8} y={LABEL_Y} textAnchor="end"
                      fontFamily="var(--mono)" fontSize="11" fontWeight={isScoped ? 700 : 400} fill={isScoped ? "var(--yellow)" : "var(--text-2)"}>{g.name}</text>
                  </g>
                );
              })}
            </svg>
          </div>
          <figcaption>
            Click on {group === "dataset" ? "a dataset" : "an entity type"} to scope the table below it.
          </figcaption>
        </figure>
      </section>

      <section className="wrap" style={{ paddingBottom: 72, display: "flex", flexDirection: "column", gap: 20 }}>
        {scope && (
          <div className="scope-row">
            <p className="soft">Scoped to <span className="mono" style={{ fontWeight: 700, color: "var(--yellow)" }}>{scope.value}</span> · {scoped.length} series</p>
            <button type="button" className="btn-sm" onClick={() => setScope(null)}>Clear scope</button>
          </div>
        )}
        <div className="tables">
          <Table title="Hardest series" note="Click on a time series to look at it in the workbench."
            mark={<span className="diamond diamond-human-hollow" aria-hidden="true" />} rows={hardest} color="var(--human)" state={state} metric={metric} />
        </div>
      </section>
    </>
  );
}

function Table({ title, note, mark, rows, color, state, metric }: {
  title: string; note: string; mark: React.ReactNode; rows: Row[]; color: string; state: State; metric: Metric;
}) {
  return (
    <div className="panel table">
      <div className="head">
        <h2>{mark}{title}</h2>
        <p>{note}</p>
      </div>
      <div className="trow th">
        <span>Series</span><span className="hide">Dataset</span><span className="hide">Type</span><span className="hide">Best detector</span>
        <span className="r hide">{metric === "vus" ? "VUS" : "AUC"}</span><span className="r">Anom.</span>
      </div>
      {rows.map((r) => (
        <Link key={r.file} className="trow" href={href("/workbench", state, { s: r.file })}>
          <span className="file">{r.file.replace(/\.csv$/, "")}</span>
          <span className="soft hide">{r.dataset}</span>
          <span className="soft hide">{r.type}</span>
          <span className="hide" style={{ color: "var(--det-soft)" }}>{r.best}</span>
          <span className="num hide" style={{ color }}>{r.score.toFixed(2)}</span>
          <span className="num soft">{r.anomalies ?? "–"}</span>
        </Link>
      ))}
    </div>
  );
}
