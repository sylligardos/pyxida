import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from app.utils import (
    get_kind, get_parser, cached_metrics, cached_runtime, cached_meta,
    VALID_METRICS, DEFAULT_METRIC,
)

st.title("Global Summary")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    kind = get_kind()
    metric = st.selectbox("Metric", VALID_METRICS, index=VALID_METRICS.index(DEFAULT_METRIC))

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
parser = get_parser(kind)
metrics = cached_metrics(kind)
runtime = cached_runtime(kind)
meta = cached_meta(kind)[['filename', 'dataset', 'entity_type']]

metrics_enriched = metrics.merge(meta, left_on='File Name', right_on='filename', how='left')
runtimes_enriched = runtime.merge(meta, left_on='File Name', right_on='filename', how='left')

# ---------------------------------------------------------------------------
# Helper: build model order by mean metric ascending
# ---------------------------------------------------------------------------
def _model_order(df, col):
    return (
        df.groupby('Model Name')[col]
        .mean()
        .dropna()
        .sort_values()
        .index.tolist()
    )


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------
def render_overall_performance():
    order = _model_order(metrics_enriched, metric)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[3, 2], vertical_spacing=0.05,
    )

    for model in order:
        vals = metrics_enriched[metrics_enriched['Model Name'] == model][metric].dropna()
        fig.add_trace(go.Box(y=vals, name=model, showlegend=False, boxmean='sd',
                             line=dict(width=1), boxpoints=False), row=1, col=1)

    means = metrics_enriched.groupby('Model Name')[metric].mean().reindex(order)
    fig.add_trace(
        go.Scatter(x=order, y=means.values, mode='lines', line=dict(dash='dash', width=1.5, color='white'),
                   name='Mean', showlegend=False),
        row=1, col=1,
    )

    runtime_plot = runtimes_enriched[runtimes_enriched['Time Cost'] > 0]
    for model in order:
        vals = runtime_plot[runtime_plot['Model Name'] == model]['Time Cost'].dropna()
        fig.add_trace(go.Box(y=vals, name=model, showlegend=False, boxpoints=False,
                             line=dict(width=1)), row=2, col=1)

    fig.update_yaxes(title_text=metric, row=1, col=1)
    fig.update_yaxes(title_text='Time Cost (s)', type='log', row=2, col=1)
    fig.update_xaxes(tickangle=70, row=2, col=1)
    fig.update_layout(height=700, margin=dict(b=120), font=dict(size=13))
    st.plotly_chart(fig, width='stretch')


def render_per_dataset():
    order = _model_order(metrics_enriched, metric)

    dataset_perf = (
        metrics_enriched.groupby(['Model Name', 'dataset'])[metric]
        .mean()
        .unstack('dataset')
        .reindex(order)
    )
    col_means = dataset_perf.mean(axis=0).sort_values(ascending=True)
    dataset_perf = dataset_perf[col_means.index]
    col_labels = [f"{n}  ({v:.2f})" for n, v in col_means.items()]

    fig2 = go.Figure(go.Heatmap(
        z=dataset_perf.values,
        x=col_labels,
        y=dataset_perf.index.tolist(),
        colorscale='YlGnBu',
        text=[[f"{v:.2f}" if pd.notna(v) else "" for v in row] for row in dataset_perf.values],
        texttemplate="%{text}",
        showscale=True,
    ))
    fig2.update_layout(
        title=f"Mean {metric} per Model and Dataset",
        height=max(400, 25 * len(order)),
        margin=dict(l=160, b=150),
        xaxis=dict(tickangle=-60, tickfont=dict(size=11)),
        font=dict(size=13),
    )
    st.plotly_chart(fig2, width='stretch')


def render_per_entity_type():
    order = _model_order(metrics_enriched, metric)

    type_perf = (
        metrics_enriched.groupby(['Model Name', 'entity_type'])[metric]
        .mean()
        .unstack('entity_type')
        .reindex(order)
    )
    type_col_means = type_perf.mean(axis=0).sort_values(ascending=True)
    type_perf = type_perf[type_col_means.index]
    type_labels = [f"{n}  ({v:.2f})" for n, v in type_col_means.items()]

    fig3 = go.Figure(go.Heatmap(
        z=type_perf.values,
        x=type_labels,
        y=type_perf.index.tolist(),
        colorscale='YlOrRd',
        text=[[f"{v:.2f}" if pd.notna(v) else "" for v in row] for row in type_perf.values],
        texttemplate="%{text}",
        showscale=True,
    ))
    fig3.update_layout(
        title=f"Mean {metric} per Model and Entity Type",
        height=max(400, 25 * len(order)),
        margin=dict(l=160, b=150),
        xaxis=dict(tickangle=-60, tickfont=dict(size=11)),
        font=dict(size=13),
    )
    st.plotly_chart(fig3, width='stretch')


# ---------------------------------------------------------------------------
# Render via tabs
# ---------------------------------------------------------------------------
tab_overall, tab_dataset, tab_entity = st.tabs([
    "Overall Performance",
    "Detector × Dataset",
    "Detector × Entity Type",
])

with tab_overall:
    render_overall_performance()

with tab_dataset:
    render_per_dataset()

with tab_entity:
    render_per_entity_type()
