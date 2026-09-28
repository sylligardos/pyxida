"""Agreement measured on anomalies rather than on timestamps.

The score-level Agreement page correlates whole score vectors, which is
dominated by the ~95% of timestamps that are normal. Two detectors can look
independent there and still catch exactly the same anomalies. This page asks
the question the benchmark is actually about: do they find the same anomalies?

The unit is the dataset, not the series. The median series holds 2 anomalies,
and a correlation over 2 points is noise.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.utils import (
    ANOMALY_LENGTH_MODES, buffer_selector, cached_anomaly_agreement,
    cached_detection, cached_detection_wide, cached_score_agreement_median,
    chart_selection, combined_score, detection_detectors, get_kind,
    get_parser, plot_series_plotly, render_anomaly_inspector,
)

st.title("Agreement on Anomalies")

kind = get_kind()
detection = cached_detection(kind)
if detection.empty:
    st.info("No detection table yet. Run `src/divergence/step2_detection.py`.")
    st.stop()

datasets = sorted(detection.filename.str.split('_').str[1].unique())
with st.sidebar:
    dataset = st.selectbox("Dataset", ['All datasets'] + datasets, index=1)
    length_label = st.radio("Anomalies", list(ANOMALY_LENGTH_MODES),
                            help="77.5% of anomalies in TSB-AD-U are a single "
                                 "point, so the split matters.")
buffer = buffer_selector()
length_mode = ANOMALY_LENGTH_MODES[length_label]

result = cached_anomaly_agreement(kind, dataset, buffer, length_mode)
if not result:
    st.info("Not enough anomalies for a correlation under this filter.")
    st.stop()

matrix = result['matrix']

# ---------------------------------------------------------------------------
# 1. The contrast: scores say independent, anomalies say otherwise
# ---------------------------------------------------------------------------

values = matrix.to_numpy()[np.triu_indices(len(matrix), 1)]
values = values[np.isfinite(values)]
score_median = cached_score_agreement_median(kind, dataset)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Anomaly-level agreement", f"{np.median(values):.3f}",
          delta=f"{np.median(values) - score_median:+.3f} vs scores",
          help="Median Spearman between detectors, computed over per-anomaly "
               "detection density.")
c2.metric("Score-level agreement", f"{score_median:.3f}",
          help="Median Spearman between the same detectors' full score "
               "vectors. Dominated by normal timestamps.")
c3.metric("Anomalies", f"{result['n_anomalies']:,}")
c4.metric("Solved by nothing", f"{result['found_by_none'] * 100:.1f}%",
          help="Anomalies where the best of all 32 detectors still scored "
               "below 0.9. Chance is 0.5, and with 32 detectors something "
               "clears 0.5 on every anomaly in the benchmark, so 0.9 is the "
               "bar that separates a real solve from noise. These are what the "
               "field has not cracked.")

st.caption(
    f"**How many detectors find an anomaly:** the median anomaly here is found "
    f"by **{result['median_caught']:.0f} of {result['n_detectors']}** "
    "detectors, counting every detector scoring above 0.5 at this buffer. "
    "Density is a ramp-weighted mean percentile rank, so 0.5 is exactly chance "
    "and anything above it is a real response. A low number means the "
    "anomalies are hard and few methods reach them."
)
st.caption(
    "Correlating whole score vectors answers 'do these two behave alike over "
    "time'. Correlating per-anomaly density answers 'do these two find the "
    "same anomalies', which is the question the benchmark exists to ask."
)

if result.get('macro'):
    st.info(
        f"**Averaged across {result['n_datasets']} datasets, each counting "
        "once.** Every number on this page is computed within a dataset first "
        "and then averaged over datasets, rather than pooling all anomalies "
        "together. Pooling would make this a page about Stock, which is 72% of "
        "all anomaly events in TSB-AD-U. The score-level figure is "
        "macro-averaged the same way so the two are comparable."
    )

# ---------------------------------------------------------------------------
# 2. Detectors that never fire on this dataset
# ---------------------------------------------------------------------------

if result['dead']:
    where = ("on every dataset" if result.get('macro') else f"on {dataset}")
    st.error(
        f"**{len(result['dead'])} of {result['n_detectors']} detectors never "
        f"vary {where}**: {', '.join(result['dead'])}. Their density is "
        "constant, so their correlation with anything is undefined and they "
        "are excluded below. Undefined is not the same as uncorrelated: a "
        "detector that never fires would otherwise look maximally diverse."
    )

# ---------------------------------------------------------------------------
# 3. The matrix, best detectors first
# ---------------------------------------------------------------------------

st.subheader("Who finds the same anomalies")

masked = matrix.to_numpy().astype(float).copy()
masked[np.tril_indices(len(masked), 0)] = np.nan
labels = [f"{d}  ({result['density'][d]:.2f})" for d in result['order']]

fig = go.Figure(go.Heatmap(
    z=masked, x=labels, y=labels, colorscale='RdBu_r', zmid=0, zmin=-1, zmax=1,
    colorbar=dict(thickness=14, title=dict(text="Spearman", side="right")),
    hovertemplate="%{y}<br>%{x}<br>rho = %{z:.3f}<extra></extra>",
))
fig.update_layout(
    height=max(520, 24 * len(matrix) + 220),
    margin=dict(l=200, r=20, t=30, b=200), font=dict(size=12),
    xaxis=dict(tickangle=-60, tickfont=dict(size=10)),
    yaxis=dict(autorange='reversed', tickfont=dict(size=10)),
)
matrix_event = st.plotly_chart(fig, on_select="rerun", selection_mode="points",
                               key="agreement_matrix", width='stretch')
st.caption(
    "Detectors are ordered by mean detection density, best first, with that "
    "density in brackets. Red near the top-left corner is the finding: the "
    "detectors worth using on this dataset are the ones that duplicate each "
    "other. **Click any cell** to load that pair into the scatter below."
)

# A clicked cell names its two detectors. The selectboxes further down are
# built after this point in the script, so writing their session-state keys
# here lands before they are instantiated, which is the only order in which
# Streamlit lets one widget drive another.
label_to_detector = {label: detector
                     for label, detector in zip(labels, result['order'])}
for point in chart_selection(matrix_event):
    picked = [label_to_detector.get(point.get(axis)) for axis in ('x', 'y')]
    if all(picked):
        st.session_state['aa_det_a'], st.session_state['aa_det_b'] = picked
    break

# ---------------------------------------------------------------------------
# 4. Is agreement concentrated among the good detectors?
# ---------------------------------------------------------------------------

rows = []
for n in (3, 5, 10):
    if len(result['order']) < n:
        continue
    top = result['order'][:n]
    block = matrix.loc[top, top].to_numpy()
    vals = block[np.triu_indices(n, 1)]
    vals = vals[np.isfinite(vals)]
    if len(vals):
        rows.append({'group': f"top {n} by density", 'mean_rho': vals.mean()})
rows.append({'group': 'all pairs', 'mean_rho': float(np.mean(values))})
summary = pd.DataFrame(rows)

fig_bar = go.Figure(go.Bar(
    x=summary.group, y=summary.mean_rho,
    marker_color=['#d62728'] * (len(summary) - 1) + ['#4C78A8'],
    text=[f"{v:.3f}" for v in summary.mean_rho], textposition='outside',
))
fig_bar.update_layout(
    title="Do the best detectors agree more than average?",
    yaxis_title="Mean Spearman over anomalies", height=380,
    margin=dict(l=60, r=20, t=50, b=60), font=dict(size=13),
)
st.plotly_chart(fig_bar, width='stretch')

# ---------------------------------------------------------------------------
# 5. Pair drill-down: one point per anomaly
# ---------------------------------------------------------------------------

st.subheader("Two detectors, anomaly by anomaly")

# Changing dataset or filter rewrites the detector list, and a stored pick
# that is no longer an option would make the selectbox raise.
options = result['order']
for key, fallback in (('aa_det_a', 0), ('aa_det_b', 1)):
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[min(fallback, len(options) - 1)]

left, right = st.columns(2)
with left:
    det_a = st.selectbox("Detector A", options, key='aa_det_a')
with right:
    det_b = st.selectbox("Detector B", options, key='aa_det_b')

wide = cached_detection_wide(kind, buffer)
if dataset != 'All datasets':
    # Filter with a mask rather than assigning a column: every non-detector
    # column added here has to be excluded by name in detection_detectors(),
    # and one that is not gets treated as a detector.
    wide = wide[wide.filename.str.split('_').str[1] == dataset]
if length_mode == 'point':
    wide = wide[wide.length == 1]
elif length_mode == 'subsequence':
    wide = wide[wide.length > 1]

if det_a in wide.columns and det_b in wide.columns and not wide.empty:
    pair = wide.dropna(subset=[det_a, det_b]).reset_index(drop=True)
    jitter = np.random.default_rng(0).normal(0, 0.012, (len(pair), 2))
    rho_ab = matrix.loc[det_a, det_b]

    # ---------------------------------------------------------------------
    # The whole series for this pair, with the picked anomaly highlighted
    # ---------------------------------------------------------------------
    # The scatter is rendered further down, so its selection is read here from
    # session state, left over from the run in which it was clicked. That is
    # what lets a click below change the plot above.
    picked = chart_selection(st.session_state.get('anomaly_pair'))
    picked_row = None
    if picked:
        index = picked[0].get('point_index')
        if index is not None and index < len(pair):
            picked_row = pair.iloc[index]

    series_options = sorted(pair.filename.unique())
    if picked_row is not None and picked_row.filename in series_options:
        default_series = picked_row.filename
    else:
        # Otherwise open on the series where the pair disagrees most, which is
        # the one worth looking at.
        spread = (pair[det_a] - pair[det_b]).abs()
        default_series = pair.loc[spread.idxmax(), 'filename']
    if st.session_state.get('aa_series') not in series_options:
        st.session_state['aa_series'] = default_series
    elif picked_row is not None:
        st.session_state['aa_series'] = picked_row.filename

    chosen_series = st.selectbox("Series", series_options, key='aa_series')

    parser = get_parser(kind)
    try:
        _, series_list, label_list = parser.load_timeseries(filename=[chosen_series])
        values, labels_full = series_list[0], label_list[0]
    except (ValueError, IndexError):
        values, labels_full = None, None

    if values is not None:
        traces, names = [], []
        for detector in (det_a, det_b):
            score = combined_score(parser, chosen_series, [detector])
            if score is not None and len(score) == len(labels_full):
                traces.append(score)
                names.append(detector)

        highlight = None
        if picked_row is not None and picked_row.filename == chosen_series:
            highlight = (int(picked_row.start), int(picked_row.end))

        st.plotly_chart(
            plot_series_plotly(
                values, labels_full,
                title=f"{chosen_series} — full series, {det_a} and {det_b}",
                detector_scores=traces or None,
                detector_names=names or None,
                highlight=highlight,
            ),
            width='stretch',
        )
        st.caption(
            "The whole series with both detectors' full scores. Every labelled "
            "anomaly is red; once you click a point in the scatter below, that "
            "anomaly turns solid and the rest fade, with a band marking it on "
            "the score rows."
            if highlight else
            "The whole series with both detectors' full scores, every labelled "
            "anomaly in red. Click a point in the scatter below to single one "
            "out."
        )

    hover = ("File: " + pair.filename
             + "<br>Anomaly #" + pair.anomaly_idx.astype(str)
             + "<br>Length: " + pair.length.astype(str)
             + f"<br>{det_a}: " + pair[det_a].round(3).astype(str)
             + f"<br>{det_b}: " + pair[det_b].round(3).astype(str)).tolist()

    fig_sc = go.Figure(go.Scattergl(
        x=pair[det_a] + jitter[:, 0], y=pair[det_b] + jitter[:, 1],
        mode='markers',
        marker=dict(size=5, opacity=0.45, color='#4C78A8'),
        text=hover, hovertemplate='%{text}<extra></extra>',
    ))
    fig_sc.add_shape(type='line', x0=0, y0=0, x1=1, y1=1,
                     line=dict(color='#999', width=1, dash='dash'))
    fig_sc.update_layout(
        title=f"{det_a} vs {det_b} — rho = {rho_ab:.3f}, {len(pair):,} anomalies",
        xaxis_title=f"{det_a} detection density",
        yaxis_title=f"{det_b} detection density",
        height=560, margin=dict(l=70, r=20, t=50, b=60), font=dict(size=13),
    )
    event = st.plotly_chart(fig_sc, on_select="rerun", selection_mode="points",
                            key="anomaly_pair", width='stretch')
    st.caption(
        "One point per anomaly, jittered so the corners do not hide their own "
        "density. On the dashed line the two agree. Top-left and bottom-right "
        "are anomalies one detector finds and the other misses entirely, and "
        "those are the ones worth opening. Click a point to see it."
    )

    if picked_row is not None:
        st.divider()
        st.subheader(f"{det_a} vs {det_b}, zoomed on the picked anomaly")
        render_anomaly_inspector(
            kind, picked_row, detection_detectors(wide),
            show_detectors=[det_a, det_b],
            subtitle=(f"{det_a} {picked_row[det_a]:.3f} / "
                      f"{det_b} {picked_row[det_b]:.3f}"),
        )
        st.caption(
            "The same anomaly as the highlight above, zoomed in. The two "
            "traces are the pair you selected, not the two detectors that "
            "happened to score this anomaly best, so a flat trace here is one "
            "of your pair missing it."
        )
else:
    st.info("Those two detectors have no shared anomalies under this filter.")
