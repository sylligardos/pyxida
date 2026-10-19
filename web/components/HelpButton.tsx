"use client";

// The "?" in the top bar: one popup per page with how the page works and
// where the ideas come from. The words live in lib/help.ts. On Explore the
// open view comes first, the other two fold; on Rankings the gap and floor
// are read from the page's own state so the popup never disagrees with it.

import { useCallback, useEffect, useState } from "react";
import { CITES, HELP, type HelpSection } from "@/lib/help";
import s from "./HelpButton.module.css";

const SESSION = "pyxida.session.";
function session<T>(key: string, fallback: T): T {
  try { const v = sessionStorage.getItem(SESSION + key); return v === null ? fallback : (JSON.parse(v) as T); } catch { return fallback; }
}

export function HelpButton({ page }: { page: string }) {
  const [open, setOpen] = useState(false);
  const [sections, setSections] = useState<HelpSection[]>([]);
  const [first, setFirst] = useState<string | null>(null);

  const show = useCallback(() => {
    let secs = HELP[page] ?? [];
    let lead: string | null = null;
    if (page === "/explore") {
      const view = session("explore.view", "landscape");
      lead = { landscape: "Landscape", rankings: "Rankings", redundancy: "Redundancy" }[view] ?? "Landscape";
      const gap = session("rankings.gap", 0.2), floor = session("rankings.floor", 0.2);
      secs = secs.map((sec) => sec.title !== "Rankings" ? sec : { ...sec, entries: sec.entries.map((e) =>
        e.term === "Solves" ? { ...e, text: `A detector solves a series when its score is within ${gap} of the best score on that series. That gap is the first picker.` }
          : e.term === "Nobody" ? { ...e, text: `Nobody solves a series when its best score is under ${floor}, the second picker.` } : e) });
    }
    setSections(secs); setFirst(lead); setOpen(true);
  }, [page]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!HELP[page]) return null;
  const ordered = first ? [...sections.filter((x) => x.title === first), ...sections.filter((x) => x.title !== first)] : sections;
  const used = Array.from(new Set(ordered.flatMap((sec) => sec.entries.flatMap((e) => e.cites ?? [])))).sort((a, b) => a - b);
  const title = { "/graph": "How the graph works", "/explore": "How Explore works", "/workbench": "How the workbench works", "/game": "How the game works" }[page] ?? "How this page works";

  return (
    <>
      <button type="button" className={s.btn} aria-label="How this page works" aria-expanded={open} title="How this page works" onClick={() => (open ? setOpen(false) : show())}>?</button>
      {open && (
        <div className={s.overlay} onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }} role="presentation">
          <div className={s.card} role="dialog" aria-modal="true" aria-label={title}>
            <div className={s.head}><h2>{title}</h2><button type="button" className={s.close} aria-label="Close" onClick={() => setOpen(false)}>×</button></div>
            {ordered.map((sec, i) => {
              const body = (
                <dl className={s.list}>
                  {sec.entries.map((e) => (
                    <Entry key={e.term} term={e.term} text={e.text} cites={e.cites} />
                  ))}
                </dl>
              );
              if (ordered.length > 1 && i > 0) {
                return <details key={sec.title} className={s.more}><summary>{sec.title}</summary>{body}</details>;
              }
              return <section key={sec.title} className={s.section}>{ordered.length > 1 && <h3>{sec.title}</h3>}{body}</section>;
            })}
            {used.length > 0 && (
              <div className={s.refs}>
                {used.map((n) => <p key={n}>[{n}] {CITES[n].url ? <a href={CITES[n].url} target="_blank" rel="noopener">{CITES[n].label}</a> : CITES[n].label}</p>)}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function Entry({ term, text, cites }: { term: string; text: string; cites?: number[] }) {
  return (
    <>
      <dt>{term}</dt>
      <dd>{text}{cites?.map((n) => <a key={n} className={s.cite} href={CITES[n].url ?? "#"} target="_blank" rel="noopener">[{n}]</a>)}</dd>
    </>
  );
}
