"use client";

// Graph: every series a node, the edge between two series the covariance of
// their detector-score profiles (scripts/export_graph.py). One graph per
// scope and metric, drawn from precomputed positions; its Louvain
// communities are the "neighbourhoods". The right column shows either the
// neighbourhoods, or the clicked series with its neighbours stacked below.
// The highlight rules follow archive/references/graph-design/graph-page-mock.html,
// without its series search.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { Graph, GraphData, Landscape, SeriesDoc, SeriesMeta, State, Summary } from "@/lib/model";
import { DATA_URL, href, stem } from "@/lib/model";
import { decimate } from "./SeriesPlot";
import { useSessionState } from "@/lib/session";

type Metric = "aucpr" | "vus";
type Colour = "dataset" | "type" | "hood" | "n" | "anomalies" | "alen";

const W = 1000, H = 640, PAD = 28;
const PAGE = 8;
const PALETTE = ["#22D3EE", "#FF3D9A", "var(--yellow)", "#A78BFA", "#34D399", "#FB923C", "#60A5FA", "#F472B6",
  "#A3E635", "#F87171", "#2DD4BF", "#C084FC", "#FBBF24", "#818CF8", "#4ADE80", "#E879F9"];
const HOODC = ["var(--yellow)", "#22D3EE", "#FF3D9A", "#34D399", "#FB923C", "#A78BFA", "#60A5FA", "#A3E635", "#F472B6", "#2DD4BF"];
const COLOURS: { id: Colour; label: string }[] = [
  { id: "dataset", label: "Dataset" }, { id: "type", label: "Entity type" }, { id: "hood", label: "Neighbourhood" },
  { id: "n", label: "Length" }, { id: "anomalies", label: "Anomalies" }, { id: "alen", label: "Anomaly length" },
];

const fmt = (n: number) => n.toLocaleString("en-US");
const pct = (x: number) => `${Math.round(x * 100)}%`;

