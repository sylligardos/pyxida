"""Combinations: is the best pair the one you would have picked?

For a series, every combination of 2 or 3 detectors has been scored by VUS-PR.
This page puts the exhaustive winner beside the sets four plausible heuristics
would have chosen, and shows what each one actually looks like on the data.

Every set here is an oracle -- chosen using the labels it is then scored on --
so this is a visualiser, not a selector. That is the point: it shows how much a
heuristic leaves on the table, which is only knowable in hindsight.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.utils import (
    cached_combo_detectors, cached_combos, cached_detection,
    cached_metrics, cached_pair_agreement, combined_score, combo_datasets,
    combo_dataset_selector, combo_k_selector, combo_series_selector,
    get_kind, get_parser, plot_series_plotly, vus_buffer_selector,
)
from divergence.selection import (
    HEURISTICS, greedy_coverage, mean_pairwise_rho, pick_sets, rho_matrix,
)

LABELS = {
    "best": "Best (exhaustive)",
    "top_k": "Top-k by solo VUS",
    "least_corr": "Least correlated",
    "least_corr_top10": "Least correlated, top-10 only",
    "max_coverage": "Max coverage (greedy)",
}
COLORS = {
    "best": "#2b8a3e", "top_k": "#4C78A8", "least_corr": "#b0b0b0",
    "least_corr_top10": "#9467bd", "max_coverage": "#e07b00",
}
ENSEMBLES = ["Oracle", "AccuCopy", "AverageEnsembling", "AOM",
             "MaximumEnsembling", "MOA", "CRH", "RandomMS"]

st.title("Detector Combinations")

kind = get_kind()
datasets = combo_datasets(kind)
detectors = cached_combo_detectors(kind)

if not datasets or not detectors:
    st.info(
        "No combination shards yet. Run `src/divergence/run_step3_all.sh` "
        "from the ffvus environment; this page picks up each dataset as its "
        "shard lands."
    )
    st.stop()

buffer = vus_buffer_selector()
dataset = combo_dataset_selector(datasets)
k = combo_k_selector()

combos = cached_combos(kind, dataset, buffer)
if combos.empty:
    st.info(f"No rows for {dataset}.")
    st.stop()

series_list = sorted(combos.filename.unique())
filename = combo_series_selector(series_list)

with st.sidebar:
    show_members = st.checkbox("Show individual detector scores", value=True)
    shown = st.multiselect(
        "Sets to draw", HEURISTICS,
        default=["best", "top_k", "max_coverage", "least_corr_top10"],
        format_func=lambda h: LABELS[h],
    )

try:
    st.page_link("pages/combinations_datasets.py", label="Back to By Dataset",
                 icon=":material/arrow_back:")
except Exception:
    # Only resolvable through st.navigation; a standalone run has no registry.
    pass

st.caption(f"{len(datasets)} of 23 datasets computed so far: {', '.join(datasets)}")


# ---------------------------------------------------------------------------
# Pick the candidate sets for this series
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Selecting candidate sets ...")
def candidates(kind: str, dataset: str, buffer: int, filename: str, k: int):
    frame = cached_combos(kind, dataset, buffer)
    frame = frame[frame.filename == filename]
    roster = cached_combo_detectors(kind)

    solo = frame[frame.k == 1]
    solo_vus = np.full(len(roster), -np.inf)
    solo_vus[solo.d0.to_numpy()] = solo.vus.to_numpy()

    block = frame[frame.k == k]
    if block.empty:
        return None
    combo_ids = block[[f"d{i}" for i in range(k)]].to_numpy()
    vus = block.vus.to_numpy(dtype=np.float64)
    genuine = block.n_constant.to_numpy() == 0

    pairs = cached_pair_agreement(kind)
    pairs = pairs[pairs.filename == filename]
    matrix = rho_matrix(pairs, roster)
    rho = mean_pairwise_rho(matrix, combo_ids)

    detection = cached_detection(kind)
    rows = detection[detection.filename == filename]
    coverage_set = None
    if not rows.empty:
        density = (rows.pivot_table(index="anomaly_idx", columns="detector",
                                    values="d0")
                   .reindex(columns=roster)
                   .to_numpy(dtype=np.float64, na_value=0.0))
        if density.shape[0]:
            coverage_set = greedy_coverage(density, k)

    picks = pick_sets(combo_ids, vus, genuine, solo_vus, rho, coverage_set)
    best_vus = vus[picks["best"]] if picks["best"] is not None else np.nan
    solo_by_name = {roster[i]: float(v) for i, v in enumerate(solo_vus)
                    if np.isfinite(v)}

    out = []
    for name in HEURISTICS:
        row = picks.get(name)
        if row is None:
            continue
        members = sorted(combo_ids[row].tolist())
        out.append({
            "heuristic": name,
            "detectors": [roster[d] for d in members],
            "vus": float(vus[row]),
            "regret": float(best_vus - vus[row]),
            "mean_rho": float(rho[row]) if np.isfinite(rho[row]) else np.nan,
            "degenerate": bool(block.n_constant.to_numpy()[row] > 0),
        })
    return (pd.DataFrame(out), float(np.nanmax(solo_vus)),
            roster[int(np.argmax(solo_vus))], solo_by_name)


result = candidates(kind, dataset, buffer, filename, k)
if result is None:
    st.info("No combinations of that size for this series.")
    st.stop()
table, best_solo_vus, best_solo_name, solo_vus_by_name = result

# ---------------------------------------------------------------------------
# Headline
# ---------------------------------------------------------------------------

row_best = table[table.heuristic == "best"].iloc[0]
row_top = table[table.heuristic == "top_k"]

c1, c2, c3 = st.columns(3)
c1.metric(f"Best single detector", f"{best_solo_vus:.3f}", help=best_solo_name)
c2.metric(f"Best {k}-set (exhaustive)", f"{row_best.vus:.3f}",
          delta=f"{row_best.vus - best_solo_vus:+.3f} vs single")
if not row_top.empty:
    c3.metric(f"Top-{k} by solo VUS", f"{row_top.iloc[0].vus:.3f}",
              delta=f"{row_top.iloc[0].vus - row_best.vus:+.3f} vs best",
              delta_color="inverse")

display = table.assign(
    Set=table.detectors.apply(lambda d: " + ".join(d)),
    Heuristic=table.heuristic.map(LABELS),
)[["Heuristic", "Set", "vus", "regret", "mean_rho", "degenerate"]]
st.dataframe(
    display, width='stretch', hide_index=True,
    column_config={
        "vus": st.column_config.NumberColumn(f"VUS-PR (L={buffer})", format="%.4f"),
        "regret": st.column_config.NumberColumn(
            "Regret", format="%.4f",
            help="VUS the exhaustive winner gets that this set does not. "
                 "Negative means this set beat every genuine combination, "
                 "i.e. combining hurt on this series."),
        "mean_rho": st.column_config.NumberColumn(
            "Mean rho", format="%.3f",
            help="Mean pairwise Spearman between members. Blank when one "
                 "member has a constant score, which makes rho undefined."),
        "degenerate": st.column_config.CheckboxColumn(
            "Not a true k-set",
            help="Ticked when a member scores a constant on this series. A "
                 "constant shifts an average by the same amount everywhere, so "
                 "it cannot change the ranking: the set scores exactly what its "
                 "remaining members score alone, and is really a smaller set. "
                 "The exhaustive winner never picks one; a ticked box means "
                 "that heuristic chose a set that collapses."),
    },
)

# ---------------------------------------------------------------------------
# The picture
# ---------------------------------------------------------------------------

parser = get_parser(kind)
try:
    _, series_list_loaded, label_list = parser.load_timeseries(filename=[filename])
except ValueError:
    st.error(f"Could not load {filename}")
    st.stop()

series, labels = series_list_loaded[0], label_list[0]

traces, names = [], []
drawn = table[table.heuristic.isin(shown)]

def wrap(text: str, width: int = 16) -> str:
    """Break a row label into short lines.

    Row labels are drawn rotated, so each <br> becomes a parallel line running
    across the row rather than down it -- more breaks means less vertical
    extent, which is what stops long names colliding with their neighbours.
    """
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "<br>".join(lines)


if show_members:
    members = sorted({d for row in drawn.detectors for d in row})
    for detector in members:
        score = combined_score(parser, filename, [detector])
        if score is not None:
            traces.append(score)
            solo = solo_vus_by_name.get(detector)
            names.append(wrap(detector) +
                         (f"<br>VUS {solo:.3f}" if solo is not None else ""))

for _, row in drawn.iterrows():
    score = combined_score(parser, filename, row.detectors)
    if score is None:
        continue
    traces.append(score)
    names.append(f"<b>{wrap(LABELS[row.heuristic])}</b><br>VUS {row.vus:.3f}")

fig = plot_series_plotly(
    series if series.ndim == 1 else series,
    labels,
    title=f"{filename} — combinations of {k}, VUS at L={buffer}",
    detector_scores=traces or None,
    detector_names=names or None,
)
fig.update_layout(height=max(420, 130 * (len(traces) + 1)))
st.plotly_chart(fig, width='stretch')
st.caption(
    "Top row is the series with labelled anomalies in red. Then the individual "
    "detectors involved, then each candidate set's averaged score. Scores are "
    "re-scaled to [0,1] before averaging -- SR's median maximum is 0.303, so a "
    "raw average would quietly under-weight it."
)

# ---------------------------------------------------------------------------
# What the shipped ensembles get on this series
# ---------------------------------------------------------------------------

metric_column = f"VUS-PR (L: {buffer})"
metrics = cached_metrics(kind)
if metric_column in metrics.columns:
    here = metrics[metrics["File Name"] == filename]
    shipped = (here[here["Model Name"].isin(ENSEMBLES)][["Model Name", metric_column]]
               .dropna().sort_values(metric_column, ascending=False)
               .rename(columns={"Model Name": "model"}))
    if not shipped.empty:
        st.subheader("Shipped ensembles on this series")
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=shipped.model.tolist(), y=shipped[metric_column].tolist(),
            marker_color="#8c8c8c", name="shipped",
            hovertemplate="%{x}<br>%{y:.3f}<extra></extra>",
        ))
        for _, row in table.iterrows():
            fig_bar.add_hline(
                y=row.vus, line=dict(color=COLORS[row.heuristic], width=2,
                                     dash="solid" if row.heuristic == "best" else "dot"),
                annotation_text=LABELS[row.heuristic],
                annotation_position="right",
            )
        fig_bar.update_layout(
            yaxis_title=f"VUS-PR (L={buffer})", height=420,
            margin=dict(l=60, r=220, t=30, b=110),
            xaxis=dict(tickangle=-45), font=dict(size=13), showlegend=False,
        )
        st.plotly_chart(fig_bar, width='stretch')
        st.caption(
            "Bars are what the benchmark ships, computed over all detectors. "
            "Lines are our sets of "
            f"{k}. Every line is an oracle -- selected with the labels it is "
            "scored on -- so a line above a bar is headroom, not a method."
        )
