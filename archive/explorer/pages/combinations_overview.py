"""Combinations, page 1: does picking the right pair matter, benchmark-wide?

Every combination of 2 and 3 detectors was scored exhaustively by VUS-PR. This
page puts the exhaustive winner beside the sets four plausible heuristics would
have chosen, averaged over every series computed so far.

Every set is an oracle -- chosen with the labels it is then scored on -- so the
gap between a heuristic and "best" is headroom, not a method.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.utils import (
    HEURISTIC_COLORS, HEURISTIC_LABELS, VUS_BUFFERS, cached_heuristics,
    TSBAD_VUS_BUFFERS, cached_solo_baseline, combo_datasets, get_kind,
    vus_buffer_selector,
)

st.title("Combinations — Overview")

kind = get_kind()
table = cached_heuristics(kind)
if table.empty:
    st.info(
        "No step-4 tables yet. Run `src/divergence/run_step4_all.sh` once the "
        "step-3 sweep has produced at least one shard."
    )
    st.stop()

buffer = vus_buffer_selector()
solo = cached_solo_baseline(kind, (buffer,))

at = table[table.buffer == buffer]
solo_at = solo[solo.buffer == buffer][['filename', 'solo_vus']]
at = at.merge(solo_at, on='filename', how='left')

n_series = at.filename.nunique()
n_datasets = at.dataset.nunique()
st.caption(
    f"Computed on **{n_series} series** across **{n_datasets} of 23 datasets** "
    f"({', '.join(sorted(map(str, at.dataset.unique())))}). "
    "The sweep is still running, so these numbers will move -- the datasets "
    "still missing are the ones with the most anomalies per series."
)

# ---------------------------------------------------------------------------
# The one-liners
# ---------------------------------------------------------------------------

mean_solo = at.groupby('filename')['solo_vus'].first().mean()


def slice_of(heuristic: str, k: int) -> pd.DataFrame:
    return at[(at.heuristic == heuristic) & (at.k == k)]


best2, top2 = slice_of('best', 2), slice_of('top_k', 2)
merged = best2[['filename', 'vus']].merge(
    top2[['filename', 'vus', 'solo_vus']], on='filename',
    suffixes=('_best', '_top'))

c1, c2, c3 = st.columns(3)
if not merged.empty:
    worse = (merged.vus_top < merged.solo_vus).mean() * 100
    c1.metric("Top-2 is worse than one detector", f"{worse:.0f}% of series",
              help="Averaging the two highest-scoring detectors, compared with "
                   "just using the best single one.")
    c2.metric("Best pair beats best single by",
              f"{(merged.vus_best - merged.solo_vus).mean():+.3f}",
              help="Mean VUS gain of the exhaustive best pair over the best "
                   "single detector, per series.")
    c3.metric("Top-2 leaves on the table",
              f"{(merged.vus_best - merged.vus_top).mean():.3f}",
              help="Mean regret of the top-2 heuristic against the exhaustive "
                   "best pair.")

# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------

st.subheader("What each strategy scores")

order, values, colors, labels = [], [], [], []
for k in (2, 3):
    for heuristic in ['top_k', 'least_corr', 'least_corr_top10',
                      'max_coverage', 'best']:
        block = slice_of(heuristic, k)
        if block.empty:
            continue
        order.append(f"{HEURISTIC_LABELS[heuristic]}<br>k={k}")
        values.append(block.vus.mean())
        colors.append(HEURISTIC_COLORS[heuristic])
        labels.append(f"{block.vus.mean():.3f}")

fig = go.Figure(go.Bar(x=order, y=values, marker_color=colors,
                       text=labels, textposition='outside',
                       hovertemplate="%{x}<br>mean VUS %{y:.4f}<extra></extra>"))
fig.add_hline(y=mean_solo, line=dict(color='#d62728', width=2, dash='dash'),
              annotation_text=f"best single detector ({mean_solo:.3f})",
              annotation_position="top left")
fig.update_layout(
    yaxis_title=f"Mean VUS-PR (L={buffer})", height=470,
    margin=dict(l=60, r=20, t=30, b=140), font=dict(size=13),
    xaxis=dict(tickangle=-40, tickfont=dict(size=11)),
)
st.plotly_chart(fig, width='stretch')
st.caption(
    "Averaged over series, not over datasets, so the larger datasets carry "
    "more weight. Anything below the dashed line is a combination that does "
    "worse than simply using the single best detector."
)

# ---------------------------------------------------------------------------
# Regret spread
# ---------------------------------------------------------------------------

st.subheader("How much each heuristic gives up")

fig_box = go.Figure()
for heuristic in ['top_k', 'max_coverage', 'least_corr_top10', 'least_corr']:
    for k in (2, 3):
        block = slice_of(heuristic, k)
        if block.empty:
            continue
        fig_box.add_trace(go.Box(
            y=block.regret, name=f"{HEURISTIC_LABELS[heuristic]}<br>k={k}",
            marker_color=HEURISTIC_COLORS[heuristic], boxpoints=False,
        ))
fig_box.update_layout(
    yaxis_title="Regret vs exhaustive best", height=430, showlegend=False,
    margin=dict(l=60, r=20, t=30, b=140), font=dict(size=13),
    xaxis=dict(tickangle=-40, tickfont=dict(size=11)),
)
st.plotly_chart(fig_box, width='stretch')
st.caption(
    "Regret is the VUS the exhaustive winner gets that this heuristic does "
    "not. A mean hides whether a heuristic is steadily mediocre or usually "
    "right and occasionally catastrophic -- the spread does not."
)

# ---------------------------------------------------------------------------
# Does it survive timing tolerance?
# ---------------------------------------------------------------------------

st.subheader("Does the gap survive timing tolerance?")

curves = []
for k in (2, 3):
    for heuristic in ['best', 'top_k']:
        block = table[(table.heuristic == heuristic) & (table.k == k)]
        per_buffer = block.groupby('buffer')['vus'].mean()
        curves.append((f"{HEURISTIC_LABELS[heuristic]} k={k}", per_buffer,
                       HEURISTIC_COLORS[heuristic],
                       'solid' if k == 2 else 'dot'))

solo_curve = (cached_solo_baseline(kind, tuple(TSBAD_VUS_BUFFERS))
              .groupby('buffer')['solo_vus'].mean())

fig_line = go.Figure()
fig_line.add_trace(go.Scatter(
    x=solo_curve.index, y=solo_curve.values, mode='lines+markers',
    name='best single detector',
    line=dict(color='#d62728', width=2, dash='dash')))
for name, series, color, dash in curves:
    fig_line.add_trace(go.Scatter(
        x=series.index, y=series.values, mode='lines+markers', name=name,
        line=dict(color=color, width=2, dash=dash)))
fig_line.update_layout(
    xaxis_title="VUS buffer L", yaxis_title="Mean VUS-PR",
    height=430, margin=dict(l=60, r=20, t=30, b=60), font=dict(size=13),
)
st.plotly_chart(fig_line, width='stretch')
st.caption(
    "L=0 is strict pointwise; larger L forgives timing error, the way VUS-PR "
    "does. If the gap between the exhaustive best and the top-k closed as L "
    "grew, the effect would be a timing artefact rather than a real difference "
    "in what the detectors find."
)
