import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Footer";
import { SeriesPlot } from "@/components/SeriesPlot";
import { ToyNote } from "@/components/ToyNote";
import { KIND_LABEL, fmt, fmtM, href, loadSeries, loadSummary, stateFrom } from "@/lib/data";

const AUTHOR = {
  name: "Emmanouil Sylligardos",
  affiliation: "DI ENS, ENS, PSL Univ., CNRS, Inria",
  location: "Paris, France",
  email: "emmanouil.sylligardos@ens.fr",
};
const REPO = "https://github.com/sylligardos/pyxida";
const DATA = "https://doi.org/10.5281/zenodo.23419645";
const TSB_AD = "https://github.com/thedatumorg/TSB-AD";

export default async function Intro({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const state = stateFrom(await searchParams);
  const summary = await loadSummary(state);
  const demo = summary?.demo_series ? await loadSeries(state, summary.demo_series) : null;
  const kindLabel = KIND_LABEL[state.kind].toLowerCase();

  return (
    <>
      <TopBar state={state} current="/" />
      <main>
        <section className="wrap hero">
          <h1>
            Up close and personal with time series anomaly detection benchmarks.
          </h1>
          <p className="lede">
            A benchmark gives you one number per detector. Pyxida reads it series by series: which series are still{" "}
            <span style={{ color: "var(--human)" }}>unsolved</span>, which detectors own the hard cases, and which ones overlap.
          </p>
          <p className="author">
            {AUTHOR.name} · {AUTHOR.affiliation} · {AUTHOR.location} · <a href={`mailto:${AUTHOR.email}`}>{AUTHOR.email}</a>
          </p>
        </section>

        <ToyNote benchmark={state.benchmark} />
        {summary ? (
          <section className="wrap counts">
            <div className="row">
              <Count n={fmt(summary.n_series)} label="Series" />
              <Count n={fmt(summary.n_datasets)} label="Datasets" />
              <Count n={fmt(summary.n_anomalies)} label="Anomalies" />
              <Count n={fmt(summary.n_detectors)} label="Detectors" det />
              <Count n={fmtM(summary.n_points)} label="Points" />
            </div>
            <p className="muted" style={{ fontSize: 14 }}>
              {summary.label}, {kindLabel}. {summary.toy ? "Only the series the detectors were run on." : "Every detector scored every series."} Counts are read from the data, not typed in.
            </p>
          </section>
        ) : (
          <section className="wrap counts">
            <p className="panel notice">
              No {kindLabel} series exported for this benchmark yet. Run <code className="inline">scripts/export_web.py</code> or switch the series kind.
            </p>
          </section>
        )}

        <section className="wrap section">
          <h2>Four ways in</h2>
          <div className="cards">
            <article className="panel card">
              <div className="top"><span>01</span><span className="diamond diamond-det" aria-hidden="true" /></div>
              <h3>Graph</h3>
              <p>Every series is a dot, and two series are linked when the same detectors stand out on both. Nothing but the scores goes in, and neighbourhoods come out.</p>
              <Link href={href("/graph", state)}>Open the graph →</Link>
            </article>
            <article className="panel card">
              <div className="top"><span>02</span><span className="diamond diamond-human-hollow" aria-hidden="true" /></div>
              <h3>Explore</h3>
              <p>The landscape puts the unsolved series at the top. Rankings show how many detectors solve each series and who owns the hard ones. Redundancy shows which detectors flag the same points.</p>
              <Link href={href("/explore", state)}>Open the landscape →</Link>
            </article>
            <article className="panel card">
              <div className="top"><span>03</span><span className="diamond diamond-det" aria-hidden="true" /></div>
              <h3>Workbench</h3>
              <p>One series at a time, its labels, and what the detectors did on it, aligned in time. Keep notes, pin detectors, run one-liners against the real ones.</p>
              <Link href={href("/workbench", state, { sample: "1" })}>Sample a series →</Link>
            </article>
            <article className="panel card">
              <div className="top">
                <span>04</span>
                <span style={{ display: "inline-flex", gap: 8 }} aria-hidden="true">
                  <span className="diamond diamond-human" /><span className="diamond diamond-det" />
                </span>
              </div>
              <h3 className="needle">The game</h3>
              <p>Mark the anomaly before the best detector does. A real series, under a minute, you against the best detector for that series. Hard mode is mostly series that no detector solves.</p>
              <Link href={href("/game", state)} style={{ color: "var(--human-soft)" }}>Play a round →</Link>
            </article>
          </div>
        </section>

        <section className="wrap section">
          <h2>Why series by series</h2>
          <div className="parser">
            <div className="code-col why">
              <p>
                No detector is the best on every series. Model selection is one way to live with that: a selector looks at a series and picks the detector to run on it.
                Under model selection the pool is only as good as its best member on each series, so a detector that solves series the others miss is worth more than another generally good one.
                And a series on which every detector scores low stays unsolved whatever the selector picks.
              </p>
              <p>
                Benchmarks report averages and rankings, which say which detector is best overall and nothing about the series underneath.
                The per-series scores are there; the standard views collapse them. Pyxida opens them up.
              </p>
              <p className="links">
                <a href={REPO}>Code</a> · <a href={DATA}>Data on Zenodo</a> · <a href={TSB_AD}>TSB-AD</a>
              </p>
            </div>
            <figure className="surface">
              <div className="head">
                <span className="file">{demo?.file ?? "no series"}</span>
                <span className="key"><span className="swatch-label" aria-hidden="true" />labeled anomaly</span>
              </div>
              {demo ? (
                <SeriesPlot values={demo.values} labels={demo.labels} title={`${demo.file}, labeled anomalies in yellow`} />
              ) : (
                <p className="muted" style={{ padding: "60px 0", textAlign: "center" }}>Export a series to draw it here.</p>
              )}
              <figcaption>One series of the benchmark, labeled anomalies in yellow. The workbench shows what every detector did on it.</figcaption>
            </figure>
          </div>
        </section>

        <section className="wrap section" id="your-data">
          <h2>Run it on your data</h2>
          <p className="soft" style={{ maxWidth: "60em", marginTop: -8 }}>
            Pyxida is not tied to a benchmark. Any folder in the format below opens in every page of this demo, your own included. TSB-AD drops in unchanged; the repo has converters for TSB-UAD, TAB, TimeEval and mTSBench.
          </p>
          <div className="steps">
            <article className="panel step">
              <span className="num">1</span>
              <div className="body">
                <b>Convert</b>
                <span>One folder per benchmark, univariate under <code className="inline">uni</code>, multivariate under <code className="inline">multi</code>. A series is a CSV of value columns and a binary <code className="inline">Label</code> column.</span>
                <pre className="code">{`<benchmark>/
├── raw/uni/<file>.csv
├── scores/uni/<Detector>/<file>.npy
└── metrics/uni/<Detector>.csv`}</pre>
              </div>
            </article>
            <article className="panel step">
              <span className="num">2</span>
              <div className="body">
                <b>Score</b>
                <span>Bring your detectors&apos; scores (or run TSB-AD&apos;s with <code className="inline">scripts/run_detectors.py</code>), then compute the metrics. It writes <code className="inline">metrics/</code> next to <code className="inline">scores/</code>.</span>
                <pre className="code">{`python scripts/compute_metrics.py --benchmark <benchmark>`}</pre>
              </div>
            </article>
            <article className="panel step">
              <span className="num">3</span>
              <div className="body">
                <b>Open</b>
                <span>Export the folder for the demo, then pick it in the menu at the top. The repo&apos;s README has every step.</span>
                <pre className="code">{`python scripts/export_web.py --benchmark <benchmark> --all
python scripts/export_graph.py --benchmark <benchmark>`}</pre>
              </div>
            </article>
          </div>
        </section>
      </main>

      <Footer takeaway="Any benchmark in this format reads the same way.">
        <Link href={href("/workbench", state, { sample: "1" })} className="btn btn-primary">Sample a series</Link>
        <Link href={href("/game", state)} className="btn btn-outline">Play the game</Link>
      </Footer>
    </>
  );
}

function Count({ n, label, det }: { n: string; label: string; det?: boolean }) {
  return (
    <div className="panel count">
      <span className={`n${det ? " det" : ""}`}>{n}</span>
      <span className="lbl">{label}</span>
    </div>
  );
}
