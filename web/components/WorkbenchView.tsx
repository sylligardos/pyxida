"use client";

// Workbench: one series, its labels, and what the detectors did on it.
// The detectors shown are the top N on this series by the chosen metric,
// plus the ones pinned; pins follow the reader from series to series.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { Landscape, SeriesDoc, State, Summary } from "@/lib/model";
import { DATA_URL, href, stem } from "@/lib/model";
import { LaneChart, type Lane } from "./LaneChart";
import { ONE_LINERS, averagePrecision } from "@/lib/oneliners";
import { useSessionState } from "@/lib/session";

type Metric = "aucpr" | "vus";
const MAX_TOP = 6;
const DEFAULT_TOP = 3;
const DEFAULT_CHANNELS = 3;
const DEFAULT_K = 20;
const MAX_K = 200;
const SAMPLE_MAX_POINTS = 300_000;
const PINS_KEY = "pyxida.pins";
const NOTES_KEY = "pyxida.notes";

type Notes = Record<string, { note: string; updated: string }>;

function readLocal<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v ? (JSON.parse(v) as T) : fallback; } catch { return fallback; }
}
function writeLocal(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private window, full, or blocked */ }
}
function putNotes(notes: Notes) {
  return fetch("/api/notes", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(notes) }).catch(() => {});
}

const fmt = (n: number) => n.toLocaleString("en-US");

