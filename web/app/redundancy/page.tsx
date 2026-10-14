import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Footer";
import { RedundancyView } from "@/components/RedundancyView";
import { href, loadRedundancy, stateFrom } from "@/lib/data";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const state = stateFrom(await searchParams);
  const data = await loadRedundancy(state);
  return (
    <>
      <TopBar state={state} current="/redundancy" />
      <main style={{ paddingTop: 32 }}>
        {data ? (
          <RedundancyView data={data} state={state} />
        ) : (
          <section className="wrap" style={{ paddingBottom: 72 }}>
            <p className="panel notice">
              This page reads the exhaustive search over every pair and triplet of detectors,
              which exist for TSB-AD univariate only. Switch to TSB-AD, univariate, to see it.
            </p>
          </section>
        )}
      </main>
      <Footer takeaway="A leaderboard tells you who is best. It does not tell you that your top two are the same detector twice.">
        <Link href={href("/workbench", state, { hardest: "1" })} className="btn btn-primary">Open the hardest series</Link>
      </Footer>
    </>
  );
}
