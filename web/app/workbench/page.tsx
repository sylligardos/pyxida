import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Footer";
import { WorkbenchView } from "@/components/WorkbenchView";
import { href, loadLandscape, loadSummary, stateFrom } from "@/lib/data";

const SAMPLE_MAX_POINTS = 300_000;

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const state = stateFrom(params);
  const [summary, landscape] = await Promise.all([loadSummary(state), loadLandscape(state)]);

  // Which series to open: the one in the link, a random one, the hardest
  // one, or the demo series.
  let initial = typeof params.s === "string" && summary?.series.some((x) => x.file === params.s) ? params.s : null;
  if (!initial && summary && params.sample) {
    const pool = summary.series.filter((x) => (x.n ?? 0) <= SAMPLE_MAX_POINTS);
    initial = (pool.length ? pool : summary.series)[Math.floor(Math.random() * (pool.length || summary.series.length))]?.file ?? null;
  }
  if (!initial && landscape && params.hardest) {
    let best: { file: string; v: number } | null = null;
    for (const r of landscape.rows) {
      const v = Math.max(...r.vus.filter((x): x is number => x !== null));
      if (isFinite(v) && (!best || v < best.v)) best = { file: r.file, v };
    }
    initial = best?.file ?? null;
  }
  // Whether the link asked for a particular series; otherwise the Workbench
  // reopens the one it had in this tab.
  const explicit = initial !== null || Boolean(params.sample) || Boolean(params.hardest);
  if (!initial && summary) initial = summary.demo_series ?? summary.series[0]?.file ?? null;

  return (
    <>
      <TopBar state={state} current="/workbench" />
      <main style={{ paddingTop: 32 }}>
        {summary && initial ? (
          <WorkbenchView key={`${state.benchmark}/${state.kind}`} summary={summary} landscape={landscape} state={state} initial={initial} explicit={explicit}
            pin={typeof params.pin === "string" ? params.pin : null} top={typeof params.top === "string" ? params.top : null} avg={typeof params.avg === "string" ? params.avg : null}
            metric={params.m === "aucpr" || params.m === "vus" ? params.m : null} />
        ) : (
          <section className="wrap" style={{ paddingBottom: 72 }}>
            <p className="panel notice">No series exported for this benchmark yet. Run <code className="inline">scripts/export_web.py --all</code> first.</p>
          </section>
        )}
      </main>
      <Footer takeaway="Look at your data before you trust a number.">
        <Link href={href("/game", state)} className="btn btn-outline">Try this one yourself</Link>
      </Footer>
    </>
  );
}