export function WorkbenchView({ summary, landscape, state, initial, explicit, pin, top, avg, metric: metricParam }: {
  summary: Summary; landscape: Landscape | null; state: State; initial: string; explicit: boolean;
  pin: string | null; top: string | null; avg: string | null; metric: Metric | null;
}) {
  // The series, metric and top-N survive navigation within the tab. A link
  // that names a series (?s=, ?sample=1, ?hardest=1) is a request for that
  // one and wins over the remembered series.
  const scopeKey = `${state.benchmark}:${state.kind}`;
  const [file, setFile] = useSessionState(`workbench.file:${scopeKey}`, initial, () => !explicit);
  // A link that names the metric (?m=aucpr) carries it over from the page it came from.
  const [metric, setMetric] = useSessionState<Metric>("workbench.metric", metricParam ?? "vus", () => !metricParam);
  const [topN, setTopN] = useSessionState("workbench.topN", DEFAULT_TOP);
  const [pins, setPins] = useState<string[]>([]);
  // Stacks to draw as one lane each, their scores averaged (?avg=A,B|C,D).
  const [avgs, setAvgs] = useState<string[][]>([]);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [channels, setChannels] = useState<number[]>([0, 1, 2]);
  const [doc, setDoc] = useState<SeriesDoc | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scores, setScores] = useState<Record<string, Uint16Array | null>>({});
  const [notes, setNotes] = useState<Notes>({});
  const [draft, setDraft] = useState("");
  // "I'm feeling lucky": Keogh's one-liners run in the browser on this
  // series, k is their window. While on, the metric is AUC-PR for all.
  const [lucky, setLucky] = useState(false);
  const [k, setK] = useState(DEFAULT_K);
  const metricBefore = useRef<Metric>("vus");
  const cache = useRef(new Map<string, Promise<Uint16Array | null>>());
  const loaded = useRef(false);     // pins are written back only after they were read

  const base = `${DATA_URL}/${state.benchmark}/${state.kind}`;
  const meta = useMemo(() => new Map(summary.series.map((s) => [s.file, s])), [summary]);
  const datasets = useMemo(() => Array.from(new Set(summary.series.map((s) => s.dataset))).sort(), [summary]);
  const row = meta.get(file);
  const dataset = row?.dataset ?? datasets[0];
  const inDataset = useMemo(() => summary.series.filter((s) => s.dataset === dataset).map((s) => s.file).sort(), [summary, dataset]);

  // Ranking of the detectors on this series, best first.
  const ranking = useMemo(() => {
    const r = landscape?.rows.find((x) => x.file === file);
    if (!r) return [] as { name: string; value: number }[];
    return r[metric].map((v, i) => ({ name: landscape!.detectors[i], value: v }))
      .filter((x): x is { name: string; value: number } => x.value !== null)
      .sort((a, b) => b.value - a.value);
  }, [landscape, file, metric]);
  const rankOf = useMemo(() => new Map(ranking.map((x, i) => [x.name, i + 1])), [ranking]);
  const valueOf = useMemo(() => new Map(ranking.map((x) => [x.name, x.value])), [ranking]);
  const roster = useMemo(() => [...summary.detectors].sort((a, b) => (rankOf.get(a) ?? 1e9) - (rankOf.get(b) ?? 1e9) || a.localeCompare(b)), [summary, rankOf]);

  const shown = useMemo(() => {
    const top = ranking.length ? ranking.slice(0, topN).map((x) => x.name) : roster.slice(0, topN);
    const set = new Map<string, boolean>();
    for (const d of top) set.set(d, false);
    for (const d of pins) set.set(d, true);
    return Array.from(set.entries()).sort((a, b) => (rankOf.get(a[0]) ?? 1e9) - (rankOf.get(b[0]) ?? 1e9));
  }, [ranking, roster, topN, pins, rankOf]);

  // Persisted per browser. A link that names detectors (?pin=A,B&top=0)
  // replaces the pins: it is a request to look at those detectors. They
  // come from the server's reading of the URL, not window.location, which
  // the effect below rewrites (and a second effect run would miss them).
  useEffect(() => {
    if (pin) {
      setPins(pin.split(",").filter((d) => summary.detectors.includes(d)));
      if (top !== null) setTopN(Math.max(0, Math.min(MAX_TOP, Number(top) || 0)));
    } else setPins(readLocal(PINS_KEY, []));
    setAvgs((avg ?? "").split("|").map((g) => g.split(",").filter((d) => summary.detectors.includes(d))).filter((g) => g.length > 1));
    fetch("/api/notes").then((r) => (r.ok ? r.json() : {})).then((server: Notes) => {
      const local = readLocal<Notes>(NOTES_KEY, {});
      const merged = { ...local, ...server };
      setNotes(merged);
      if (Object.keys(local).length) {   // old browser notes: push them to the file, then forget them
        putNotes(merged).then(() => { try { localStorage.removeItem(NOTES_KEY); } catch { /* blocked */ } });
      }
    }).catch(() => setNotes(readLocal(NOTES_KEY, {})));
    loaded.current = true;
  }, [summary, pin, top, avg]);
  useEffect(() => { if (loaded.current) writeLocal(PINS_KEY, pins); }, [pins]);

  // The URL follows the series, so a link to the Workbench is a link to a series.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    q.set("s", file); q.delete("sample"); q.delete("hardest"); q.delete("pin"); q.delete("top"); q.delete("avg"); q.delete("m");
    window.history.replaceState(null, "", `${window.location.pathname}?${q}`);
  }, [file]);

  // Load the series. The score cache holds the current series only: a
  // 900k-point lane is 1.8 MB, and nobody returns to a sampled series.
  useEffect(() => {
    let live = true;
    cache.current.clear();
    setDoc(null); setLoadError(null); setHighlight(null); setChannels(Array.from({ length: DEFAULT_CHANNELS }, (_, i) => i));
    fetch(`${base}/series/${stem(file)}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status === 404 ? "not exported" : `HTTP ${r.status}`))))
      .then((d) => { if (live) setDoc(d); })
      .catch((e: Error) => { if (live) setLoadError(e.message); });
    return () => { live = false; };
  }, [base, file]);

  // Load the scores shown, once each.
  const loadScore = useCallback((det: string) => {
    const key = `${file}/${det}`;
    if (!cache.current.has(key)) {
      cache.current.set(key, fetch(`${base}/scores/${stem(file)}/${det}.u16`)
        .then((r) => (r.ok ? r.arrayBuffer() : null))
        .then((b) => (b ? new Uint16Array(b) : null)));
    }
    return cache.current.get(key)!;
  }, [base, file]);

  useEffect(() => {
    let live = true;
    const want = Array.from(new Set([...shown.map(([d]) => d), ...avgs.flat()]));
    Promise.all(want.map((d) => loadScore(d).then((s) => [d, s] as const))).then((pairs) => {
      if (live) setScores(Object.fromEntries(pairs));
    });
    return () => { live = false; };
  }, [shown, avgs, loadScore]);

  // Each stack's lane: the mean of its detectors' scaled scores, as the
  // Redundancy page stacks them, with its AUC-PR on this series.
  const avgLanes = useMemo<Lane[]>(() => {
    if (!doc) return [];
    return avgs.flatMap((g) => {
      const ss = g.map((d) => scores[d]);
      if (ss.some((s) => !s || s.length !== doc.n)) return [];
      const values = new Float32Array(doc.n);
      for (const s of ss) for (let i = 0; i < doc.n; i++) values[i] += s![i] / ss.length;
      const ap = averagePrecision(values, doc.labels);
      return [{ id: `avg:${g.join("+")}`, kind: "score" as const, title: `avg ${g.join(" + ")}`, lines: g, sub: `${isNaN(ap) ? "no labels" : `AUC ${ap.toFixed(2)}`} · avg`, values }];
    });
  }, [avgs, scores, doc]);

  useEffect(() => { setDraft(notes[`${state.benchmark}:${state.kind}:${file}`]?.note ?? ""); }, [notes, file, state]);

  const sample = () => {
    const pool = summary.series.filter((s) => (s.n ?? 0) <= SAMPLE_MAX_POINTS);
    const pick = (pool.length ? pool : summary.series)[Math.floor(Math.random() * (pool.length || summary.series.length))];
    if (pick) setFile(pick.file);
  };

  const toggleLucky = () => {
    if (lucky) { setLucky(false); setMetric(metricBefore.current); }
    else { metricBefore.current = metric; setMetric("aucpr"); setLucky(true); }
  };
  const series = doc ? (doc.values ?? doc.channels?.[channels[0] ?? 0]?.values ?? null) : null;
  const luckyLanes = useMemo<Lane[]>(() => {
    if (!lucky || !doc || !series) return [];
    return ONE_LINERS.map((o) => ({ o, values: o.run(series, k) }))
      .map(({ o, values }) => ({ o, values, ap: averagePrecision(values, doc.labels) }))
      .sort((a, b) => (isNaN(b.ap) ? -1 : b.ap) - (isNaN(a.ap) ? -1 : a.ap))
      .map(({ o, values, ap }, i) => ({ id: `lucky:${o.id}`, kind: "lucky" as const, title: `#${i + 1} ${o.title}`, sub: `${isNaN(ap) ? "no labels" : `AUC ${ap.toFixed(2)}`} · one-liner`, values }));
  }, [lucky, doc, series, k]);

  const pointsAnomalous = doc ? doc.labels.reduce((s, [a, b]) => s + (b - a + 1), 0) : 0;
  const n = doc?.n ?? row?.n ?? 0;

  const lanes: Lane[] = [];
  if (doc) {
    if (doc.channels) {
      for (const c of channels.filter((c) => c < doc.channels!.length)) {
        lanes.push({ id: `ch${c}`, kind: "series", title: doc.channels[c].name, sub: c === channels[0] && doc.labels.length ? (highlight !== null ? `labeled anomaly #${highlight + 1}` : `${doc.labels.length} labeled anomal${doc.labels.length === 1 ? "y" : "ies"}`) : undefined, values: doc.channels[c].values });
      }
    } else if (doc.values) {
      lanes.push({ id: "series", kind: "series", title: "Series", sub: doc.labels.length ? (highlight !== null ? `labeled anomaly #${highlight + 1}` : `${doc.labels.length} labeled anomal${doc.labels.length === 1 ? "y" : "ies"}`) : "no labeled anomaly", values: doc.values });
    }
    for (const [d, pinned] of shown) {
      const s = scores[d];
      if (!s || s.length !== doc.n) continue;
      const rank = rankOf.get(d), v = valueOf.get(d);
      lanes.push({ id: d, kind: "score", title: `${rank ? `#${rank} ` : ""}${d}`, sub: `${v !== undefined ? `${metric === "vus" ? "VUS" : "AUC"} ${v.toFixed(2)}` : "unranked"}${pinned ? " · pinned" : ""}`, pinned, values: s });
    }
    lanes.push(...avgLanes, ...luckyLanes);
  }

  // Fetched but absent or of the wrong length: not drawn, and said so.
  const missing = doc ? shown.map(([d]) => d).filter((d) => d in scores && (!scores[d] || scores[d]!.length !== doc.n)) : [];
  const noteKey = `${state.benchmark}:${state.kind}:${file}`;
  const noted = useMemo(() => Object.entries(notes).sort((a, b) => b[1].updated.localeCompare(a[1].updated)), [notes]);
  const saveNote = () => {
    const next = { ...notes };
    if (draft.trim()) next[noteKey] = { note: draft.trim(), updated: new Date().toISOString().slice(0, 16).replace("T", " ") };
    else delete next[noteKey];
    setNotes(next); putNotes(next);
  };
  const deleteNote = (k: string) => {
    const next = { ...notes }; delete next[k];
    setNotes(next); putNotes(next);
    if (k === noteKey) setDraft("");
  };
  const editNote = (f: string) => { setFile(f); setTimeout(() => document.getElementById("wb-note")?.focus(), 50); };
  const exportNotes = () => {
    const rows = [["series", "note", "updated"], ...Object.entries(notes).map(([k, v]) => [k, v.note, v.updated])];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "pyxida-notes.csv"; a.click(); URL.revokeObjectURL(a.href);
  };

  return (
    <section className="wrap wb" style={{ paddingBottom: 72 }}>
      <aside className="wb-side">
        <button type="button" className="btn btn-primary" onClick={sample}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4" /><circle cx="8.5" cy="8.5" r="1.4" fill="currentColor" /><circle cx="15.5" cy="15.5" r="1.4" fill="currentColor" /><circle cx="15.5" cy="8.5" r="1.4" fill="currentColor" /><circle cx="8.5" cy="15.5" r="1.4" fill="currentColor" /></svg>
          Sample a series
        </button>
        <div className="panel wb-box">
          <div className="ctl">
            <label className="lbl" htmlFor="wb-ds">Dataset</label>
            <div className="select sel"><select id="wb-ds" value={dataset} onChange={(e) => {
              const first = summary.series.filter((s) => s.dataset === e.target.value).map((s) => s.file).sort()[0];
              if (first) setFile(first);
            }}>{datasets.map((d) => <option key={d} value={d}>{d}</option>)}</select><Chev /></div>
          </div>
          <div className="ctl">
            <label className="lbl" htmlFor="wb-series">Series</label>
            <div className="select sel mono"><select id="wb-series" value={file} onChange={(e) => setFile(e.target.value)} style={{ fontFamily: "var(--mono)", fontSize: 13 }}>
              {inDataset.map((f) => <option key={f} value={f}>{stem(f)}</option>)}
            </select><Chev /></div>
          </div>
        </div>
        <div className="panel wb-box">
          <div className="ctl">
            <span className="lbl" id="wb-metric">Rank detectors by</span>
            <div className="seg tall" role="group" aria-labelledby="wb-metric" style={{ display: "flex" }}>
              <button type="button" aria-pressed={metric === "aucpr"} onClick={() => setMetric("aucpr")} style={{ flex: 1, justifyContent: "center" }}>AUC-PR</button>
              <button type="button" aria-pressed={metric === "vus"} disabled={lucky} title={lucky ? "One-liners are scored by AUC-PR only" : undefined} onClick={() => setMetric("vus")} style={{ flex: 1, justifyContent: "center" }}>VUS-PR</button>
            </div>
          </div>
          <div className="ctl">
            <label className="lbl" htmlFor="wb-topn">Top detectors <span style={{ color: "var(--det)" }}>{topN === 0 ? "pins only" : topN}</span></label>
            <input id="wb-topn" type="range" min={0} max={MAX_TOP} step={1} value={topN} onChange={(e) => setTopN(Number(e.target.value))} style={{ accentColor: "var(--det)", height: 40, margin: 0, width: "100%" }} />
          </div>
          <div className="ctl">
            <span className="lbl">Also show</span>
            <div className="chips">
              {pins.map((d) => (
                <span key={d} className="chip">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFE14D" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M12 17v5M8 3h8l-1 7 3 3H6l3-3z" /></svg>
                  {d}
                  <button type="button" aria-label={`Unpin ${d}`} onClick={() => setPins(pins.filter((p) => p !== d))}>×</button>
                </span>
              ))}
              {avgs.map((g, i) => (
                <span key={g.join("+")} className="chip">
                  avg {g.join(" + ")}
                  <button type="button" aria-label={`Remove the average of ${g.join(" and ")}`} onClick={() => setAvgs(avgs.filter((_, j) => j !== i))}>×</button>
                </span>
              ))}
              <div className="select chip-select">
                <select aria-label="Pin a detector" value="" onChange={(e) => { if (e.target.value && !pins.includes(e.target.value)) setPins([...pins, e.target.value]); }}>
                  <option value="">+ pin a detector</option>
                  {roster.filter((d) => !pins.includes(d)).map((d) => (
                    <option key={d} value={d}>{rankOf.has(d) ? `#${rankOf.get(d)} ${d} · ${valueOf.get(d)!.toFixed(2)}` : d}</option>
                  ))}
                </select><Chev />
              </div>
            </div>
          </div>
          <div className="ctl">
            <button type="button" className={`btn ${lucky ? "btn-primary" : "btn-outline"}`} aria-pressed={lucky} onClick={toggleLucky} style={{ height: 44, fontSize: 15, background: lucky ? "#FB923C" : undefined, borderColor: "#FB923C", color: lucky ? "#1C1500" : "#FB923C" }}>
              I&apos;m feeling lucky
            </button>
            {lucky ? (
              <>
                <label className="lbl" htmlFor="wb-k" style={{ marginTop: 8 }}>Window k <span style={{ color: "#FB923C" }}>{k}</span></label>
                <input id="wb-k" type="range" min={2} max={MAX_K} step={1} value={k} onChange={(e) => setK(Number(e.target.value))} style={{ accentColor: "#FB923C", height: 40, margin: 0, width: "100%" }} />
                <span className="muted" style={{ fontSize: 12 }}>Keogh&apos;s one-liners, run live on this series and scored by AUC-PR.</span>
              </>
            ) : <span className="muted" style={{ fontSize: 12 }}>Run eight one-line detectors on this series.</span>}
          </div>
        </div>
      </aside>

      <div className="wb-main">
        <div className="wb-title">
          <h2 className="mono">{stem(file)}</h2>
        </div>
        <div className="tiles">
          <Tile v={row?.dataset ?? "–"} l="Dataset" />
          <Tile v={row?.type ?? "–"} l="Type" />
          <Tile v={n ? fmt(n) : "–"} l="Length" />
          <Tile v={doc ? String(doc.labels.length) : "–"} l="Anomalies" yellow />
          <Tile v={doc && n ? `${((100 * pointsAnomalous) / n).toFixed(2)}%` : "–"} l="Anomalous" />
        </div>

        {doc && doc.labels.length > 0 && (
          <div className="chips" style={{ alignItems: "center" }}>
            <span className="lbl">Highlight an anomaly</span>
            <button type="button" className="chip" aria-pressed={highlight === null} onClick={() => setHighlight(null)} style={{ color: highlight === null ? "var(--yellow)" : undefined }}>Show all</button>
            {doc.labels.slice(0, 12).map(([a, b], i) => (
              <button type="button" key={i} className={`chip${highlight === i ? " on" : ""}`} aria-pressed={highlight === i} onClick={() => setHighlight(highlight === i ? null : i)}>
                <span className="swatch-label" style={{ width: 10, height: 8 }} aria-hidden="true" />#{i + 1} · {fmt(a)}–{fmt(b)} · {fmt(b - a + 1)} pts
              </button>
            ))}
            {doc.labels.length > 12 && <span className="muted" style={{ fontSize: 13 }}>and {doc.labels.length - 12} more</span>}
          </div>
        )}

        {doc?.channels && (
          <div className="chips" style={{ alignItems: "center" }}>
            <span className="lbl">Channels ({doc.n_channels} in this series{doc.n_channels! > doc.channels.length ? `, first ${doc.channels.length} exported` : ""})</span>
            {doc.channels.map((c, i) => (
              <button type="button" key={i} className={`chip${channels.includes(i) ? " on" : ""}`} aria-pressed={channels.includes(i)}
                onClick={() => setChannels(channels.includes(i) ? channels.filter((x) => x !== i) : [...channels, i].sort((a, b) => a - b))}>{c.name}</button>
            ))}
          </div>
        )}

        <figure className="surface wb-chart">
          {doc ? (
            lanes.length ? <LaneChart n={doc.n} lanes={lanes} labels={doc.labels} highlight={highlight} /> : <p className="muted" style={{ padding: 40, textAlign: "center" }}>No detectors selected. Raise Top detectors or pin some.</p>
          ) : loadError ? (
            <p className="muted" style={{ padding: 60, textAlign: "center" }}>
              {loadError === "not exported"
                ? <>This series is not exported yet. Run <code className="inline">scripts/export_web.py --benchmark {state.benchmark} --kind {state.kind} --all</code>.</>
                : <>Could not load {stem(file)} ({loadError}).</>}
            </p>
          ) : (
            <p className="muted" style={{ padding: 60, textAlign: "center" }}>Loading {stem(file)} …</p>
          )}
          <figcaption className="rk-xlabel">Drag to zoom · double-click to reset</figcaption>
        </figure>
        {missing.length > 0 && (
          <p className="muted" style={{ fontSize: 13 }}>Not scored on this series, so not drawn: {missing.join(", ")}.</p>
        )}

        <div className="panel notes">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <label htmlFor="wb-note" style={{ fontSize: 18, fontWeight: 600 }}>Notes</label>
            <span className="mono muted" style={{ fontSize: 12 }}>{Object.keys(notes).length} series with notes</span>
          </div>
          <textarea id="wb-note" rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. MatrixProfile fires 12 points before the anomaly, not on it." />
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <div style={{ display: "flex", gap: 10 }}>
              <button type="button" className="btn btn-outline" style={{ height: 44, padding: "0 20px", fontSize: 15 }} onClick={saveNote}>{notes[noteKey] ? "Update note" : "Save note"}</button>
              {notes[noteKey] && <button type="button" className="btn-sm" onClick={() => deleteNote(noteKey)}>Delete note</button>}
              {Object.keys(notes).length > 0 && <button type="button" className="btn-sm" onClick={exportNotes}>Export as CSV</button>}
            </div>
            {notes[noteKey] && <span className="muted" style={{ fontSize: 13 }}>Saved {notes[noteKey].updated}</span>}
          </div>
          {noted.length > 0 && (
            <div className="note-list">
              {noted.map(([k, v]) => {
                const [b, kind, f] = k.split(":");
                const here = k === noteKey, mine = b === state.benchmark && kind === state.kind;
                return (
                  <div key={k} className="note-row" aria-current={here ? "true" : undefined}>
                    {mine
                      ? <button type="button" className="mono note-open" onClick={() => editNote(f)}>{stem(f)}</button>
                      : <span className="mono note-open" style={{ color: "var(--text-3)" }}>{b} {kind} · {stem(f)}</span>}
                    <span style={{ fontSize: 14, color: "var(--text-2)" }}>{v.note}</span>
                    <span className="mono muted" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{v.updated}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <p className="muted" style={{ fontSize: 13 }}>
          <Link href={href("/game", state)}>Try this one yourself →</Link>
        </p>
      </div>
    </section>
  );
}

const Chev = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><polyline points="2,4 6,8 10,4" /></svg>
);

function Tile({ v, l, yellow }: { v: string; l: string; yellow?: boolean }) {
  return (
    <div className="panel tile">
      <span className="mono" style={{ fontSize: 20, fontWeight: 700, lineHeight: 1, color: yellow ? "var(--yellow)" : undefined, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v}</span>
      <span className="lbl" style={{ fontSize: 11 }}>{l}</span>
    </div>
  );
}
