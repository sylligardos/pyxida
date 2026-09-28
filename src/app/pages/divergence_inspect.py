"""Divergence study, step 3: where does an agreeing pair actually split?

Pick a pair that agrees on a dataset, then find the series where the agreement
does not survive a tolerance window -- those are the real disagreements, as
opposed to one detector simply firing earlier, later, or for longer.

Everything is in rank space. Detector scores are min-max normalised to [0, 1],
not z-normalised, so raw scores are not comparable between two detectors.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy.ndimage import maximum_filter1d
from scipy.stats import rankdata

from app.utils import (
    WINDOWS, DEFAULT_METRIC, VALID_METRICS, get_kind, get_parser,
    cached_pair_agreement, cached_detector_quality, attach_quality,
    extract_anomaly_segments, window_selector,
)

st.title("Where They Split")

# How much the agreement has to move before we call it something.
MOVED = 0.02


def verdict(delta: float) -> str:
    if delta < -MOVED:
        return "real disagreement"
    if delta > MOVED:
        return "timing only"
    return "they agree"


@st.cache_data(show_spinner=False)
def series_traces(kind: str, det_a: str, det_b: str, filename: str, window: int):
    """Ranks, per-point distance, and the agreement-vs-window curve for one series."""
    parser = get_parser(kind)
    kept, scores, _ = parser.load_scores(
        detectors=[det_a, det_b], filenames=[filename],
        drop_missing=True, return_filenames=True,
    )
    if not kept:
        return None
    score_matrix = scores[0]
    n_points = score_matrix.shape[1]

    rank_a = rankdata(score_matrix[0]) / n_points
    rank_b = rankdata(score_matrix[1]) / n_points
    distance = np.abs(rank_a - rank_b)
    smooth = max(11, n_points // 400)
    smoothed = np.convolve(distance, np.ones(smooth) / smooth, mode="same")

    curve = []
    for w in WINDOWS:
        pooled = (score_matrix if w <= 1
                  else maximum_filter1d(score_matrix, size=w, axis=-1, mode="nearest"))
        ranked = np.stack([rankdata(row) for row in pooled])
        if ranked[0].std() == 0 or ranked[1].std() == 0:
            curve.append(np.nan)
        else:
            curve.append(float(np.corrcoef(ranked[0], ranked[1])[0, 1]))
    return rank_a, rank_b, distance, smoothed, curve


def plot_split(timeseries, labels, rank_a, rank_b, distance, smoothed,
               det_a, det_b, title):
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True,
                        row_heights=[3, 2, 2, 2], vertical_spacing=0.03)
    x = np.arange(len(rank_a))
    series = timeseries if timeseries.ndim == 1 else timeseries[:, 0]

    fig.add_trace(go.Scattergl(x=x, y=series, mode="lines",
                               line=dict(width=1, color="#333"), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scattergl(x=x, y=rank_a, mode="lines",
                               line=dict(width=1, color="#e07b00"), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scattergl(x=x, y=rank_b, mode="lines",
                               line=dict(width=1, color="#4C78A8"), showlegend=False), row=3, col=1)
    fig.add_trace(go.Scattergl(x=x, y=distance, mode="lines",
                               line=dict(width=0.4, color="rgba(43,138,62,0.03)"),
                               showlegend=False), row=4, col=1)
    fig.add_trace(go.Scattergl(x=x, y=smoothed, mode="lines",
                               line=dict(width=1.8, color="#2b8a3e"), showlegend=False), row=4, col=1)

    if labels is not None:
        for seg_start, seg_end in extract_anomaly_segments(labels):
            for row in range(1, 5):
                fig.add_vrect(x0=seg_start, x1=max(seg_end, seg_start + 1),
                              fillcolor="red", opacity=0.22, line_width=0,
                              layer="below", row=row, col=1)

    fig.update_yaxes(title_text="series", row=1, col=1)
    fig.update_yaxes(title_text=f"{det_a}<br>rank", range=[-0.02, 1.02], row=2, col=1)
    fig.update_yaxes(title_text=f"{det_b}<br>rank", range=[-0.02, 1.02], row=3, col=1)
    fig.update_yaxes(title_text="disagreement<br>|Δrank|", row=4, col=1)
    fig.update_xaxes(title_text="time", row=4, col=1)
    fig.update_layout(title=title, height=740, margin=dict(l=90, r=20, t=60, b=50),
                      font=dict(size=12), hovermode="x unified")
    return fig


def plot_curve(curve, window):
    """Agreement against tolerance window. The slope is the whole story."""
    fig = go.Figure(go.Scatter(
        x=list(range(len(WINDOWS))), y=curve, mode="lines+markers",
        line=dict(width=2.5, color="#2b8a3e"), marker=dict(size=9), showlegend=False,
    ))
    fig.add_vline(x=WINDOWS.index(window), line=dict(color="#e07b00", width=1.5, dash="dash"))
    fig.update_layout(
        height=260, margin=dict(l=60, r=20, t=40, b=45), font=dict(size=12),
        title="Agreement as timing slack increases",
        xaxis=dict(tickmode="array", tickvals=list(range(len(WINDOWS))),
                   ticktext=["pointwise"] + [f"±{w}" for w in WINDOWS[1:]],
                   title="tolerance window"),
        yaxis=dict(title="Spearman", range=[-1.02, 1.02]),
    )
    return fig


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
with st.sidebar:
    kind = get_kind()

agreement = cached_pair_agreement(kind)
if agreement.empty:
    st.warning(
        f"No agreement table for kind = `{kind}`.\n\n"
        f"```bash\npython src/divergence/step1_agreement.py --kind {kind}\n```"
    )
    st.stop()

with st.sidebar:
    window = window_selector()
    threshold = st.slider("A pair agrees if median agreement >", 0.0, 1.0, 0.90, 0.01)
    metric = st.selectbox("Quality metric", VALID_METRICS,
                          index=VALID_METRICS.index(DEFAULT_METRIC))
    min_quality = st.slider(
        "Both detectors must score at least", 0.0, 1.0, 0.40, 0.05,
        help="Two detectors that both score 0.05 are not worth studying: whether "
             "they agree or disagree tells us nothing. This filters on the weaker "
             "of the two, measured on this dataset.",
    )

col = f"w{window}"
if col not in agreement.columns:
    st.warning(f"This agreement table has no `{col}` column. Rebuild step 1.")
    st.stop()

agreement = agreement.assign(delta=agreement[col] - agreement["w1"])

# --- 1. pair x dataset ------------------------------------------------------
st.subheader("1. Pairs that agree")

cells = (
    agreement.groupby(["detector_a", "detector_b", "dataset"])
    .agg(agreement=(col, "median"), n_series=(col, "count"),
         n_real=("delta", lambda s: int((s < -MOVED).sum())))
    .reset_index()
)
cells = cells[cells["agreement"] > threshold]
cells = attach_quality(cells, cached_detector_quality(kind, metric))

n_before = len(cells)
cells = cells[cells["worse"].fillna(0) >= min_quality]
cells = cells.sort_values("n_real", ascending=False)

if cells.empty:
    st.info(
        f"Nothing survives: no pair both agrees above {threshold:.2f} and has both "
        f"detectors scoring at least {min_quality:.2f}. Loosen one of them."
    )
    st.stop()

st.caption(
    f"{len(cells)} of {n_before} agreeing pairs have both detectors scoring at "
    f"least {min_quality:.2f} on {metric}. The rest were dropped: if both "
    f"detectors are bad, their agreement is not evidence of anything."
)

cells["pair"] = cells.detector_a + "  /  " + cells.detector_b
picked = st.dataframe(
    cells[["pair", "dataset", "agreement", "n_series", "n_real",
           "quality_a", "quality_b", "worse"]],
    width="stretch", hide_index=True, height=250,
    on_select="rerun", selection_mode="single-row",
    column_config={
        "pair": st.column_config.TextColumn(
            "Pair",
            help="The two detectors being compared. Their scores are turned into "
                 "ranks first, because detector score scales are not comparable."),
        "dataset": st.column_config.TextColumn(
            "Dataset",
            help="A pair can behave alike on one dataset and not another, so every "
                 "row is one pair on one dataset."),
        "agreement": st.column_config.NumberColumn(
            "Agreement", format="%.3f",
            help="Median Spearman correlation between the two detectors across this "
                 "dataset's series, at the tolerance window set in the sidebar. "
                 "1.0 = they rank every timestamp identically, 0 = unrelated. "
                 "Only pairs above your threshold are listed."),
        "n_series": st.column_config.NumberColumn(
            "Series", help="How many series in this dataset the pair was compared on."),
        "n_real": st.column_config.NumberColumn(
            "Real splits",
            help="Series where agreement gets WORSE once timing slack is allowed. "
                 "If one detector merely fired early or late, slack fixes it and "
                 "agreement rises. If it falls, one detector genuinely never fired "
                 "where the other did. These are the series worth looking at."),
        "quality_a": st.column_config.NumberColumn(
            "Quality A", format="%.3f",
            help="Mean score of the first detector on this dataset, using the "
                 "metric chosen in the sidebar."),
        "quality_b": st.column_config.NumberColumn(
            "Quality B", format="%.3f",
            help="Mean score of the second detector on this dataset."),
        "worse": st.column_config.NumberColumn(
            "Worse of the two", format="%.3f",
            help="The weaker detector's score. Sort by this to find pairs where "
                 "BOTH detectors are actually good -- those are the only ones "
                 "whose disagreement is worth interpreting."),
    },
)
rows = picked.selection.rows
cell = cells.iloc[rows[0] if rows else 0]
st.caption(f"Showing **{cell.pair}** on **{cell.dataset}**. Click any row to change it.")

# --- 2. series --------------------------------------------------------------
st.subheader("2. Which series really split")

table = agreement[
    (agreement.dataset == cell.dataset)
    & (agreement.detector_a == cell.detector_a)
    & (agreement.detector_b == cell.detector_b)
].copy()
table["kind"] = table.delta.map(verdict)
table = table.sort_values("delta")

n_real = int((table.delta < -MOVED).sum())
n_timing = int((table.delta > MOVED).sum())
st.markdown(
    f"**{cell.detector_a} and {cell.detector_b} agree on {len(table)} {cell.dataset} series. "
    f"On {n_real} they genuinely disagree — on {n_timing} more it was only timing.**"
)

picked_series = st.dataframe(
    table[["filename", "w1", col, "delta", "kind", "n_points"]],
    width="stretch", hide_index=True, height=250,
    on_select="rerun", selection_mode="single-row",
    column_config={
        "filename": st.column_config.TextColumn(
            "Series", help="One time series. Click the row to plot it below."),
        "w1": st.column_config.NumberColumn(
            "Pointwise", format="%.3f",
            help="Agreement with no timing slack: the two detectors must fire on "
                 "exactly the same timestamps to count as agreeing."),
        col: st.column_config.NumberColumn(
            f"With ±{window}", format="%.3f",
            help=f"Agreement once each detector is credited for firing anywhere "
                 f"within {window} points. This forgives a detector that fires "
                 f"early, late, or for longer than the other."),
        "delta": st.column_config.NumberColumn(
            "Change", format="%+.3f",
            help="With-slack minus pointwise. POSITIVE means the disagreement was "
                 "only timing and slack repaired it. NEGATIVE means slack made "
                 "things worse, so one detector genuinely missed something."),
        "kind": st.column_config.TextColumn(
            "Verdict",
            help="'real disagreement' if agreement fell, 'timing only' if it rose, "
                 "'they agree' if it barely moved."),
        "n_points": st.column_config.NumberColumn(
            "Length", help="Number of timestamps in the series."),
    },
)
srows = picked_series.selection.rows
series_row = table.iloc[srows[0] if srows else 0]

# --- 3. the plot ------------------------------------------------------------
st.subheader("3. Look at it")

parser = get_parser(kind)
fnames, timeseries, labels = parser.load_timeseries(filename=[series_row.filename])
traces = series_traces(kind, cell.detector_a, cell.detector_b, series_row.filename, window)

if traces is None:
    st.warning("Scores unavailable for this series.")
else:
    rank_a, rank_b, distance, smoothed, curve = traces
    left, right = st.columns([2, 1])
    with left:
        st.markdown(
            f"**{verdict(series_row.delta).capitalize()}** — agreement goes "
            f"{series_row.w1:.3f} → {series_row[col]:.3f} when a ±{window} point "
            f"timing slack is allowed."
        )
    with right:
        st.plotly_chart(plot_curve(curve, window), width="stretch")

    st.plotly_chart(
        plot_split(timeseries[0], labels[0], rank_a, rank_b, distance, smoothed,
                   cell.detector_a, cell.detector_b,
                   title=f"{cell.detector_a} vs {cell.detector_b} — {series_row.filename}"),
        width="stretch",
    )
    st.caption(
        "Both detectors shown as ranks, not raw scores: their scales are not "
        "comparable. Bottom row is the per-point rank distance. If the curve on "
        "the right goes up, the split was only timing; if it goes down, one "
        "detector genuinely missed something. Drag to zoom."
    )
