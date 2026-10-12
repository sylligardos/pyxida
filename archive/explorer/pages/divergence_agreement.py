"""Divergence study, step 2: which detector pairs agree?

Reads the step-1 output (Spearman correlation of every detector pair on every
series) and answers one question: which pairs behave equivalently.

Where they *dis*agree is the next page's job, deliberately not this one's.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.utils import get_kind, cached_pair_agreement, window_selector

st.title("Detector Agreement")

ALL_DATASETS = "All datasets"

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
with st.sidebar:
    kind = get_kind()

agreement = cached_pair_agreement(kind)

if agreement.empty:
    st.warning(
        f"No agreement table for kind = `{kind}`.\n\n"
        f"Build it first:\n\n"
        f"```bash\npython src/divergence/step1_agreement.py --kind {kind}\n```"
    )
    st.stop()

datasets = sorted(agreement.dataset.unique())

with st.sidebar:
    dataset = st.selectbox("Dataset", [ALL_DATASETS] + datasets)
    window = window_selector()
    threshold = st.slider(
        "Equivalent if median agreement >", 0.0, 1.0, 0.90, 0.01,
        help="Drag to see how many pairs survive.",
    )

col = f"w{window}"
if col not in agreement.columns:
    st.warning(f"This agreement table has no `{col}` column. Rebuild step 1.")
    st.stop()
agreement = agreement.assign(spearman=agreement[col])

scoped = agreement if dataset == ALL_DATASETS else agreement[agreement.dataset == dataset]

detectors = sorted(set(scoped.detector_a) | set(scoped.detector_b))
n_series = scoped.filename.nunique()
defined = scoped.spearman.dropna()

# ---------------------------------------------------------------------------
# 1. The distribution
# ---------------------------------------------------------------------------
st.subheader("How often do two detectors agree?")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Series", f"{n_series:,}")
c2.metric("Detectors", len(detectors))
c3.metric("Correlations", f"{len(defined):,}")
c4.metric("Above 0.9", f"{(defined > 0.9).mean() * 100:.2f}%")

fig_hist = go.Figure(
    go.Histogram(x=defined, nbinsx=120, marker=dict(color="#4C78A8"), showlegend=False)
)
fig_hist.add_vline(
    x=threshold, line=dict(color="#e07b00", width=2, dash="dash"),
    annotation_text=f"threshold {threshold:.2f}", annotation_position="top",
)
fig_hist.update_layout(
    xaxis_title=("Agreement between two detectors on one series "
                 f"({'pointwise' if window == 1 else f'tolerance +/- {window} pts'})"),
    yaxis_title="Count",
    height=320,
    margin=dict(t=30, b=50),
    font=dict(size=13),
    bargap=0.02,
)
st.plotly_chart(fig_hist, width="stretch")

st.caption(
    f"Median agreement is {defined.median():.3f}. Scores are compared as ranks "
    f"because detector score scales are not comparable, and with a tolerance "
    f"window because a detector firing a few points early is not a disagreement "
    f"-- the same reason VUS-PR exists."
)

# ---------------------------------------------------------------------------
# 2. The heatmap
# ---------------------------------------------------------------------------
st.subheader("Agreement between every pair")

pair_median = scoped.groupby(["detector_a", "detector_b"])["spearman"].median()

index = {det: i for i, det in enumerate(detectors)}
values = np.full((len(detectors), len(detectors)), np.nan)
for (det_a, det_b), value in pair_median.items():
    i, j = index[det_a], index[det_b]
    values[i, j] = value
    values[j, i] = value
np.fill_diagonal(values, 1.0)
# The matrix is symmetric, so blank the upper triangle and show each pair once.
values[np.triu_indices(len(detectors), k=1)] = np.nan
matrix = pd.DataFrame(values, index=detectors, columns=detectors)

fig_map = go.Figure(
    go.Heatmap(
        z=matrix.values,
        x=matrix.columns.tolist(),
        y=matrix.index.tolist(),
        colorscale="RdBu_r",
        zmid=0, zmin=-1, zmax=1,
        colorbar=dict(title="median<br>Spearman"),
        hovertemplate="%{y} vs %{x}<br>median Spearman = %{z:.3f}<extra></extra>",
    )
)
fig_map.update_layout(
    title=f"Median Spearman per detector pair — {dataset}",
    height=760,
    margin=dict(l=150, b=150, t=60),
    xaxis=dict(tickangle=70),
    yaxis=dict(autorange="reversed"),
    font=dict(size=12),
)
st.plotly_chart(fig_map, width="stretch")

st.caption(
    "Almost the whole map is neutral. Detectors sharing a score scale is not "
    "the same as detectors ranking timestamps alike."
)

# ---------------------------------------------------------------------------
# 3. The equivalent pairs
# ---------------------------------------------------------------------------
st.subheader(f"Pairs above {threshold:.2f}")

per_dataset = (
    agreement.groupby(["dataset", "detector_a", "detector_b"])["spearman"]
    .agg(median="median", n_series="count")
    .reset_index()
)
passing = per_dataset[per_dataset["median"] > threshold]
if dataset != ALL_DATASETS:
    passing = passing[passing.dataset == dataset]

if passing.empty:
    st.info(f"No pair reaches a median Spearman above {threshold:.2f}. Lower the threshold.")
else:
    if dataset == ALL_DATASETS:
        # Only the datasets where the pair actually clears the threshold, each
        # carrying its own median. A single overall number would be misleading
        # here: the pair is equivalent in those datasets, not everywhere.
        def _where(group: pd.DataFrame) -> str:
            group = group.sort_values("median", ascending=False)
            return ", ".join(
                f"{row.dataset} ({row.median:.2f})" for row in group.itertuples()
            )

        table = (
            passing.groupby(["detector_a", "detector_b"])
            .apply(_where, include_groups=False)
            .reset_index(name="datasets")
        )
        table["n"] = passing.groupby(["detector_a", "detector_b"]).size().values
        table = table.sort_values("n", ascending=False)
        table["pair"] = table.detector_a + "  /  " + table.detector_b
        st.dataframe(
            table[["pair", "datasets"]],
            width="stretch", hide_index=True,
            column_config={
                "pair": st.column_config.TextColumn(
                    "Pair",
                    help="The two detectors being compared. Scores are turned into "
                         "ranks first, because detector score scales are not comparable."),
                "datasets": st.column_config.TextColumn(
                    "Equivalent in (median Spearman)",
                    help="Every dataset where this pair's median agreement clears the "
                         "threshold, with that dataset's median in brackets. A pair "
                         "can behave alike on one dataset and not another, so only "
                         "the datasets that qualify are listed."),
            },
        )
        st.caption(
            f"{len(table)} distinct pairs of {len(detectors) * (len(detectors) - 1) // 2} "
            f"possible are equivalent somewhere, across {passing.dataset.nunique()} datasets."
        )
    else:
        table = passing.sort_values("median", ascending=False).copy()
        table["pair"] = table.detector_a + "  /  " + table.detector_b
        st.dataframe(
            table[["pair", "median", "n_series"]],
            width="stretch", hide_index=True,
            column_config={
                "pair": st.column_config.TextColumn(
                    "Pair",
                    help="The two detectors being compared. Scores are turned into "
                         "ranks first, because detector score scales are not comparable."),
                "median": st.column_config.NumberColumn(
                    "Median Spearman", format="%.3f",
                    help="Median rank correlation between the two detectors across "
                         "this dataset's series. 1.0 = they rank every timestamp "
                         "identically, 0 = unrelated, negative = they disagree."),
                "n_series": st.column_config.NumberColumn(
                    "Series", help="How many series the pair was compared on."),
            },
        )
        st.caption(
            f"{len(table)} pairs of {len(detectors) * (len(detectors) - 1) // 2} possible "
            f"are equivalent on {dataset}."
        )
