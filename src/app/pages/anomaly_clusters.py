"""Anomalies, page 3: do anomalies group by which detectors find them?

Clusters anomalies on their detector-density profile, then lets you colour the
projection by anomaly properties to see whether the clusters line up with
anything nameable. Click a point to inspect that anomaly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from app.utils import (
    anomaly_page_setup, cached_detection_wide, chart_selection,
    detection_detectors, detector_heatmap, render_anomaly_inspector,
)

st.title("Anomaly Clusters")

setup = anomaly_page_setup()
if setup is None:
    st.stop()
kind, buffer, df_all, df_filtered, detectors = setup

with st.sidebar:
    n_clusters = st.slider("Number of clusters", 2, 12, 6)


def _quantile_bin(series: pd.Series, n_bins: int = 5) -> pd.Categorical:
    """Quantile-bin a series, labelling groups from the actual boundaries."""
    _, boundaries = pd.qcut(series, n_bins, retbins=True, duplicates='drop')
    labels = [f"{int(round(boundaries[i]))}-{int(round(boundaries[i + 1]))}"
              for i in range(len(boundaries) - 1)]
    return pd.qcut(series, n_bins, labels=labels, duplicates='drop')


def _length_bin(series: pd.Series) -> pd.Categorical:
    """Bin anomaly length, keeping point anomalies as their own group.

    Length 1 is most of the benchmark, so plain quantile binning collapses to
    two groups and hides all the structure in the subsequence tail.
    """
    tail = series[series > 1]
    if tail.empty:
        return pd.cut(series, bins=[0, 1], labels=["Point (1)"], include_lowest=True)
    _, raw = pd.qcut(tail, 4, retbins=True, duplicates='drop')
    bounds = [int(round(b)) for b in raw]
    bounds[0] = 2
    labels = ["Point (1)"] + [
        f"{bounds[i] if i == 0 else bounds[i] + 1}-{bounds[i + 1]}"
        for i in range(len(bounds) - 1)
    ]
    return pd.cut(series, bins=[0, 1] + bounds[1:], labels=labels, include_lowest=True)


def _discrete_colorscale(palette: list[str], n: int) -> list:
    scale = []
    for i in range(n):
        color = palette[i % len(palette)]
        scale += [[i / n, color], [(i + 1) / n, color]]
    return scale


@st.cache_data(show_spinner="Clustering anomalies ...")
def cluster_anomalies(kind: str, buffer: int, n_clusters: int) -> pd.DataFrame:
    """PCA + KMeans on the detector-density profile of every anomaly.

    Fitted on the whole benchmark, not the sidebar selection, so clusters and
    bin boundaries stay put while you filter.
    """
    df = cached_detection_wide(kind, buffer)
    columns = detection_detectors(df)
    features = StandardScaler().fit_transform(df[columns].fillna(0).values)

    labels = KMeans(n_clusters=min(n_clusters, len(df)),
                    random_state=42, n_init=10).fit_predict(features)
    projected = PCA(n_components=2).fit_transform(features)

    out = df.assign(PC1=projected[:, 0], PC2=projected[:, 1], cluster=labels)
    out['type_label'] = np.where(out['length'] == 1, 'Point', 'Subsequence')
    out = out.join(out.groupby('filename').size().rename('anomaly_count'), on='filename')
    out['length_bin'] = _length_bin(out['length'])
    out['anomaly_count_bin'] = _quantile_bin(out['anomaly_count'])
    if 'ts_length' in out.columns:
        out['ts_length_bin'] = _quantile_bin(out['ts_length'])
    return out


clustered = cluster_anomalies(kind, buffer, n_clusters)
clustered = clustered[
    clustered['dataset'].isin(df_filtered['dataset'].unique())
    & clustered['entity_type'].isin(df_filtered['entity_type'].unique())
].reset_index(drop=True)

if clustered.empty:
    st.info("No anomalies left after filtering.")
    st.stop()

COLOR_MODES = {
    "Cluster": ("cluster", "categorical"),
    "Point vs subsequence": ("type_label", "categorical"),
    "Entity type": ("entity_type", "categorical"),
    "Dataset": ("dataset", "categorical"),
    "Anomaly length": ("length_bin", "binned"),
    "Anomalies in series": ("anomaly_count_bin", "binned"),
}
if 'ts_length_bin' in clustered.columns:
    COLOR_MODES["Series length"] = ("ts_length_bin", "binned")

color_by = st.radio("Colour by", list(COLOR_MODES.keys()), horizontal=True,
                    key="cluster_color_by")
color_col, color_kind = COLOR_MODES[color_by]

categories = clustered[color_col].astype('category')
codes = categories.cat.codes.tolist()
names = [str(c) for c in categories.cat.categories.tolist()]
n_categories = max(len(names), 1)

if color_kind == "categorical":
    colorscale = _discrete_colorscale(pc.qualitative.Safe, n_categories)
else:
    sequential = pc.sequential.YlOrRd
    step = max(1, len(sequential) // n_categories)
    colorscale = _discrete_colorscale(
        [sequential[min(i * step, len(sequential) - 1)] for i in range(n_categories)],
        n_categories,
    )

hover = (
    "File: " + clustered['filename']
    + "<br>Anomaly #" + clustered['anomaly_idx'].astype(str)
    + "<br>Length: " + clustered['length'].astype(str)
    + "<br>Best: " + clustered['best_detector'].astype(str)
    + "<br>" + color_by + ": " + clustered[color_col].astype(str)
).tolist()

fig_scatter = go.Figure(go.Scattergl(
    x=clustered['PC1'].tolist(), y=clustered['PC2'].tolist(),
    mode='markers',
    marker=dict(
        size=5, opacity=0.7, color=codes, colorscale=colorscale,
        cmin=-0.5, cmax=n_categories - 0.5,
        colorbar=dict(tickvals=list(range(n_categories)), ticktext=names,
                      thickness=15, title=dict(text=color_by, side='right')),
    ),
    hovertemplate='%{text}<extra></extra>', text=hover,
))
fig_scatter.update_layout(
    title="Anomalies projected from their detector-density profile",
    xaxis_title="PC1", yaxis_title="PC2",
    height=520, margin=dict(l=60, r=160, t=50, b=50), font=dict(size=13),
)
event = st.plotly_chart(fig_scatter, on_select="rerun", selection_mode="points",
                        key="cluster_scatter", width='stretch')

st.caption(
    "Two anomalies sit close together when the same detectors found them, and "
    "far apart when different ones did. If a colouring lines up with the "
    "clusters, that property explains part of which detector wins."
)

cluster_means = clustered.groupby('cluster')[detectors].mean()
cluster_means.index = [f"Cluster {c}  (n={int((clustered.cluster == c).sum()):,})"
                       for c in cluster_means.index]
st.plotly_chart(
    detector_heatmap(cluster_means,
                     title="Mean detection density per cluster",
                     y_title="Cluster"),
    width='stretch',
)

# ---------------------------------------------------------------------------
# Click to inspect
# ---------------------------------------------------------------------------
points = chart_selection(event)
if points:
    index = points[0].get("point_index")
    if index is not None and index < len(clustered):
        row = clustered.iloc[index]

        st.divider()
        st.subheader("Selected anomaly")
        render_anomaly_inspector(
            kind, row, detectors,
            subtitle=f"cluster {int(row['cluster'])}",
        )
