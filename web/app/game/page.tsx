import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Footer";
import { href, stateFrom } from "@/lib/data";

// The attract series behind the hero: synthetic, seeded, the same every time.
function attract(): string {
  const n = 300, w = 800, h = 220;
  let s = 4242;
  const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  const ys: number[] = [];
  for (let i = 0; i < n; i++) {
    let v = Math.sin(i / 7) * 0.6 + Math.sin(i / 29) * 0.3 + (rnd() - 0.5) * 0.15;
    if (i >= 189 && i < 210) v = 0.2 + Math.sin(i / 2.2) * 0.9;
    ys.push(v);
  }
  const mn = Math.min(...ys), mx = Math.max(...ys);
  return ys.map((v, i) => `${((i / (n - 1)) * w).toFixed(1)},${(10 + (1 - (v - mn) / (mx - mn)) * (h - 20)).toFixed(1)}`).join(" ");
}

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const state = stateFrom(await searchParams);
  return (
    <>
      <TopBar state={state} current="/game" />
      <main style={{ paddingTop: 32 }}>
        <section className="wrap" style={{ paddingBottom: 72, display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="cabinet">
            <svg viewBox="0 0 800 220" preserveAspectRatio="none" className="attract" aria-hidden="true">
              <polyline points={attract()} fill="none" stroke="#22D3EE" strokeWidth="1.8" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            </svg>
            <div className="attract-q" aria-hidden="true"><span>?</span></div>
            <div className="cab-top">
              <span>You <span style={{ color: "var(--human)" }}>◆</span> vs <span style={{ color: "var(--det)" }}>◆</span> detectors</span>
              <span>Booth monitor · ICDE 2027</span>
            </div>
            <h2 className="needle-hero">Pyxida</h2>
            <p className="cab-text">A real series from the benchmark. Forty seconds. Mark where the anomaly is, then see the label and what the detectors flagged.</p>
            <div className="cab-play">
              <a href="/play" target="_blank" rel="noopener" className="btn btn-primary" style={{ height: 60, padding: "0 32px", fontSize: 18, fontWeight: 700 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><polygon points="6,4 20,12 6,20" /></svg>
                Play
              </a>
              <span className="muted" style={{ fontSize: 13 }}>Opens in a new tab, with sound. About three minutes a round.</span>
            </div>
          </div>

          <div className="steps">
            <Step n="1" color="var(--human)" title="Mark">Drag over the series, up to five ranges. Or say there is nothing here.</Step>
            <Step n="2" color="var(--yellow)" title="Reveal">The labeled anomaly in yellow, your marks in magenta, the detectors&apos; flags in cyan.</Step>
            <Step n="3" color="var(--det)" title="Score">A hit is +1, a false alarm is −1, for you and for the detectors alike. Best of the series wins.</Step>
          </div>
        </section>
      </main>
      <Footer takeaway="Play a round, then open the series you lost in the Workbench.">
        <Link href={href("/workbench", state)} className="btn btn-outline">Back to the Workbench</Link>
      </Footer>
    </>
  );
}

function Step({ n, color, title, children }: { n: string; color: string; title: string; children: React.ReactNode }) {
  return (
    <article className="panel step" style={{ flex: "1 1 220px" }}>
      <span className="num" style={{ color }}>{n}</span>
      <div className="body"><b>{title}</b><span>{children}</span></div>
    </article>
  );
}
