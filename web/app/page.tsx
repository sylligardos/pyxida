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
const TEMPLATE = "https://github.com/sylligardos/tsad-template";
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
          <p className="eyebrow">ICDE 2027 demo</p>
          <h1>
            See what is still <span style={{ color: "var(--human)" }}>unsolved</span> in time series anomaly detection, and who is pushing it.
          </h1>
          <p className="lede">
            Jump-start your work on a correct foundation. The parser gives you the data and the evaluation,
            the template gives you the project, and this demo tells you what to run and where to look.
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
          <h2>What you can do with it</h2>
          <div className="cards">
            <article className="panel card">
              <div className="top"><span>01</span><span className="diamond diamond-human-hollow" aria-hidden="true" /></div>
              <h3>Explore</h3>
              <p>Every series scored by the best detector on it. Which datasets and anomaly types are still open, and which the top five already solve.</p>
              <Link href={href("/explore", state)}>Open the landscape →</Link>
            </article>
            <article className="panel card">
              <div className="top"><span>02</span><span className="diamond diamond-det" aria-hidden="true" /></div>
              <h3>Workbench</h3>
              <p>One series at a time, its labels, and what the detectors did on it, aligned in time. Every click on a series anywhere lands here.</p>
              <Link href={href("/workbench", state, { sample: "1" })}>Sample a series →</Link>
            </article>
            <article className="panel card">
              <div className="top">
                <span>03</span>
                <span style={{ display: "inline-flex", gap: 8 }} aria-hidden="true">
                  <span className="diamond diamond-human" /><span className="diamond diamond-det" />
                </span>
              </div>
              <h3 className="needle">Needle</h3>
              <p>Mark the anomaly before the detectors do. A real series, forty seconds, you against a team of detectors. Scores on the booth monitor.</p>
              <Link href={href("/game", state)} style={{ color: "var(--human-soft)" }}>Play a round →</Link>
            </article>
          </div>
        </section>

        <section className="wrap section">
          <h2>The parser, in six lines</h2>
          <div className="parser">
            <div className="code-col">
              <pre className="code">
                <span className="kw">from</span> pyxida <span className="kw">import</span> TSBADParser{"\n\n"}
                parser = TSBADParser(benchmark=<span className="str">&quot;{state.benchmark}&quot;</span>, kind=<span className="str">&quot;{state.kind}&quot;</span>){"\n"}
                names, series, labels = parser.load_timeseries({"\n"}
                {"    "}filename=[<span className="str">&quot;{summary?.demo_series ?? "<series file>"}&quot;</span>]){"\n"}
                parser.visualize_timeseries(series[0], anomaly_labels=labels[0],{"\n"}
                {"    "}title=names[0])
              </pre>
              <p className="links">
                <a href={REPO}>Pyxida repo</a> · <a href={TEMPLATE}>Project template</a> · <a href={TSB_AD}>TSB-AD</a>
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
              <figcaption>The plot is what those six lines produce. Labeled anomalies in yellow, the same yellow as in the game.</figcaption>
            </figure>
          </div>
        </section>

        <section className="wrap section" id="your-data">
          <h2>Run it on your data</h2>
          <p className="soft" style={{ maxWidth: "60em", marginTop: -8 }}>
            Any folder in the format below opens in every page of this demo. TSB-AD drops in unchanged; the repo has converters for TSB-UAD, TAB, TimeEval and mTSBench.
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
                <span>Run the detectors and compute the metrics. Both scripts take the folder and write <code className="inline">scores/</code> and <code className="inline">metrics/</code> next to it.</span>
                <pre className="code">{`python scripts/run_detectors.py <benchmark>
python scripts/compute_metrics.py <benchmark>`}</pre>
              </div>
            </article>
            <article className="panel step">
              <span className="num">3</span>
              <div className="body">
                <b>Open</b>
                <span>Export the folder for the demo, then pick it in the menu at the top. The Workbench shows every series with a score; the Landscape needs the metrics.</span>
                <pre className="code">{`python scripts/export_web.py --benchmark <benchmark>`}</pre>
              </div>
            </article>
          </div>
        </section>
      </main>

      <Footer takeaway="Everything here is one pip install away.">
        <Link href={href("/workbench", state, { sample: "1" })} className="btn btn-primary">Sample a series</Link>
        <Link href={href("/game", state)} className="btn btn-outline">Play Needle</Link>
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
