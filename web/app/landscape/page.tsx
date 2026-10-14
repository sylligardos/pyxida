import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Footer";
import { LandscapeView } from "@/components/LandscapeView";
import { href, loadLandscape, stateFrom } from "@/lib/data";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const state = stateFrom(await searchParams);
  const data = await loadLandscape(state);
  return (
    <>
      <TopBar state={state} current="/landscape" />
      <main style={{ paddingTop: 32 }}>
        {data ? (
          <LandscapeView data={data} state={state} />
        ) : (
          <section className="wrap" style={{ paddingBottom: 72 }}>
            <p className="panel notice">No detector metrics exported for this benchmark yet. Run <code className="inline">scripts/export_web.py</code> first.</p>
          </section>
        )}
      </main>
      <Footer takeaway="Stop tuning on the solved datasets. The open problems are on the left.">
        <Link href={href("/workbench", state, { hardest: "1" })} className="btn btn-primary">Open the hardest series</Link>
      </Footer>
    </>
  );
}
