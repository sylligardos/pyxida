"""Across benchmarks: does the detector you would pick depend on the benchmark?

Same detectors, same metric, different benchmarks. Everything here is read from
the metric files every benchmark has in the common format, so it works for any
benchmark added later. Only detectors that appear under the same name in at
least two benchmarks are compared -- the same name means the same TSB-AD
implementation and hyperparameters, except where a benchmark shipped its own
scores (TSB-UAD).

This page ignores the sidebar's benchmark choice: it is the one page about all
of them at once.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import (
    BENCHMARK_LABELS,
    BENCHMARK_NOTES,
    TSBAD_VUS_BUFFERS,
    TSBADParser,
    _metrics,
    _parser,
    benchmark_label,
    page_header,
    takeaway,
)

page_header(
    "⚖️ Across benchmarks",
    "Does the detector you would pick depend on the benchmark you test it on?",
)

available = TSBADParser.list_benchmarks()
ordered = [b for b in BENCHMARK_LABELS if b in available] + \
          [b for b in available if b not in BENCHMARK_LABELS]

with st.sidebar:
    kind = st.radio("Series", ["uni", "multi"], horizontal=True, key="xb_kind",
                    format_func=lambda k: "univariate" if k == "uni" else "multivariate")
    buffer = st.select_slider("VUS buffer (L)", options=TSBAD_VUS_BUFFERS, value=128,
                              key="xb_buffer")
    chosen = st.multiselect("Benchmarks", ordered, default=ordered,
                            format_func=benchmark_label, key="xb_benchmarks")

column = f"VUS-PR (L: {buffer})"


@st.cache_data(show_spinner="Reading every benchmark's metrics ...")
def per_series(benchmarks: tuple, kind: str, column: str) -> pd.DataFrame:
    """One row per (benchmark, series, detector) with the chosen VUS."""
    frames = []
    for bench in benchmarks:
        parser = _parser(bench, kind)
        metrics = _metrics(bench, kind)
        if metrics.empty or column not in metrics.columns:
            continue
        metrics = metrics[metrics["Model Name"].isin(set(parser.get_detectors()))]
        datasets = parser.meta.set_index("filename").dataset
        frames.append(pd.DataFrame({
            "benchmark": bench,
            "filename": metrics["File Name"].to_numpy(),
            "dataset": metrics["File Name"].map(datasets).to_numpy(),
            "detector": metrics["Model Name"].to_numpy(),
            "vus": metrics[column].to_numpy(),
        }))
    return pd.concat(frames, ignore_index=True).dropna(subset=["vus"]) if frames else pd.DataFrame()


table = per_series(tuple(chosen), kind, column)
if table.empty:
    st.info("None of the chosen benchmarks has metrics for these series.")
    st.stop()

# Detectors present, by name, in at least two benchmarks.
spread = table.groupby("detector").benchmark.nunique()
shared = sorted(spread[spread >= 2].index)
with st.sidebar:
    shared_only = st.checkbox(
        "Only datasets every benchmark has", value=False, key="xb_shared_datasets",
        help="Datasets matched by name (NAB, MGAB, ...). Removes the effect of "
             "each benchmark covering different data, leaving how it was "
             "curated and labelled.")

if shared_only:
    per_bench = table.groupby("benchmark").dataset.apply(set)
    common = set.intersection(*per_bench) if len(per_bench) else set()
    table = table[table.dataset.isin(common)]
    st.caption(f"Datasets in every benchmark shown: {', '.join(sorted(common)) or 'none'}.")

table = table[table.detector.isin(shared)]
if table.empty or not shared:
    st.info("No detector appears under the same name in two of the chosen benchmarks.")
    st.stop()

# Every dataset counts once, as on the other pages: otherwise a benchmark's
# biggest dataset decides its ranking.
per_dataset = table.groupby(["benchmark", "dataset", "detector"]).vus.mean()
means = per_dataset.groupby(["benchmark", "detector"]).mean().unstack("benchmark")
means = means[[b for b in chosen if b in means.columns]]
series_count = table.groupby("benchmark").filename.nunique()
means.columns = [f"{benchmark_label(b)} ({series_count[b]})" for b in means.columns]
ranks = means.rank(ascending=False)

# ---------------------------------------------------------------------------
# Mean VUS and rank per benchmark
# ---------------------------------------------------------------------------

left, right = st.columns([3, 2])
with left:
    st.subheader("Mean VUS-PR per detector")
    figure = go.Figure(go.Heatmap(
        z=means.to_numpy(), x=list(means.columns), y=list(means.index),
        text=[[("" if np.isnan(v) else f"{v:.2f}  (#{int(r)})") for v, r in zip(vr, rr)]
              for vr, rr in zip(means.to_numpy(), ranks.to_numpy())],
        texttemplate="%{text}", colorscale="Blues", zmin=0, zmax=1,
        colorbar=dict(title="VUS"),
        hovertemplate="%{y} on %{x}: %{z:.3f}<extra></extra>",
    ))
    figure.update_layout(height=60 + 38 * len(means), margin=dict(l=10, r=10, t=10, b=10),
                         font=dict(size=13), yaxis=dict(autorange="reversed"))
    st.plotly_chart(figure, width="stretch")
    st.caption(
        f"VUS-PR at L={buffer}, averaged per dataset and then across datasets. "
        "(#n) is the detector's rank on that benchmark. The number in each column "
        "header is how many series have scores. Blank: the detector was not run there."
    )

with right:
    st.subheader("Do the rankings agree?")
    rho = ranks.corr(method="spearman", min_periods=3)
    figure = go.Figure(go.Heatmap(
        z=rho.to_numpy(), x=list(rho.columns), y=list(rho.index),
        text=np.vectorize(lambda v: "" if np.isnan(v) else f"{v:+.2f}")(rho.to_numpy()),
        texttemplate="%{text}", colorscale="RdBu", zmin=-1, zmax=1,
        colorbar=dict(title="rho"),
        hovertemplate="%{x} vs %{y}: %{z:+.2f}<extra></extra>",
    ))
    figure.update_layout(height=60 + 60 * len(rho), margin=dict(l=10, r=10, t=10, b=10),
                         font=dict(size=13), yaxis=dict(autorange="reversed"))
    st.plotly_chart(figure, width="stretch")
    st.caption(
        "Spearman correlation between two benchmarks' rankings, over the detectors "
        "both ran (at least 3). +1: same order. -1: reversed."
    )

# ---------------------------------------------------------------------------
# Where the winner changes
# ---------------------------------------------------------------------------

winners = means.idxmax()
st.subheader("Who wins where")
cols = st.columns(len(winners))
for col, (bench, det) in zip(cols, winners.items()):
    col.metric(bench, det, help=f"Mean VUS-PR {means.loc[det, bench]:.3f}")

with st.expander("What is behind each benchmark"):
    for bench in chosen:
        st.markdown(f"**{benchmark_label(bench)}.** {BENCHMARK_NOTES.get(bench, '')}")
    st.markdown(
        "TSB-AD's metrics were computed with an earlier version of the VUS code "
        "than the other benchmarks'; values can differ slightly for identical "
        "scores. TSB-UAD's detectors are its own shipped implementations: only "
        "names that match are compared."
    )

n_winners = winners.nunique()
takeaway(
    "The leaderboard depends on the benchmark. Check a detector on a second one "
    "before you believe its rank."
    if n_winners > 1 else
    "Here the same detector wins on every benchmark shown -- check whether that "
    "holds at other buffers before relying on it."
)