// Dim purple to yellow, for a value in [0, 1].
function ramp(t: number) {
  const a = [60, 52, 120], b = [255, 225, 77];
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * Math.max(0, Math.min(1, t))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

type Node = { file: string; i: number; x: number; y: number; m?: SeriesMeta; c: number };
type Hood = { c: number; letter: string; colour: string; members: number[]; top: string; topShare: number; det: string; share: number };

// ---- series files, fetched once per tab and shared by every lane ----

const docCache = new Map<string, Promise<SeriesDoc | null>>();
function loadDoc(url: string): Promise<SeriesDoc | null> {
  let p = docCache.get(url);
  if (!p) {
    p = fetch(url).then((r) => (r.ok ? (r.json() as Promise<SeriesDoc>) : null)).catch(() => null);
    docCache.set(url, p);
  }
  return p;
}

// One series as a small polyline with its anomaly windows shaded pink. The
// file is fetched when the lane scrolls into view.
function Lane({ url, file, h, big, nameColour, tag, tagColour, bar, barColour, onPick, open }: {
  url: string; file: string; h: number; big: boolean; nameColour: string; tag: string; tagColour: string; bar: number; barColour: string; onPick: () => void;
  open?: string;   // a link for the name instead of onPick: the selected series opens in the Workbench
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [doc, setDoc] = useState<SeriesDoc | null | undefined>(undefined);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let live = true;
    const io = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      io.disconnect();
      loadDoc(url).then((d) => { if (live) setDoc(d); });
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => { live = false; io.disconnect(); };
  }, [url]);

  const values = doc?.values ?? doc?.channels?.[0]?.values;
  const plot = useMemo(() => {
    if (!values || !values.length) return null;
    const n = values.length;
    let min = Infinity, max = -Infinity;
    for (const v of values) { if (v < min) min = v; if (v > max) max = v; }
    const span = max - min || 1;
    const pts = decimate(values, 300).map(([i, v]) => `${((i / Math.max(1, n - 1)) * 320).toFixed(1)},${(56 - ((v - min) / span) * 52).toFixed(1)}`).join(" ");
    const bands = (doc?.labels ?? []).map(([a, b]) => [(a / Math.max(1, n - 1)) * 320, Math.max(1.5, ((b - a + 1) / Math.max(1, n - 1)) * 320)] as const);
    return { pts, bands };
  }, [values, doc]);

  return (
    <div ref={ref} className="gr-lane" style={{ background: big ? "rgba(255,225,77,0.05)" : "transparent" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        {open ? (
          <Link href={open} className="gr-lk" style={{ flex: "1 1 auto" }} aria-label={`Open ${file} in the Workbench`}>
            <span className="mono ellip" style={{ fontSize: 11, color: nameColour }}>{file}</span>
          </Link>
        ) : (
          <button type="button" className="gr-lk" style={{ flex: "1 1 auto" }} onClick={onPick} aria-label={`Select ${file}`}>
            <span className="mono ellip" style={{ fontSize: 11, color: nameColour }}>{file}</span>
          </button>
        )}
        <span className="mono" style={{ fontSize: 11, color: tagColour, whiteSpace: "nowrap" }}>{tag}</span>
        <span style={{ width: 44, height: 4, borderRadius: 2, background: "var(--panel)", overflow: "hidden", display: "block", flex: "0 0 auto" }}>
          <span style={{ display: "block", height: "100%", background: barColour, width: pct(bar) }} />
        </span>
      </div>
      <svg viewBox="0 0 320 60" preserveAspectRatio="none" role="img" aria-label={`${file}, anomalies shaded`} style={{ width: "100%", height: h, display: "block" }}>
        {plot ? (
          <>
            {plot.bands.map(([x, w], k) => <rect key={k} x={x.toFixed(1)} y="0" width={w.toFixed(1)} height="60" fill="#FF3D9A" fillOpacity="0.28" />)}
            <polyline points={plot.pts} fill="none" stroke={big ? "var(--text)" : "var(--text-2)"} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
          </>
        ) : doc === null ? (
          <text x="160" y="34" textAnchor="middle" fontSize="10" fill="var(--text-3)">not exported</text>
        ) : (
          <line x1="0" y1="30" x2="320" y2="30" stroke="var(--grid)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        )}
      </svg>
    </div>
  );
}

const Badge = ({ letter, colour }: { letter: string; colour: string }) => (
  <span className="gr-badge" style={{ background: colour }}>{letter}</span>
);

const Close = ({ onClick }: { onClick: () => void }) => (
  <button type="button" className="gr-x" aria-label="Close" onClick={onClick}>
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><line x1="2" y1="2" x2="12" y2="12" /><line x1="12" y1="2" x2="2" y2="12" /></svg>
  </button>
);

function Pager({ range, noPrev, noNext, prev, next }: { range: string; noPrev: boolean; noNext: boolean; prev: () => void; next: () => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <button type="button" className="gr-zbtn" aria-label="Previous series" onClick={prev} disabled={noPrev}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><polyline points="9,2 4,7 9,12" /></svg>
      </button>
      <span className="mono" style={{ fontSize: 11, color: "var(--text-3)", whiteSpace: "nowrap" }}>{range}</span>
      <button type="button" className="gr-zbtn" aria-label="Next series" onClick={next} disabled={noNext}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><polyline points="5,2 10,7 5,12" /></svg>
      </button>
    </div>
  );
}

export function GraphView({ summary, landscape, state }: { summary: Summary; landscape: Landscape; state: State }) {
  const scopeKey = `${state.benchmark}:${state.kind}`;
  const [scope, setScope] = useSessionState(`graph.scope:${scopeKey}`, "all");
  const [metric, setMetric] = useSessionState<Metric>("graph.metric", "vus");
  const [colour, setColour] = useSessionState<Colour>("graph.colour", "dataset");
  const [height, setHeight] = useSessionState("graph.height", 700);   // of the two panels, dragged at the handle below them
  const [graph, setGraph] = useState<Graph | null | undefined>(undefined);   // undefined: loading
  // Where the reader is survives a trip to the Workbench and back. Indices
  // are safe to keep: changing the scope or the metric clears the pick.
  const [sel, setSel] = useSessionState<number | null>(`graph.sel:${scopeKey}`, null);          // node index
  const [hood, setHood] = useSessionState<number | null>(`graph.hood:${scopeKey}`, null);       // picked neighbourhood
  const [hoodHover, setHoodHover] = useState<number | null>(null);
  const [iso, setIso] = useSessionState<string | null>(`graph.iso:${scopeKey}`, null);          // isolated legend category
  const [view, setView] = useSessionState<"nb" | "hood">(`graph.view:${scopeKey}`, "nb");
  const [page, setPage] = useSessionState(`graph.page:${scopeKey}`, 0);
  const [hover, setHover] = useState<{ i: number; x: number; y: number; w: number } | null>(null);
  // Zoom and pan as a transform on the drawing group: screen = p * s + t.
  const [tf, setTf] = useSessionState(`graph.tf:${scopeKey}`, { s: 1, tx: 0, ty: 0 });
  const svgRef = useRef<SVGSVGElement>(null);
  const figRef = useRef<HTMLElement>(null);
  const drag = useRef<{ x: number; y: number; tx: number; ty: number; moved: boolean } | null>(null);
  const dragged = useRef(false);
  const resize = useRef<{ y: number; h: number } | null>(null);

  const base = `${DATA_URL}/${state.benchmark}/${state.kind}`;
  const meta = useMemo(() => new Map(summary.series.map((s) => [s.file, s])), [summary]);
  const rows = useMemo(() => new Map(landscape.rows.map((r) => [r.file, r])), [landscape]);

  useEffect(() => {
    let live = true;
    fetch(`${base}/graph.json`).then((r) => (r.ok ? r.json() : null)).then((g) => { if (live) setGraph(g); }).catch(() => { if (live) setGraph(null); });
    return () => { live = false; };
  }, [base]);

  const clearPick = useCallback(() => { setSel(null); setHood(null); setHoodHover(null); setHover(null); setPage(0); }, [setSel, setHood, setPage]);
  const resetZoom = () => setTf({ s: 1, tx: 0, ty: 0 });
  const zoomBy = useCallback((f: number, mx = W / 2, my = H / 2) => setTf((v) => {
    const s = Math.min(40, Math.max(0.25, v.s * f)), k = s / v.s;
    return { s, tx: mx - (mx - v.tx) * k, ty: my - (my - v.ty) * k };
  }), [setTf]);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      // The drawing is centred in the figure (preserveAspectRatio meet).
      const k = Math.min(r.width / W, r.height / H), ox = (r.width - W * k) / 2, oy = (r.height - H * k) / 2;
      zoomBy(e.deltaY > 0 ? 1 / 1.15 : 1.15, (e.clientX - r.left - ox) / k, (e.clientY - r.top - oy) / k);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [graph, zoomBy]);

  const data: GraphData | null = graph?.graphs[scope]?.[metric] ?? null;

  const nodes: Node[] = useMemo(() => (data?.files ?? []).map((f, i) => {
    const [px, py] = data!.nodes[i];
    return { file: f, i, x: PAD + ((px + 1) / 2) * (W - 2 * PAD), y: PAD + ((1 - py) / 2) * (H - 2 * PAD), m: meta.get(f), c: data!.community[i] };
  }), [data, meta]);

  const adj = useMemo(() => {
    const a: { j: number; w: number }[][] = nodes.map(() => []);
    for (const [i, j, w] of data?.edges ?? []) { a[i].push({ j, w }); a[j].push({ j: i, w }); }
    for (const l of a) l.sort((p, r) => r.w - p.w);
    return a;
  }, [data, nodes]);
  const maxW = useMemo(() => Math.max(1e-9, ...(data?.edges.map((e) => e[2]) ?? [])), [data]);

  // The best detectors of a series for the current metric, best first.
  const ranking = useCallback((file: string) => {
    const r = rows.get(file);
    if (!r) return [] as { name: string; value: number }[];
    return r[metric].map((v, i) => ({ name: landscape.detectors[i], value: v }))
      .filter((x): x is { name: string; value: number } => x.value !== null)
      .sort((a, b) => b.value - a.value);
  }, [rows, metric, landscape]);

  // Neighbourhoods: members, the dataset most of them come from, and the
  // detector that is best on the most of them.
  const hoods: Hood[] = useMemo(() => {
    const groups = new Map<number, number[]>();
    for (const n of nodes) { if (!groups.has(n.c)) groups.set(n.c, []); groups.get(n.c)!.push(n.i); }
    return Array.from(groups.entries()).sort((a, b) => a[0] - b[0]).map(([c, members], k) => {
      const ds = new Map<string, number>(), dets = new Map<string, number>();
      for (const i of members) {
        const d = nodes[i].m?.dataset ?? "?";
        ds.set(d, (ds.get(d) ?? 0) + 1);
        const best = ranking(nodes[i].file)[0];
        if (best) dets.set(best.name, (dets.get(best.name) ?? 0) + 1);
      }
      const top = Array.from(ds.entries()).sort((a, b) => b[1] - a[1])[0] ?? ["?", 0];
      const det = Array.from(dets.entries()).sort((a, b) => b[1] - a[1])[0] ?? ["?", 0];
      return { c, letter: String.fromCharCode(65 + k), colour: HOODC[k % HOODC.length], members, top: top[0], topShare: top[1] / members.length, det: det[0], share: det[1] / members.length };
    });
  }, [nodes, ranking]);
  const hoodOf = useMemo(() => new Map(hoods.map((h) => [h.c, h])), [hoods]);

  // Colour of each node and the legend it needs. Categories by count,
  // neighbourhoods in letter order with their badge colours.
  const isCat = colour === "dataset" || colour === "type" || colour === "hood";
  const catOf = useCallback((n: Node) => colour === "hood" ? hoodOf.get(n.c)?.letter ?? "?" : n.m?.[colour as "dataset" | "type"] ?? "?", [colour, hoodOf]);
  const numOf = useCallback((n: Node): number | null => colour === "alen" ? graph?.anomaly_len[n.file] ?? null : n.m?.[colour as "n" | "anomalies"] ?? null, [colour, graph]);
  const { fill, cats, lo, hi } = useMemo(() => {
    if (isCat) {
      let cmap: Map<string, string>;
      if (colour === "hood") {
        cmap = new Map(hoods.map((h) => [h.letter, h.colour]));
      } else {
        const counts = new Map<string, number>();
        for (const n of nodes) { const v = catOf(n); counts.set(v, (counts.get(v) ?? 0) + 1); }
        const sorted = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).map((x) => x[0]);
        cmap = new Map(sorted.map((v, i) => [v, PALETTE[i % PALETTE.length]]));
      }
      return { fill: (n: Node) => cmap.get(catOf(n)) ?? "#888", cats: Array.from(cmap.entries()).map(([v, c]) => [v, c] as const), lo: 0, hi: 0 };
    }
    const vals = nodes.map(numOf).filter((v): v is number => v !== null);
    const log = colour === "n" || colour === "alen";
    const t = (v: number) => (log ? Math.log10(Math.max(1, v)) : v);
    const mn = Math.min(...vals.map(t)), mx = Math.max(...vals.map(t)), span = mx - mn || 1;
    return {
      fill: (n: Node) => { const v = numOf(n); return v == null ? "#555" : ramp((t(v) - mn) / span); },
      cats: [] as (readonly [string, string])[], lo: vals.length ? Math.min(...vals) : 0, hi: vals.length ? Math.max(...vals) : 0,
    };
  }, [nodes, colour, isCat, hoods, catOf, numOf]);

  // What is lit: see the brief's highlight rules, later rules win.
  const nbSet = useMemo(() => new Set(sel !== null ? adj[sel]?.map((e) => e.j) : []), [adj, sel]);
  const hh = sel === null && hood === null ? hoodHover : null;
  const isoCat = isCat ? iso : null;

  const edgeLayer = useMemo(() => data && (
    <g>
      {data.edges.map(([a, b, w], k) => {
        const lit = sel !== null && (a === sel || b === sel);
        let o = 0.08 + 0.3 * (w / maxW);
        if (hh !== null) o = nodes[a].c === hh && nodes[b].c === hh ? o : 0.03;
        if (hood !== null) o = nodes[a].c === hood && nodes[b].c === hood ? o : 0.03;
        if (sel !== null) o = lit ? 0.9 : hood !== null ? Math.min(o, 0.08) : 0.04;
        if (isoCat) o = 0.04;
        return <line key={k} className={lit ? "gr-edge lit" : "gr-edge"} x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y} strokeOpacity={o.toFixed(2)} />;
      })}
    </g>
  ), [data, nodes, sel, hood, hh, isoCat, maxW]);

  const nodeLayer = useMemo(() => (
    <g>
      {nodes.map((n) => {
        const isSel = n.i === sel, near = nbSet.has(n.i), inHood = hood !== null && n.c === hood;
        let o = 1;
        if (hh !== null) o = n.c === hh ? 1 : 0.12;
        if (hood !== null) o = inHood ? 1 : 0.12;
        if (sel !== null) o = isSel || near ? 1 : hood !== null ? (inHood ? 0.8 : 0.1) : 0.3;
        if (isoCat) o = catOf(n) === isoCat ? 1 : 0.12;
        const cls = `gr-node${isSel ? " sel" : near ? " near" : ""}`;
        return (
          <circle key={n.file} className={cls} cx={n.x} cy={n.y} fill={fill(n)} fillOpacity={o}
            onClick={() => { if (dragged.current) return; setSel(isSel ? null : n.i); setIso(null); setPage(0); setHover(null); }}
            onPointerEnter={(e) => { const r = figRef.current?.getBoundingClientRect(); if (r) setHover({ i: n.i, x: e.clientX - r.left, y: e.clientY - r.top, w: r.width }); }}
            onPointerMove={(e) => { const r = figRef.current?.getBoundingClientRect(); if (r) setHover({ i: n.i, x: e.clientX - r.left, y: e.clientY - r.top, w: r.width }); }}
            onPointerLeave={() => setHover((h) => (h?.i === n.i ? null : h))} />
        );
      })}
    </g>
  ), [nodes, sel, nbSet, hood, hh, isoCat, fill, catOf, setSel, setIso, setPage]);

  // ---- the right column ----
  const selNode = sel !== null ? nodes[sel] ?? null : null;
  const selHood = selNode ? hoodOf.get(selNode.c) ?? null : null;
  const pickedHood = hood !== null ? hoodOf.get(hood) ?? null : null;
  const metaOf = (n: Node) => `${n.m?.dataset ?? "?"} · ${n.m?.type ?? "?"} · ${n.m?.n != null ? fmt(n.m.n) : "?"} points · ${n.m?.anomalies ?? "?"} anomalies`;
  const laneUrl = (n: Node) => `${base}/series/${stem(n.file)}.json`;
  const pickNode = (i: number) => { setSel(i); setPage(0); setHover(null); };
  const pageOf = (list: number[]) => {
    const pages = Math.max(1, Math.ceil(list.length / PAGE)), p = Math.min(page, pages - 1);
    const from = p * PAGE, to = Math.min(list.length, from + PAGE);
    return { rows: list.slice(from, to), paged: list.length > PAGE, range: `${from + 1} to ${to} of ${list.length}`, noPrev: p === 0, noNext: p >= pages - 1,
      prev: () => setPage(Math.max(0, p - 1)), next: () => setPage(Math.min(pages - 1, p + 1)) };
  };
  const hoodLane = (i: number) => {
    const n = nodes[i], best = ranking(n.file)[0];
    return <Lane key={n.file} url={laneUrl(n)} file={n.file} h={52} big={false} nameColour="var(--text)" tag={`${n.m?.dataset ?? "?"} · ${best ? `${best.name} ${best.value.toFixed(2)}` : "no score"}`} tagColour="var(--text-3)" bar={best?.value ?? 0} barColour="var(--det)" onPick={() => pickNode(i)} />;
  };

  const metricLabel = graph?.metrics[metric].label ?? metric;
  const scopes = graph?.scopes ?? [];
  const datasets = scopes.filter((s) => s.group === "dataset"), types = scopes.filter((s) => s.group === "type");
  const hov = hover !== null ? nodes[hover.i] : null;

  let side: React.ReactNode;
  if (selNode !== null && selHood !== null) {
    const h = selHood;
    const best = ranking(selNode.file).slice(0, 3);
    const nbs = adj[selNode.i];
    const inHood = view === "hood";
    const p = inHood ? pageOf(h.members.filter((m) => m !== selNode.i)) : null;
    side = (
      <>
        <div className="gr-head">
          <Badge letter={h.letter} colour={h.colour} />
          <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: "1 1 auto" }}>
            <span className="mono" style={{ fontSize: 13, lineHeight: 1.4, wordBreak: "break-all" }}>{selNode.file}</span>
            <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{metaOf(selNode)}</span>
          </span>
          <Close onClick={clearPick} />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "8px 16px", padding: "10px 20px", borderBottom: "1px solid var(--grid)" }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-3)", minWidth: 0 }}>
            <span style={{ color: "var(--det-soft)" }}>solved best by</span> {best.length ? best.map((d) => `${d.name} ${d.value.toFixed(2)}`).join(" · ") : "no scores"}
          </span>
          <div className="seg gr-tiny" role="group" aria-label="What to stack below">
            <button type="button" aria-pressed={!inHood} onClick={() => { setView("nb"); setHood(null); setPage(0); }}>Neighbours</button>
            <button type="button" aria-pressed={inHood} onClick={() => { setView("hood"); setHood(selNode.c); setPage(0); }}>Neighbourhood {h.letter}</button>
          </div>
        </div>
        <div className="gr-list-head">
          <span className="lbl" style={{ fontSize: 11 }}>{inHood ? `Neighbourhood ${h.letter} · ${h.det} wins on ${pct(h.share)}` : `${nbs.length} neighbours · strongest link first`}</span>
          {p?.paged && <Pager {...p} />}
        </div>
        <div className="gr-scroll">
          <Lane url={laneUrl(selNode)} file={selNode.file} h={120} big nameColour="var(--yellow)" tag="selected" tagColour="var(--yellow)" bar={best[0]?.value ?? 0} barColour="var(--det)" onPick={() => {}} open={href("/workbench", state, { s: selNode.file })} />
          {inHood
            ? p!.rows.map(hoodLane)
            : nbs.map((e) => {
              const n = nodes[e.j], w = e.w / maxW;
              return <Lane key={n.file} url={laneUrl(n)} file={n.file} h={52} big={false} nameColour="var(--text)" tag={`${n.m?.dataset ?? "?"} · link ${w.toFixed(2)}`} tagColour="var(--text-3)" bar={w} barColour="var(--yellow)" onPick={() => pickNode(e.j)} />;
            })}
        </div>
        <div style={{ padding: "10px 20px", borderTop: "1px solid var(--grid)", display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10 }}>
          <Link href={href("/workbench", state, { s: selNode.file })} className="gr-btn-soft">
            Open this time series in the Workbench <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><line x1="2" y1="8" x2="13" y2="8" /><polyline points="9,4 13,8 9,12" /></svg>
          </Link>
        </div>
      </>
    );
  } else if (pickedHood !== null) {
    const h = pickedHood;
    const p = pageOf(h.members);
    side = (
      <>
        <div className="gr-head">
          <Badge letter={h.letter} colour={h.colour} />
          <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: "1 1 auto" }}>
            <span className="mono" style={{ fontSize: 13, lineHeight: 1.4 }}>Neighbourhood {h.letter} · {fmt(h.members.length)} series, {pct(h.topShare)} {h.top}</span>
            <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{h.det} wins on {pct(h.share)} of them · click a name to select it</span>
          </span>
          <Close onClick={clearPick} />
        </div>
        <div className="gr-list-head">
          <span className="lbl" style={{ fontSize: 11 }}>each series with its best detector</span>
          {p.paged && <Pager {...p} />}
        </div>
        <div className="gr-scroll">{p.rows.map(hoodLane)}</div>
      </>
    );
  } else {
    side = (
      <>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, padding: "16px 20px 10px" }}>
          <span className="lbl">Neighbourhoods · {hoods.length}</span>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>click to inspect</span>
        </div>
        <div className="gr-scroll" style={{ padding: "0 20px", display: "flex", flexDirection: "column", gap: 2 }}>
          {hoods.map((h) => (
            <button key={h.c} type="button" className="gr-hrow" aria-pressed={hood === h.c}
              onClick={() => { setHood(h.c); setHoodHover(null); setSel(null); setIso(null); setPage(0); setView("hood"); }}
              onMouseEnter={() => setHoodHover(h.c)} onMouseLeave={() => setHoodHover((v) => (v === h.c ? null : v))}
              onFocus={() => setHoodHover(h.c)} onBlur={() => setHoodHover((v) => (v === h.c ? null : v))}>
              <Badge letter={h.letter} colour={h.colour} />
              <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <span style={{ fontSize: 15 }}>{fmt(h.members.length)} series, {pct(h.topShare)} {h.top}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-3)" }}>{h.det} wins on {pct(h.share)} of them</span>
              </span>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--text-3)" strokeWidth="1.6" aria-hidden="true"><polyline points="5,2 10,7 5,12" /></svg>
            </button>
          ))}
        </div>
        <p style={{ margin: 0, padding: "14px 20px", borderTop: "1px solid var(--grid)", color: "var(--text-3)", fontSize: 14 }}>
          Or click a dot on the graph: the series appears here, its neighbours stacked below it.
        </p>
      </>
    );
  }

  return (
    <>
      <section className="wrap" style={{ paddingBottom: 16 }}>
        <div className="panel ls-controls" style={{ padding: "14px 20px", gap: "14px 24px" }}>
          <div className="ctl">
            <label className="lbl" htmlFor="gr-scope">Series</label>
            <div className="select">
              <select id="gr-scope" value={scope} onChange={(e) => { setScope(e.target.value); clearPick(); setIso(null); resetZoom(); }}>
                <option value="all">All {scopes[0]?.n ?? ""}</option>
                <optgroup label="One dataset">{datasets.map((s) => <option key={s.key} value={s.key}>{s.value} ({s.n})</option>)}</optgroup>
                <optgroup label="One entity type">{types.map((s) => <option key={s.key} value={s.key}>{s.value} ({s.n})</option>)}</optgroup>
              </select>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><polyline points="2,4 6,8 10,4" /></svg>
            </div>
          </div>
          <div className="ctl">
            <span className="lbl" id="gr-metric">Metric</span>
            <div className="seg tall" role="group" aria-labelledby="gr-metric">
              <button type="button" aria-pressed={metric === "aucpr"} onClick={() => { setMetric("aucpr"); clearPick(); }}>AUC-PR</button>
              <button type="button" aria-pressed={metric === "vus"} onClick={() => { setMetric("vus"); clearPick(); }}>VUS-PR</button>
            </div>
          </div>
          <div className="ctl">
            <span className="lbl" id="gr-colour">Colour by</span>
            <div className="seg tall" role="group" aria-labelledby="gr-colour">
              {COLOURS.map((c) => <button key={c.id} type="button" aria-pressed={colour === c.id} onClick={() => { setColour(c.id); setIso(null); }}>{c.label}</button>)}
            </div>
          </div>
        </div>
      </section>

      <section className="wrap" style={{ paddingBottom: 14 }}>
        <p className="rk-title">Which series are solved by the same detectors? <span>Each dot is a series. Dots close together are solved by the same detectors.</span></p>
      </section>

      <section className="wrap gr-main" style={{ "--gr-h": `${height}px` } as React.CSSProperties}>
        <figure ref={figRef} className="gr-fig">
          {graph === undefined ? (
            <p className="gr-note">Loading the graph…</p>
          ) : graph === null ? (
            <p className="gr-note">No graph exported for this benchmark yet. Run <code className="inline">scripts/export_graph.py</code> first.</p>
          ) : !data || !nodes.length ? (
            <p className="gr-note">No {metricLabel} scores for these series.</p>
          ) : (
            <>
              <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Series graph"
                style={{ display: "block", cursor: "grab", touchAction: "none" }}
                onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, tx: tf.tx, ty: tf.ty, moved: false }; }}
                onPointerMove={(e) => {
                  const d = drag.current; if (!d) return;
                  const r = e.currentTarget.getBoundingClientRect();
                  const k = Math.min(r.width / W, r.height / H);
                  const dx = (e.clientX - d.x) / k, dy = (e.clientY - d.y) / k;
                  if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) d.moved = true;
                  setTf((v) => ({ ...v, tx: d.tx + dx, ty: d.ty + dy }));
                }}
                onPointerUp={() => { dragged.current = drag.current?.moved ?? false; drag.current = null; }}
                onPointerLeave={() => { drag.current = null; }}
                onDoubleClick={resetZoom}>
                <g transform={`translate(${tf.tx} ${tf.ty}) scale(${tf.s})`} style={{ "--z": 1 / tf.s } as React.CSSProperties}>
                  {edgeLayer}
                  {nodeLayer}
                </g>
              </svg>
              {hov && hover && (
                <div className="gr-tip" style={hover.x > hover.w * 0.55 ? { right: hover.w - hover.x + 14, top: hover.y - 10 } : { left: hover.x + 14, top: hover.y - 10 }}>
                  <div style={{ color: "var(--text)" }}>{hov.file}</div>
                  <div style={{ color: "var(--text-3)" }}>{metaOf(hov)} · neighbourhood {hoodOf.get(hov.c)?.letter ?? "?"}</div>
                </div>
              )}
              <div className="gr-over mono" style={{ left: 16, top: 14 }}>
                {fmt(nodes.length)} series · {fmt(data.edges.length)} edges, the {graph.k} strongest per series · {data.n_detectors} detectors on {metricLabel}
              </div>
              <figcaption className="gr-over mono" style={{ left: 16, bottom: 14, maxWidth: "calc(100% - 90px)" }}>Click a dot to see the series · scroll to zoom · drag to move · double-click to reset</figcaption>
              <div className="gr-legend">
                {isCat
                  ? cats.map(([v, c]) => (
                    <button key={v} type="button" className="gr-chip" aria-pressed={iso === v} style={{ opacity: iso && iso !== v ? 0.45 : 1 }}
                      onClick={() => { setIso(iso === v ? null : v); clearPick(); }}>
                      <i aria-hidden="true" style={{ background: c }} />{v}
                    </button>
                  ))
                  : <span className="mono" style={{ fontSize: 11, color: "var(--text-3)", display: "inline-flex", alignItems: "center", gap: 6 }}>
                    {fmt(lo)}<span aria-hidden="true" style={{ width: 70, height: 7, borderRadius: 4, background: `linear-gradient(90deg, ${ramp(0)}, ${ramp(1)})` }} />{fmt(hi)}{colour === "n" || colour === "alen" ? " (log)" : ""}
                  </span>}
              </div>
              <div style={{ position: "absolute", right: 16, bottom: 16, display: "flex", flexDirection: "column", gap: 6 }}>
                <button type="button" className="gr-zbtn big" aria-label="Zoom in" onClick={() => zoomBy(1.25)}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><line x1="8" y1="3" x2="8" y2="13" /><line x1="3" y1="8" x2="13" y2="8" /></svg>
                </button>
                <button type="button" className="gr-zbtn big" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.25)}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><line x1="3" y1="8" x2="13" y2="8" /></svg>
                </button>
              </div>
            </>
          )}
        </figure>
        <aside className="surface gr-side">{side}</aside>
      </section>
      <section className="wrap" style={{ paddingBottom: 24 }}>
        <div className="gr-handle" role="separator" aria-orientation="horizontal" aria-label="Drag to change the height of the panels" title="Drag to resize"
          onPointerDown={(e) => { resize.current = { y: e.clientY, h: height }; e.currentTarget.setPointerCapture(e.pointerId); }}
          onPointerMove={(e) => { const r = resize.current; if (r) setHeight(Math.max(480, Math.min(1400, Math.round(r.h + e.clientY - r.y)))); }}
          onPointerUp={() => { resize.current = null; }}
          onDoubleClick={() => setHeight(700)}>
          <i aria-hidden="true" />
        </div>
      </section>
    </>
  );
}
