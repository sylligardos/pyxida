"""Landscape: which datasets and which anomaly types are still open.

Every point is a series, scored by the *best* detector on it. "Is this dataset
open" means "did anything work here", and averaging over 30 detectors mostly
measures how many weak detectors the benchmark happens to include.

Chart scopes, table navigates: clicking a box filters the tables to that
dataset or type, clicking a row opens the series in the Workbench. One meaning
per surface.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import (
    benchmark_summary,
    cached_combo_detectors,
    cached_combos,
    chart_selection,
    combo_datasets,
    get_parser,
    goto_workbench,
    page_header,
    table_selection,
    takeaway,
    vus_buffer_selector,
)

KIND = "uni"
TABLE_ROWS = 15
SCOPE_KEY = "ls_scope"

page_header(
    "🗺️ Landscape",
    "Which datasets and which anomaly types are solved, and which are open?",
)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Reading VUS for every series ...")
def landscape(kind: str, buffer: int) -> pd.DataFrame:
    """One row per series: how far the best and the median detector got.

    Read from the k=1 rows of the step-3 shards, so it is the same number the
    Workbench ranks with. Detectors that emit a constant on a series are
    dropped: a constant score has no ranking, so its VUS is an artefact of the
    anomaly rate rather than a detection.
    """
    roster = cached_combo_detectors(kind)
    if not roster:
        return pd.DataFrame()

    rows = []
    for dataset in combo_datasets(kind):
        frame = cached_combos(kind, dataset, buffer)
        if frame.empty:
            continue
        solo = frame[(frame.k == 1) & (frame.n_constant == 0)]
        if solo.empty:
            continue
        grouped = solo.groupby("filename")
        best = solo.loc[grouped.vus.idxmax()].set_index("filename")
        rows.append(pd.DataFrame({
            "dataset": best.dataset,
            "best_vus": best.vus,
            "best_detector": [roster[i] for i in best.d0],
            "median_vus": grouped.vus.median(),
            "n_detectors": grouped.vus.size(),
        }))

    if not rows:
        return pd.DataFrame()

    table = pd.concat(rows).reset_index()
    meta = get_parser(kind).meta.reset_index()[["filename", "entity_type"]]
    summary = benchmark_summary(kind)
    return (table.merge(meta, on="filename", how="left")
            .assign(
                length=lambda f: f.filename.map(summary.get("lengths", {})),
                anomalies=lambda f: f.filename.map(summary.get("anomalies", {})),
            ))


buffer = vus_buffer_selector()
table = landscape(KIND, buffer)

if table.empty:
    st.info(
        "No combination shards yet. Run `src/divergence/run_step3_all.sh` from "
        "the ffvus environment."
    )
    st.stop()

with st.sidebar:
    unit = st.radio(
        "Score each series by", ["best detector", "median detector"],
        help="Best answers 'did anything work here'. Median answers 'what do "
             "you get if you pick blindly'. The gap between them is the value "
             "of choosing well.",
    )
    datasets_shown = st.multiselect(
        "Datasets", sorted(table.dataset.unique()), default=[],
        help="Empty shows all of them.",
    )

column = "best_vus" if unit == "best detector" else "median_vus"
visible = table[table.dataset.isin(datasets_shown)] if datasets_shown else table


# ---------------------------------------------------------------------------
# The two charts
# ---------------------------------------------------------------------------

def distribution_chart(frame: pd.DataFrame, group: str, scope_kind: str) -> go.Figure:
    """One box per group, every series drawn as a clickable point.

    Sorted by median, hardest first, so the chart reads left to right as a
    priority list. The points are not decoration: a high box with one series
    hanging far below it is a solved dataset with an open case inside it, and
    that is invisible in any table of averages.
    """
    order = (frame.groupby(group)[column].median().sort_values().index.tolist())
    figure = go.Figure()
    for name in order:
        block = frame[frame[group] == name]
        figure.add_trace(go.Box(
            y=block[column], name=str(name),
            boxpoints="all", jitter=0.5, pointpos=0, marker=dict(size=4, opacity=0.55),
            line=dict(width=1.4), fillcolor="rgba(76,120,168,0.25)",
            marker_color="#4C78A8",
            customdata=block.filename,
            hovertemplate="%{customdata}<br>VUS %{y:.3f}<extra></extra>",
            showlegend=False,
        ))
    figure.update_layout(
        height=480, margin=dict(l=60, r=20, t=30, b=140),
        yaxis=dict(title=f"VUS-PR of the {unit} (L={buffer})", range=[-0.02, 1.02]),
        xaxis=dict(tickangle=-45),
        font=dict(size=13),
    )
    return figure


def apply_scope(event, group: str, frame: pd.DataFrame, order_key: str) -> None:
    """A click anywhere in a box scopes the tables to that box."""
    points = chart_selection(event)
    if not points:
        return
    point = points[0]
    index = (point.get("curve_number") if isinstance(point, dict)
             else getattr(point, "curve_number", None))
    if index is None:
        return
    groups = st.session_state.get(order_key, [])
    if 0 <= index < len(groups):
        st.session_state[SCOPE_KEY] = (group, groups[index])


by_dataset, by_type = st.tabs(["By dataset", "By entity type"])

for tab, group, key in ((by_dataset, "dataset", "ls_order_dataset"),
                        (by_type, "entity_type", "ls_order_type")):
    with tab:
        order = visible.groupby(group)[column].median().sort_values().index.tolist()
        st.session_state[key] = order
        event = st.plotly_chart(
            distribution_chart(visible, group, key),
            width='stretch', on_select="rerun", key=f"ls_chart_{group}",
        )
        apply_scope(event, group, visible, key)
        st.caption(
            f"One point per series, {len(visible)} in total. The box is the "
            f"spread across that {group.replace('_', ' ')}'s series. "
            "Click anywhere in a box to filter the tables below to it."
        )


# ---------------------------------------------------------------------------
# Hardest and easiest series
# ---------------------------------------------------------------------------

scope = st.session_state.get(SCOPE_KEY)
scoped = visible
if scope:
    group, value = scope
    scoped = visible[visible[group] == value]
    left, right = st.columns([4, 1])
    left.markdown(f"**Scoped to `{value}`** — {len(scoped)} series")
    if right.button("Clear scope", width='stretch'):
        del st.session_state[SCOPE_KEY]
        st.rerun()

COLUMNS = {
    "filename": st.column_config.TextColumn("Series", width="medium"),
    "dataset": "Dataset",
    "entity_type": "Type",
    "best_detector": "Best detector",
    column: st.column_config.NumberColumn(f"VUS ({unit.split()[0]})", format="%.3f"),
    "anomalies": st.column_config.NumberColumn("Anom.", format="%d"),
    "length": st.column_config.NumberColumn("Length", format="%d"),
}
SHOW = ["filename", "dataset", "entity_type", "best_detector", column,
        "anomalies", "length"]


def clickable(frame: pd.DataFrame, key: str) -> None:
    """A table whose rows open the Workbench.

    No detectors are named, so the reader's Top-N slider is left alone and they
    land on the best few for that series -- see the arrival contract in
    references/DEMO_PLAN.md.
    """
    event = st.dataframe(
        frame[SHOW], hide_index=True, width='stretch',
        column_config=COLUMNS, on_select="rerun",
        selection_mode="single-row", key=key,
    )
    rows = table_selection(event)
    if rows:
        goto_workbench(frame.iloc[rows[0]].filename)


hardest, easiest = st.columns(2)
with hardest:
    st.subheader("Hardest series")
    st.caption("Nothing in the benchmark gets far on these. Click one to look at it.")
    clickable(scoped.nsmallest(TABLE_ROWS, column), "ls_hard")
with easiest:
    st.subheader("Easiest series")
    st.caption("Solved. A method that wins here has not been tested.")
    clickable(scoped.nlargest(TABLE_ROWS, column), "ls_easy")

solved = float((scoped[column] > 0.9).mean()) if len(scoped) else 0.0
open_cases = float((scoped[column] < 0.3).mean()) if len(scoped) else 0.0
st.caption(
    f"{100 * solved:.0f}% of these series are solved (VUS above 0.9) and "
    f"{100 * open_cases:.0f}% are open (below 0.3). "
    f"Read over {len(cached_combo_detectors(KIND))} detectors at L={buffer}."
)

takeaway("Stop tuning on the solved datasets. The open problems are on the left.")
