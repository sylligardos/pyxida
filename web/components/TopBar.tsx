import Link from "next/link";
import { BENCHMARKS, KIND_LABEL, KINDS, State, href, hasKind, YOUR_DATA } from "@/lib/data";
import { BenchmarkSelect } from "./BenchmarkSelect";
import { HelpButton } from "./HelpButton";

// Three pages. Needle is the bonus: a pill at the right, not a page.
const PAGES = [
  { path: "/", label: "Intro" },
  { path: "/graph", label: "Graph" },
  { path: "/explore", label: "Explore" },
  { path: "/workbench", label: "Workbench" },
];

const Chevron = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    <polyline points="2,4 6,8 10,4" />
  </svg>
);

export async function TopBar({ state, current }: { state: State; current: string }) {
  const kinds = await Promise.all(KINDS.map(async (k) => [k, await hasKind(state.benchmark, k)] as const));
  return (
    <header className="topbar">
      <div className="wrap">
        <Link href={href("/", state)} className="wordmark">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FFE14D" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <polygon points="16.2,7.8 14.1,14.1 7.8,16.2 9.9,9.9" fill="#FFE14D" />
          </svg>
          <span>Pyxida</span>
        </Link>
        <nav className="nav" aria-label="Pages">
          {PAGES.map((p) => (
            <Link key={p.path} href={href(p.path, state)} aria-current={p.path === current ? "page" : undefined}>
              {p.label}
            </Link>
          ))}
        </nav>
        <div className="controls">
          <div className="select">
            <BenchmarkSelect value={state.benchmark} kind={state.kind} options={BENCHMARKS} yours={YOUR_DATA} />
            <Chevron />
          </div>
          <div className="seg" role="group" aria-label="Series kind">
            {kinds.map(([k, ok]) => (
              <Link
                key={k}
                href={href(current, { ...state, kind: k })}
                aria-current={k === state.kind ? "true" : undefined}
                aria-disabled={ok ? undefined : "true"}
                title={ok ? undefined : `No ${KIND_LABEL[k].toLowerCase()} series in this benchmark`}
              >
                {KIND_LABEL[k]}
              </Link>
            ))}
          </div>
          <Link href={href("/game", state)} className="pill-needle" aria-current={current === "/game" ? "page" : undefined}>Needle</Link>
          <HelpButton page={current} />
        </div>
      </div>
    </header>
  );
}
