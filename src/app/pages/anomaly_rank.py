"""Anomalies, page 1: which anomalies is everyone missing?

Ranks every labelled anomaly by how well detectors find it on average, so the
hard tail and the trivial head are both visible.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import plotly.graph_objects as go
import streamlit as st

from app.utils import anomaly_page_setup, render_anomaly_inspector

st.title("Hardest & Easiest Anomalies")

setup = anomaly_page_setup()
if setup is None:
    st.stop()
kind, buffer, df_all, df, detectors = setup

with st.sidebar:
    top_k = st.slider("How many to list", 5, 50, 10)

ranked = df.sort_values('overall_detectability').reset_index(drop=True)
n_anomalies = len(ranked)
k = min(int(top_k), n_anomalies)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Anomalies", f"{n_anomalies:,}")
c2.metric("Detectors", len(detectors))
c3.metric("Mean detectability", f"{ranked.overall_detectability.mean():.3f}")
if 'chance' in ranked.columns:
    c4.metric("Chance", f"{ranked.chance.mean():.3f}",
              help="What a random detector scores at this buffer. Read every "
                   "number against it.")

fig = go.Figure(go.Histogram(
    x=ranked['overall_detectability'], nbinsx=40,
    marker_color='#4C78A8', showlegend=False,
))
hardest_cut = ranked['overall_detectability'].iloc[k - 1]
easiest_cut = ranked['overall_detectability'].iloc[max(n_anomalies - k, 0)]
fig.add_vline(x=hardest_cut, line=dict(color='#d62728', width=2, dash='dash'),
              annotation_text=f"{k} hardest", annotation_position="top left")
fig.add_vline(x=easiest_cut, line=dict(color='#2b8a3e', width=2, dash='dash'),
              annotation_text=f"{k} easiest", annotation_position="top right")
if 'chance' in ranked.columns:
    fig.add_vline(x=ranked.chance.mean(), line=dict(color='#e07b00', width=2),
                  annotation_text="chance", annotation_position="top")
fig.update_layout(
    xaxis_title="Mean detection density across detectors",
    yaxis_title="Anomalies", height=340, bargap=0.02,
    margin=dict(l=60, r=20, t=40, b=50), font=dict(size=13),
)
st.plotly_chart(fig, width='stretch')

st.caption(
    "Detection density is the fraction of an anomaly's points that land inside "
    "a detector's top-q timestamps, where q is the anomaly rate of that series. "
    "Ranking is what makes detectors comparable: their raw score scales are not."
)

columns = ['filename', 'dataset', 'anomaly_idx', 'length',
           'overall_detectability', 'best_detector']
column_config = {
    "filename": "Series",
    "dataset": "Dataset",
    "anomaly_idx": st.column_config.NumberColumn("Anomaly #"),
    "length": st.column_config.NumberColumn("Length", help="Points in the anomaly."),
    "overall_detectability": st.column_config.NumberColumn(
        "Detectability", format="%.3f",
        help="Mean detection density across every detector."),
    "best_detector": st.column_config.TextColumn(
        "Best detector", help="The detector with the highest density on this anomaly."),
}

hardest = ranked.head(k).reset_index(drop=True)
easiest = (ranked.tail(k).sort_values('overall_detectability', ascending=False)
           .reset_index(drop=True))

left, right = st.columns(2)
with left:
    st.markdown(f"**{k} hardest** — nobody finds these")
    hardest_event = st.dataframe(
        hardest[columns], width='stretch', hide_index=True,
        column_config=column_config, key="hardest_table",
        on_select="rerun", selection_mode="single-row",
    )
with right:
    st.markdown(f"**{k} easiest** — everybody finds these")
    easiest_event = st.dataframe(
        easiest[columns], width='stretch', hide_index=True,
        column_config=column_config, key="easiest_table",
        on_select="rerun", selection_mode="single-row",
    )

st.caption("Click a row to see that anomaly in its series.")


def _selected_row(event) -> int | None:
    rows = (event.selection.get("rows") if event and event.selection else None) or []
    return rows[0] if rows else None


# Both tables keep their own selection, so a click on one does not clear the
# other. Track which one actually changed this rerun and show that anomaly.
picks = {'hardest': _selected_row(hardest_event), 'easiest': _selected_row(easiest_event)}
previous = st.session_state.get('rank_picks', {'hardest': None, 'easiest': None})
changed = [side for side, row in picks.items()
           if row is not None and row != previous.get(side)]
if changed:
    st.session_state['rank_active'] = changed[0]
st.session_state['rank_picks'] = picks

active = st.session_state.get('rank_active')
if picks.get(active) is None:
    active = next((side for side, row in picks.items() if row is not None), None)

if active is not None:
    table = hardest if active == 'hardest' else easiest
    index = picks[active]
    if index < len(table):
        st.divider()
        st.subheader(f"Selected anomaly — {active}")
        render_anomaly_inspector(kind, table.iloc[index], detectors)
