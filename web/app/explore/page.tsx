import { TopBar } from "@/components/TopBar";
import { ExploreView, type ExploreTab } from "@/components/ExploreView";
import { loadLandscape, loadRedundancy, stateFrom } from "@/lib/data";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const state = stateFrom(params);
  const [landscape, redundancy] = await Promise.all([loadLandscape(state), loadRedundancy(state)]);
  const v = params.v;
  const initial: ExploreTab | null = v === "landscape" || v === "rankings" || v === "redundancy" ? v : null;
  return (
    <>
      <TopBar state={state} current="/explore" />
      <ExploreView key={`${state.benchmark}/${state.kind}`} landscape={landscape} redundancy={redundancy} state={state} initial={initial} />
    </>
  );
}
