import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Footer";
import { RankingView } from "@/components/RankingView";
import { href, loadLandscape, stateFrom } from "@/lib/data";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const state = stateFrom(await searchParams);
  const data = await loadLandscape(state);
  return (
    <>
      <TopBar state={state} current="/rankings" />
      <main style={{ paddingTop: 32 }}>
        {data ? (
          <RankingView data={data} state={state} />
        ) : (
          <section className="wrap" style={{ paddingBottom: 72 }}>
            <p className="panel notice">No detector metrics exported for this benchmark yet. Run <code className="inline">scripts/export_web.py</code> first.</p>
          </section>
        )}
      </main>
      <Footer takeaway="The leaderboard rewards detectors that are good where everyone is good. The series that matter are the ones only one detector gets, and the ones nobody does.">
        <Link href={href("/redundancy", state)} className="btn btn-primary">See why: Redundancy</Link>
      </Footer>
    </>
  );
}
