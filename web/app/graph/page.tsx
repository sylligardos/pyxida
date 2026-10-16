import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Footer";
import { GraphView } from "@/components/GraphView";
import { ToyNote } from "@/components/ToyNote";
import { href, loadLandscape, loadSummary, stateFrom } from "@/lib/data";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const state = stateFrom(await searchParams);
  const [summary, landscape] = await Promise.all([loadSummary(state), loadLandscape(state)]);
  return (
    <>
      <TopBar state={state} current="/graph" />
      <main style={{ paddingTop: 32 }}>
        <ToyNote benchmark={state.benchmark} />
        {summary && landscape ? (
          <GraphView key={`${state.benchmark}/${state.kind}`} summary={summary} landscape={landscape} state={state} />
        ) : (
          <section className="wrap" style={{ paddingBottom: 72 }}>
            <p className="panel notice">No data exported for this benchmark yet. Run <code className="inline">scripts/export_web.py</code> then <code className="inline">scripts/export_graph.py</code>.</p>
          </section>
        )}
      </main>
      <Footer takeaway="Series cluster by which detectors win on them, not by where they came from.">
        <Link href={href("/workbench", state)} className="btn btn-outline">Open the Workbench</Link>
      </Footer>
    </>
  );
}
