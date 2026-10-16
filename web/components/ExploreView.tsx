"use client";

// Explore: the benchmark from three views, one at a time. Landscape (every
// series by its best detector), Rankings (who solves what, who solves
// nothing) and Redundancy (which detectors are the same detector twice).
// The view survives navigation within the tab; a link may name it (?v=).

import { useEffect } from "react";
import type { Landscape, Redundancy, State } from "@/lib/model";
import { useSessionState } from "@/lib/session";
import { LandscapeView } from "./LandscapeView";
import { RankingView } from "./RankingView";
import { RedundancyView } from "./RedundancyView";
import { Footer } from "./Footer";

export type ExploreTab = "landscape" | "rankings" | "redundancy";
export const EXPLORE_TABS: { id: ExploreTab; label: string; takeaway: string }[] = [
  { id: "landscape", label: "Landscape", takeaway: "Stop tuning on the solved datasets. The open problems are on the left." },
  { id: "rankings", label: "Rankings", takeaway: "The leaderboard rewards detectors that are good where everyone is good. The series that matter are the ones only one detector gets, and the ones nobody does." },
  { id: "redundancy", label: "Redundancy", takeaway: "A leaderboard tells you who is best. It does not tell you that your top two are the same detector twice." },
];

export function ExploreView({ landscape, redundancy, state, initial }: {
  landscape: Landscape | null; redundancy: Redundancy | null; state: State; initial: ExploreTab | null;
}) {
  const [view, setView] = useSessionState<ExploreTab>("explore.view", initial ?? "landscape", () => initial === null);

  // The URL follows the view, so a link to Explore is a link to a view.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    q.set("v", view);
    window.history.replaceState(null, "", `${window.location.pathname}?${q}`);
  }, [view]);

  const tab = EXPLORE_TABS.find((t) => t.id === view) ?? EXPLORE_TABS[0];
  return (
    <>
      <main style={{ paddingTop: 32 }}>
        <section className="wrap" style={{ paddingBottom: 24 }}>
          <div className="seg tall" role="tablist" aria-label="View" style={{ display: "inline-flex" }}>
            {EXPLORE_TABS.map((t) => (
              <button key={t.id} type="button" role="tab" aria-selected={t.id === view} aria-pressed={t.id === view} onClick={() => setView(t.id)}>{t.label}</button>
            ))}
          </div>
        </section>
        {view === "landscape" && (landscape
          ? <LandscapeView data={landscape} state={state} />
          : <Notice>No detector metrics exported for this benchmark yet. Run <code className="inline">scripts/export_web.py</code> first.</Notice>)}
        {view === "rankings" && (landscape
          ? <RankingView data={landscape} state={state} />
          : <Notice>No detector metrics exported for this benchmark yet. Run <code className="inline">scripts/export_web.py</code> first.</Notice>)}
        {view === "redundancy" && (redundancy
          ? <RedundancyView data={redundancy} state={state} />
          : <Notice>This view reads the exhaustive search over every pair and triplet of detectors, which exists for TSB-AD univariate only. Switch to TSB-AD, univariate, to see it.</Notice>)}
      </main>
      <Footer takeaway={tab.takeaway} />
    </>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <section className="wrap" style={{ paddingBottom: 72 }}>
      <p className="panel notice">{children}</p>
    </section>
  );
}
