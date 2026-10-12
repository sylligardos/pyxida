"""Anomalies, page 2: which detector wins where?

Groups anomalies by the detector that found them best, then shows how every
other detector scored on the same group. Off-diagonal mass means the winner had
company; a sharp diagonal means it was alone.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import plotly.graph_objects as go
import streamlit as st

from app.utils import anomaly_page_setup, detector_heatmap

st.title("Which Detector Wins Where")

setup = anomaly_page_setup()
if setup is None:
    st.stop()
kind, buffer, df_all, df, detectors = setup

wins = df['best_detector'].value_counts().reindex(detectors, fill_value=0)
wins = wins.sort_values(ascending=False)
never_wins = wins[wins == 0].index.tolist()
n_unfound = int((df['best_detector'] == "none").sum())

c1, c2, c3 = st.columns(3)
c1.metric("Anomalies", f"{len(df):,}")
c2.metric("Detectors that win at least once", int((wins > 0).sum()))
c3.metric("Top detector's share", f"{wins.iloc[0] / max(len(df) - n_unfound, 1) * 100:.1f}%",
          help="Of the anomalies at least one detector found.")
if n_unfound:
    st.caption(
        f"{n_unfound:,} of {len(df):,} anomalies ({n_unfound / len(df) * 100:.1f}%) "
        f"were found by no detector at all, and are excluded below -- they have "
        f"no winner to group by."
    )

fig_bar = go.Figure(go.Bar(
    x=wins.index.tolist(), y=wins.values,
    marker_color='#4C78A8', showlegend=False,
    hovertemplate="%{x}<br>%{y} anomalies<extra></extra>",
))
fig_bar.update_layout(
    title="Anomalies won, per detector",
    yaxis_title="Anomalies won", height=430,
    margin=dict(l=60, r=20, t=50, b=150),
    xaxis=dict(tickangle=-60, tickfont=dict(size=11)),
    font=dict(size=13),
)
st.plotly_chart(fig_bar, width='stretch')

if never_wins:
    st.caption(f"Never the best on any anomaly here: {', '.join(never_wins)}.")

st.subheader("How the rest scored on the same anomalies")

matrix = (
    df.groupby('best_detector')[detectors].mean()
    .reindex([d for d in wins.index if wins[d] > 0])
    .dropna(how='all')
)
if matrix.empty:
    st.info("No groups to show.")
else:
    st.plotly_chart(
        detector_heatmap(
            matrix,
            title="Mean detection density — rows: winner, columns: every detector",
            y_title="Won by",
        ),
        width='stretch',
    )
    st.caption(
        "Each row is the set of anomalies a detector won. Columns are sorted by "
        "their overall mean, shown in brackets. A row that is bright only on its "
        "own column is a detector finding things nobody else does; a row that is "
        "bright across many columns means the win was a narrow margin."
    )
