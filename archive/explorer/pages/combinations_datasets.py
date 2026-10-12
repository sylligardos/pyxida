"""Combinations, page 2: which datasets does the choice of pair actually matter for?

The overview says picking the right pair is worth something on average. This
page says where that average comes from -- which datasets carry it, which are
indifferent -- and then hands you the individual series worth opening.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.utils import (
    HEURISTIC_COLORS, HEURISTIC_LABELS, cached_heuristics,
    cached_solo_baseline, combo_k_selector, get_kind, vus_buffer_selector,
)

ORDER = ['top_k', 'max_coverage', 'least_corr_top10', 'least_corr', 'best']

st.title("Combinations — By Dataset")

kind = get_kind()
table = cached_heuristics(kind)
if table.empty:
    st.info("No step-4 tables yet. Run `src/divergence/run_step4_all.sh`.")
    st.stop()

buffer = vus_buffer_selector()
k = combo_k_selector()

solo = cached_solo_baseline(kind, (buffer,))
solo_at = solo[solo.buffer == buffer][['filename', 'solo_vus']]

at = table[(table.buffer == buffer) & (table.k == k)].merge(
    solo_at, on='filename', how='left')
at['gain'] = at.vus - at.solo_vus
at['dataset'] = at.dataset.astype(str)

# ---------------------------------------------------------------------------
# Headroom: how much the exhaustive winner beats the obvious choice
# ---------------------------------------------------------------------------

pivot = at.pivot_table(index='dataset', columns='heuristic', values='gain',
                       aggfunc='mean', observed=True)
pivot = pivot.reindex(columns=[h for h in ORDER if h in pivot.columns])
if 'best' in pivot and 'top_k' in pivot:
    pivot['headroom'] = pivot['best'] - pivot['top_k']
    pivot = pivot.sort_values('headroom', ascending=False)

counts = at.groupby('dataset', observed=True).filename.nunique()

st.caption(
    f"{at.filename.nunique()} series across {pivot.shape[0]} datasets, at "
    f"k={k} and L={buffer}. Every value is the mean VUS gain over the best "
    "single detector on the same series, so 0 means the combination was worth "
    "nothing and negative means it hurt."
)

headroom = pivot['headroom'] if 'headroom' in pivot else pd.Series(dtype=float)
if not headroom.empty:
    fig_bar = go.Figure(go.Bar(
        x=[f"{d}  (n={counts.get(d, 0)})" for d in headroom.index],
        y=headroom.values, marker_color='#2b8a3e',
        text=[f"{v:.3f}" for v in headroom.values], textposition='outside',
        customdata=np.c_[pivot['best'].values, pivot['top_k'].values],
        hovertemplate=("%{x}<br>best %{customdata[0]:+.4f}"
                       "<br>top-k %{customdata[1]:+.4f}"
                       "<br><b>headroom %{y:.4f}</b><extra></extra>"),
    ))
    fig_bar.update_layout(
        title=f"Headroom — the best {k}-set minus the top-{k}",
        yaxis_title=f"Best {k}-set minus top-{k} (VUS-PR)", height=450,
        margin=dict(l=60, r=20, t=50, b=150), font=dict(size=13),
        xaxis=dict(tickangle=-60, tickfont=dict(size=11)),
    )
    st.plotly_chart(fig_bar, width='stretch')
    st.caption(
        "Read against a different baseline from the table below. This bar is "
        "**Best minus Top-k**, so the best-single-detector baseline cancels "
        "out; the table's cells are each measured **against the best single "
        "detector**. On NAB that is 0.049 minus -0.013, giving 0.062. Tall "
        "bars are datasets where the obvious choice is badly wrong and "
        "searching pays; bars near zero are datasets where you may as well "
        f"take the {k} best detectors and stop."
    )

# ---------------------------------------------------------------------------
# Every strategy, every dataset
# ---------------------------------------------------------------------------

st.subheader("Gain over the best single detector")
st.caption(
    "Every cell is that strategy's mean VUS-PR minus the best single "
    "detector's, on the same series. The bar above is the Best column minus "
    "the Top-k column of this table, which is why the two do not read the same."
)

matrix = pivot.drop(columns=['headroom'], errors='ignore')
if not matrix.empty:
    limit = float(np.nanmax(np.abs(matrix.to_numpy()))) or 1.0
    fig_heat = go.Figure(go.Heatmap(
        z=matrix.to_numpy(),
        x=[HEURISTIC_LABELS.get(c, c) for c in matrix.columns],
        y=[f"{d}  (n={counts.get(d, 0)})" for d in matrix.index],
        colorscale='RdBu', zmid=0, zmin=-limit, zmax=limit,
        text=[[f"{v:+.3f}" if pd.notna(v) else "" for v in row]
              for row in matrix.to_numpy()],
        texttemplate="%{text}", textfont=dict(size=10),
        colorbar=dict(thickness=14, title=dict(text="gain", side="right")),
        hovertemplate="%{y}<br>%{x}<br>gain %{z:+.4f}<extra></extra>",
    ))
    fig_heat.update_layout(
        height=max(320, 34 * len(matrix) + 190),
        margin=dict(l=170, r=20, t=30, b=130), font=dict(size=13),
        xaxis=dict(tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(autorange='reversed', tickfont=dict(size=11)),
    )
    st.plotly_chart(fig_heat, width='stretch')
    st.caption(
        "Blue is a gain over the single best detector, red is a loss. A red "
        "cell under Top-k means that on that dataset, averaging the two "
        "best-scoring detectors actively costs you."
    )

# ---------------------------------------------------------------------------
# The series worth opening
# ---------------------------------------------------------------------------

st.subheader("Series where the obvious choice is most wrong")

with st.sidebar:
    dataset_options = ['(all)'] + list(pivot.index)
    focus = st.selectbox("Dataset for the series list", dataset_options)
    top_n = st.slider("How many series", 5, 50, 15)

worst = at[at.heuristic == 'top_k'].copy()
if focus != '(all)':
    worst = worst[worst.dataset == focus]

best_rows = at[at.heuristic == 'best'][['filename', 'vus', 'detectors']]
worst = worst.merge(best_rows, on='filename', how='left',
                    suffixes=('_top', '_best'))
worst['missed'] = worst.vus_best - worst.vus_top
worst = worst.sort_values('missed', ascending=False).head(int(top_n))

columns = ['filename', 'dataset', 'detectors_top', 'vus_top',
           'detectors_best', 'vus_best', 'missed']
event = st.dataframe(
    worst[columns], width='stretch', hide_index=True,
    key='worst_series', on_select='rerun', selection_mode='single-row',
    column_config={
        'filename': 'Series', 'dataset': 'Dataset',
        'detectors_top': st.column_config.TextColumn(
            f'Top-{k}', help='What ranking by solo VUS would have picked.'),
        'vus_top': st.column_config.NumberColumn('VUS', format='%.3f'),
        'detectors_best': st.column_config.TextColumn(
            'Exhaustive best', help='The actual best set of this size.'),
        'vus_best': st.column_config.NumberColumn('VUS ', format='%.3f'),
        'missed': st.column_config.NumberColumn(
            'Missed', format='%.3f',
            help='VUS the top-k choice gave up on this series.'),
    },
)
st.caption("Click a row to open that series on the Inspect page.")

rows = (event.selection.get('rows') if event and event.selection else None) or []
if rows and rows[0] < len(worst):
    picked = worst.iloc[rows[0]]
    # The same session-state keys the sidebar selectors read, so the Inspect
    # page opens on this series with every other setting still in place.
    st.session_state['combo_dataset'] = str(picked.dataset)
    st.session_state['combo_series'] = str(picked.filename)
    try:
        st.switch_page('pages/combinations.py')
    except Exception:
        st.success(
            f"Selected {picked.filename}. Open **Inspect a Series** to see it."
        )
