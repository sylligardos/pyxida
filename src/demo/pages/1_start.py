"""Start: what this is, who made it, what is in it, and what you can do with it.

The page is an invitation, not an audit. The benchmark's defects are real
findings and they belong in the paper, not on the first thing a visitor sees.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import (
    ONE_SENTENCE,
    REPO_DATA,
    REPO_PARSER,
    REPO_TEMPLATE,
    TAGLINE,
    TITLE,
    WORKBENCH_SAMPLE_KEY,
    BENCHMARK_NOTES,
    benchmark_label,
    benchmark_summary,
    KIND_LABELS,
    current_benchmark,
    current_kind,
    demo_series,
    get_parser,
    paper_author,
    plot_series_plotly,
    takeaway,
)

KIND = current_kind()
MAX_CHANNELS = 3
BENCHMARK = current_benchmark()
DEMO_SERIES = demo_series(KIND)
if DEMO_SERIES is None:
    st.title(f"🧭 {TITLE}")
    st.info(f"{benchmark_label(BENCHMARK)} has no {KIND_LABELS[KIND]} series. "
            "Switch the Series control in the sidebar.")
    st.stop()

# What the demo shows below the snippet is what the snippet produces. Kept as a
# string so the two cannot drift into a lie: the page runs these exact calls.
SNIPPET = f'''from tsbadparser import TSBADParser

parser = TSBADParser(benchmark="{BENCHMARK}", kind="{KIND}")
names, series, labels = parser.load_timeseries(
    filename=["{DEMO_SERIES}"])
parser.visualize_timeseries(series[0], anomaly_labels=labels[0], title=names[0])'''


@st.cache_data
def load_demo_series(benchmark: str, kind: str, filename: str):
    names, series, labels = get_parser(kind).load_timeseries(filename=[filename])
    return names[0], series[0], labels[0]


# ---------------------------------------------------------------------------

author = paper_author()

st.title(f"🧭 {TITLE}")
st.markdown(f"### {TAGLINE}")
st.caption(
    f"{author['name']} · {author['affiliation']} · {author['location']} · "
    f"[{author['email']}](mailto:{author['email']})"
)
st.write(ONE_SENTENCE)

st.divider()

# --- The benchmark at a glance -------------------------------------------
summary = benchmark_summary(KIND)

st.subheader(f"{benchmark_label(BENCHMARK)}, {KIND_LABELS[KIND]}")
columns = st.columns(5)
columns[0].metric("Series", f"{summary['n_series']:,}")
columns[1].metric("Datasets", summary["n_datasets"])
if "n_anomalies" in summary:
    columns[2].metric("Anomalies", f"{summary['n_anomalies']:,}")
else:
    columns[2].metric("Scored series", f"{summary.get('n_scored_series', 0):,}")
columns[3].metric("Detectors", summary["n_detectors"])
columns[4].metric("Points", f"{summary.get('n_points', 0) / 1e6:.1f}M")
if BENCHMARK == "tsb-ad" and KIND == "uni":
    st.caption(
        f"Every detector scored every series: "
        f"{summary['n_detectors'] * summary['n_series']:,} score files, "
        f"{summary.get('n_entity_types', 0)} entity types, "
        f"from [TSB-AD]({REPO_DATA}). Counts are read from the data, not typed in."
    )
else:
    st.caption(
        f"{BENCHMARK_NOTES.get(BENCHMARK, '')} Same format as TSB-AD, so every "
        "page reads it the same way. Counts are read from the data, not typed in."
        if BENCHMARK != "tsb-ad" else
        f"Every detector scored every series, from [TSB-AD]({REPO_DATA}). "
        "Counts are read from the data, not typed in."
    )

st.divider()

# --- What you can do with it ---------------------------------------------
# PLACEHOLDER. The layout slot is settled; the words are written later.
st.subheader("What you can do with it")
st.markdown(
    """
    - _(placeholder)_ Load any series, its labels, and 32 detectors' scores in one call.
    - _(placeholder)_ Compare detectors on a shared, correct evaluation.
    - _(placeholder)_ Find the datasets and anomaly types that are still open.
    - _(placeholder)_ Start a new project from a template that already runs.
    """
)

st.divider()

# --- The parser in six lines ---------------------------------------------
st.subheader("The parser, in six lines")

left, right = st.columns([2, 3])
with left:
    st.code(SNIPPET, language="python")
    st.markdown(
        f"[Parser repo]({REPO_PARSER}) · [Project template]({REPO_TEMPLATE})"
    )
with right:
    name, series, labels = load_demo_series(BENCHMARK, KIND, DEMO_SERIES)
    # A multivariate series can have 100+ channels; the first few make the point.
    if series.ndim == 2 and series.shape[1] > MAX_CHANNELS:
        series = series[:, :MAX_CHANNELS]
        st.caption(f"First {MAX_CHANNELS} channels shown.")
    st.plotly_chart(
        plot_series_plotly(series, labels, title=name),
        width='stretch',
    )
    st.caption(
        "The plot on the right is what those six lines produce. "
        "`visualize_timeseries` draws it with matplotlib; the demo re-renders "
        "it interactively. Anomalies in red."
    )

st.divider()

takeaway("Everything here is one pip install away.")

left, right = st.columns(2)
if left.button("🔬 Sample a series", width='stretch'):
    st.session_state[WORKBENCH_SAMPLE_KEY] = True
    st.switch_page("pages/4_workbench.py")
if right.button("🚀 Get started", width='stretch'):
    st.switch_page("pages/5_get_started.py")
