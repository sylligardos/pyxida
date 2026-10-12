"""Workbench: the one place a series is reviewed.

Every link in the demo lands here, so this page owns the series in
st.session_state and never resets a setting on arrival -- losing the sidebar
when you follow a link is the single worst thing the exploratory app does.

Detectors shown are the top 3 by solo VUS-PR at the L on the slider, because
that is what a reader wants to see first: the best anyone did on this series.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root

import numpy as np
import pandas as pd
import streamlit as st

from app.lib import (
    WORKBENCH_ANOMALY_KEY,
    WORKBENCH_COMBOS_KEY,
    WORKBENCH_KEY,
    WORKBENCH_PINS_KEY,
    WORKBENCH_SAMPLE_KEY,
    anomaly_bounds,
    benchmark_summary,
    cached_combo_detectors,
    cached_combos,
    cached_metrics,
    combined_score,
    combo_datasets,
    current_benchmark,
    current_kind,
    demo_series,
    get_parser,
    has_combos,
    scored_series,
    load_notes,
    page_header,
    plot_series_plotly,
    save_note,
    takeaway,
    vus_buffer_selector,
)

KIND = current_kind()
DEFAULT_N_DETECTORS = 3
# A multivariate series can have 100+ channels; one plot row each is unreadable.
DEFAULT_CHANNELS = 3
MAX_CHANNELS = 8
MAX_DETECTORS = 6
# Above this the browser is drawing more points than it has pixels, and the
# sample button should not hand someone a page that takes ten seconds.
SAMPLE_MAX_POINTS = 300_000

page_header(
    "🔬 Workbench",
    "What does this series actually look like, and what did the detectors do?",
)

parser = get_parser(KIND)
meta = parser.meta.reset_index()
# Every cache below takes the benchmark: two benchmarks can hold series with the
# same file name (0001_Daphnet_... exists in TSB-UAD and in TAB).
BENCH = current_benchmark()
DEMO_SERIES = demo_series(KIND)

# Benchmarks scored only on examples have many series with no detector at all.
# Listing them by default lands the reader on empty plots.
scored = scored_series(KIND)
if 0 < len(scored) < len(meta):
    # A link to a series with no scores would otherwise be filtered out of the
    # list it is meant to select, and the arrival silently ignored.
    if st.session_state.get(WORKBENCH_KEY) in set(meta.filename) - scored:
        st.session_state["wb_only_scored"] = False
    st.session_state.setdefault("wb_only_scored", True)
    with st.sidebar:
        only_scored = st.checkbox(
            "Only series with scores", key="wb_only_scored",
            help=f"{len(scored):,} of {len(meta):,} series in this benchmark have "
                 "detector scores. Untick to browse the rest (series and labels only).")
    if only_scored:
        meta = meta[meta.filename.isin(scored)]
if meta.empty:
    st.info("This benchmark has no series of this kind.")
    st.stop()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading series ...")
def load_series(bench: str, kind: str, filename: str):
    names, series, labels = get_parser(kind).load_timeseries(filename=[filename])
    return series[0], labels[0]


@st.cache_data
def channel_labels(bench: str, kind: str, filename: str, n: int) -> list:
    """Channel names from the CSV header (all columns but Label)."""
    header = pd.read_csv(get_parser(kind).raw_path / filename, nrows=0).columns[:-1]
    return [str(c) for c in header][:n] if len(header) >= n else [f"C{i}" for i in range(n)]


@st.cache_data
def solo_vus(bench: str, kind: str, dataset: str, buffer: int, filename: str) -> pd.Series:
    """Solo VUS-PR for every detector on one series, at one L.

    Read from the step-3 shards, which store all 257 buffers, so the slider is
    continuous. Falls back to the metrics the benchmark ships, which exist for
    every series but only at the ten buffers TSB-AD reports.
    """
    roster = cached_combo_detectors(kind)
    frame = cached_combos(kind, dataset, buffer)
    if not frame.empty and roster:
        rows = frame[(frame.filename == filename) & (frame.k == 1)]
        if not rows.empty:
            return pd.Series(
                rows.vus.to_numpy(),
                index=[roster[i] for i in rows.d0.to_numpy()],
            ).sort_values(ascending=False)

    metrics = cached_metrics(kind)
    column = f"VUS-PR (L: {buffer})"
    if column in metrics.columns:
        rows = metrics[metrics["File Name"] == filename]
        rows = rows[rows["Model Name"].isin(parser.get_detectors())]
        if not rows.empty:
            return (rows.set_index("Model Name")[column]
                    .dropna().sort_values(ascending=False))
    return pd.Series(dtype=float)


@st.cache_data
def score_of(bench: str, kind: str, filename: str, detector: str):
    """One detector's score on one series, or None if it is missing there."""
    _, scores, _ = get_parser(kind).load_scores(
        detectors=[detector], filenames=[filename],
        drop_missing=True, return_filenames=True,
    )
    return scores[0][0] if scores else None


@st.cache_data
def combo_score(bench: str, kind: str, filename: str, members: tuple):
    """The averaged score of a set -- the thing its VUS was computed on."""
    return combined_score(get_parser(kind), filename, list(members))


@st.cache_data
def combo_vus(bench: str, kind: str, dataset: str, buffer: int, filename: str,
              members: tuple) -> float | None:
    """VUS-PR of one combination, looked up rather than recomputed.

    Step 3 scored every set of 2 and 3 exhaustively, so the number on screen is
    the same one the Redundancy page ranked with. Sets of another size were
    never scored and get no number instead of a differently-computed one.
    """
    roster = cached_combo_detectors(kind)
    if not roster or not 2 <= len(members) <= 3:
        return None
    try:
        wanted = frozenset(roster.index(name) for name in members)
    except ValueError:
        return None

    frame = cached_combos(kind, dataset, buffer)
    rows = frame[(frame.filename == filename) & (frame.k == len(members))]
    columns = [f"d{i}" for i in range(len(members))]
    for values, vus in zip(rows[columns].to_numpy(), rows.vus.to_numpy()):
        if frozenset(values) == wanted:
            return float(vus)
    return None


# ---------------------------------------------------------------------------
# Which series
# ---------------------------------------------------------------------------

buffer = vus_buffer_selector(continuous=has_combos(KIND))

arrived = st.session_state.pop(WORKBENCH_KEY, None)
arrival_pins = st.session_state.pop(WORKBENCH_PINS_KEY, None)
arrival_anomaly = st.session_state.pop(WORKBENCH_ANOMALY_KEY, None)
arrival_combos = st.session_state.pop(WORKBENCH_COMBOS_KEY, None)

if arrived in set(meta.filename):
    # Someone followed a link. Move the selectors to it once, then let them be.
    st.session_state["wb_dataset"] = meta[meta.filename == arrived].iloc[0].dataset
    st.session_state["wb_series"] = arrived

    if arrival_pins is not None:
        # Replace, never append, and focus: a link that names detectors is a
        # request to look at those detectors, not at those plus three others.
        st.session_state["wb_pins"] = [d for d in arrival_pins
                                       if d in set(parser.get_detectors())]
        st.session_state["wb_top_n"] = 0
    if arrival_anomaly is not None:
        st.session_state["wb_anomaly"] = int(arrival_anomaly)
    if arrival_combos is not None:
        st.session_state["wb_combos"] = [list(c) for c in arrival_combos]

datasets = sorted(meta.dataset.unique())
# Cold start on the same short NAB series the Start page draws, rather than on
# whatever sorts first -- that is CATSv2, 300k points, and a slow first
# impression is the one thing a demo cannot afford.
default_row = meta[meta.filename == DEMO_SERIES]
if not len(default_row) and len(meta):
    default_row = meta.head(1)
if len(default_row):
    st.session_state.setdefault("wb_dataset", default_row.iloc[0].dataset)
    st.session_state.setdefault("wb_series", default_row.iloc[0].filename)
# Remembered from another visit, or from before the filter above changed.
if st.session_state.get("wb_dataset") not in datasets:
    st.session_state["wb_dataset"] = datasets[0]


def sample_series() -> None:
    """Jump to a random series, anywhere in the benchmark.

    Uniform over everything short enough to draw instantly. Nothing cleverer: a
    weighted "interesting" sample would be a claim about what is interesting,
    and the demo's whole argument is that nobody should take that on trust.
    """
    lengths = benchmark_summary(KIND).get("lengths", {})
    pool = meta[meta.filename.map(lambda f: lengths.get(f, 0)) <= SAMPLE_MAX_POINTS]
    pick = (pool if len(pool) else meta).sample(1).iloc[0]
    st.session_state["wb_dataset"] = pick.dataset
    st.session_state["wb_series"] = pick.filename


if st.session_state.pop(WORKBENCH_SAMPLE_KEY, False):
    sample_series()

with st.sidebar:
    st.button("🎲 Sample a series", on_click=sample_series, width='stretch')
    dataset = st.selectbox("Dataset", datasets, key="wb_dataset")

    in_dataset = sorted(meta[meta.dataset == dataset].filename)
    # Changing dataset strands the old series: its name is not in the new
    # options, and Streamlit raises rather than falling back.
    if st.session_state.get("wb_series") not in in_dataset:
        st.session_state["wb_series"] = in_dataset[0]
    st.selectbox("Series", in_dataset, key="wb_series")

    st.session_state.setdefault("wb_top_n", DEFAULT_N_DETECTORS)
    n_detectors = st.slider(
        "Top detectors", 0, MAX_DETECTORS, key="wb_top_n",
        help="The best N on this series by solo VUS-PR at the L above. Set it "
             "to 0 to see only the detectors you pick below.",
    )

filename = st.session_state["wb_series"]

series, labels = load_series(BENCH, KIND, filename)
starts, ends = anomaly_bounds(labels)
row = meta[meta.filename == filename].iloc[0]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.subheader(filename)
columns = st.columns(5)
columns[0].metric("Dataset", row.dataset)
columns[1].metric("Type", row.entity_type)
columns[2].metric("Length", f"{len(series):,}")
columns[3].metric("Anomalies", len(starts))
columns[4].metric("Anomalous", f"{100 * float(np.mean(labels)):.2f}%")

ranking = solo_vus(BENCH, KIND, row.dataset, buffer, filename)
rank_of = {name: position for position, name in enumerate(ranking.index, start=1)}
ranked = not ranking.empty


def detector_label(detector: str) -> str:
    """`MatrixProfile - 0.31 (#17)`. The rank is usually the point: it says how
    far down the leaderboard the detector you care about actually sits."""
    if detector in rank_of:
        return f"{detector} — {ranking[detector]:.3f}  (#{rank_of[detector]})"
    return f"{detector} — unranked here"


# Pins are a set of names, so they survive a change of series or of L. Options
# are the whole roster, not just the ranked ones, so a link can pin anything
# and the widget never rejects its own state.
roster = sorted(parser.get_detectors(), key=lambda d: (rank_of.get(d, 10_000), d))
with st.sidebar:
    st.session_state.setdefault("wb_pins", [])
    st.session_state["wb_pins"] = [d for d in st.session_state["wb_pins"]
                                   if d in set(roster)]
    pinned = st.multiselect(
        "Also show", roster, key="wb_pins", format_func=detector_label,
        help="Pinned detectors stay as you move between series, so you can "
             "follow one detector across the benchmark.",
    )

    combos = [tuple(c) for c in st.session_state.get("wb_combos", [])]
    if len(pinned) >= 2 and st.checkbox(
        "Average the pinned detectors",
        help="Draws the mean of the pinned scores as one extra row -- the "
             "ensemble a combination's VUS is actually computed on.",
    ):
        combos.append(tuple(pinned))
    combos = list(dict.fromkeys(combos))
    if st.session_state.get("wb_combos") and st.button("Clear combinations",
                                                       width='stretch'):
        del st.session_state["wb_combos"]
        st.rerun()

top = list(ranking.index[:n_detectors]) if ranked else []
if not ranked:
    top = sorted(parser.get_detectors())[:n_detectors]

# A detector that is both in the top N and pinned appears once, badged as
# pinned. Everything is drawn best-first regardless of how it got here.
shown = {detector: False for detector in top}
for detector in pinned:
    shown[detector] = True
shown = dict(sorted(shown.items(), key=lambda kv: rank_of.get(kv[0], 10_000)))

if ranked:
    st.caption(
        f"Ranked by solo VUS-PR at L={buffer}. "
        f"{len(rank_of)} detectors scored this series."
    )
else:
    st.caption(
        "No VUS on record for this series, so the top-N falls back to "
        "alphabetical order."
    )

entries = [
    (f"{'📌 ' if is_pinned else ''}{f'#{rank_of[d]} ' if d in rank_of else ''}{d}",
     f"{ranking[d]:.3f}" if d in rank_of else "--")
    for d, is_pinned in shown.items()
]
# Combinations get a tile too, not just a row on the chart: "what does the pair
# actually score" is the question the Redundancy page sends people here with.
for members in combos:
    value = combo_vus(BENCH, KIND, row.dataset, buffer, filename, members)
    entries.append(("Σ " + " + ".join(members),
                    f"{value:.3f}" if value is not None else "--"))

if entries:
    # Five to a row: any more and the numbers are too narrow to read.
    for start in range(0, len(entries), 5):
        for column, (label, value) in zip(st.columns(5), entries[start:start + 5]):
            column.metric(label, value)

# ---------------------------------------------------------------------------
# The picture
# ---------------------------------------------------------------------------

if len(starts) == 0:
    picked = None
    st.session_state.pop("wb_anomaly", None)
    st.info("This series carries no labelled anomaly.")
else:
    options = [None] + list(range(len(starts)))
    # One widget per series. Under a single key Streamlit keeps the widget when
    # the options change, so moving to another series left the previous
    # series' range on the label ("#1 2,014-2,148" on a 1,421-point series).
    # A link's anomaly arrives in wb_anomaly and seeds the new widget once.
    anomaly_key = f"wb_anomaly_{filename}"
    seed = st.session_state.pop("wb_anomaly", None)
    # Only a real index is written: a None in session state reads as "nothing
    # selected" and shows the placeholder, where the first option is wanted.
    if seed is not None and seed in options:
        st.session_state[anomaly_key] = seed
    picked = st.selectbox(
        "Highlight an anomaly",
        options, key=anomaly_key,
        format_func=lambda i: (
            "Show all of them" if i is None
            else f"#{i + 1}   {starts[i]:,}–{ends[i]:,}   ({ends[i] - starts[i]:,} pts)"
        ),
        help="The series is never zoomed. The chosen anomaly is drawn solid "
             "and the rest fade, so you keep the context around it.",
    )

traces, names, unavailable = [], [], []
for detector, is_pinned in shown.items():
    score = score_of(BENCH, KIND, filename, detector)
    if score is None or len(score) != len(labels):
        unavailable.append(detector)
        continue
    traces.append(score)
    # Rank goes on the second line, after the VUS: the first line already
    # carries the pin and the name, and row labels are drawn rotated, so a long
    # first line is what makes neighbouring rows collide.
    rank = rank_of.get(detector)
    label = f"{'📌 ' if is_pinned else ''}{detector}"
    if detector in rank_of:
        label += f"<br>VUS {ranking[detector]:.3f} · #{rank}"
    names.append(label)

# Combinations last, under their members: the members explain the row above
# them, and the reader should meet them in that order.
for members in combos:
    score = combo_score(BENCH, KIND, filename, members)
    if score is None or len(score) != len(labels):
        unavailable.append(" + ".join(members))
        continue
    traces.append(score)
    label = "Σ " + " + ".join(members)
    value = combo_vus(BENCH, KIND, row.dataset, buffer, filename, members)
    if value is not None:
        label += f"<br>VUS {value:.3f}"
    names.append(label)

if unavailable:
    st.caption(
        f"Not scored on this series, so not drawn: {', '.join(unavailable)}."
    )
if not traces:
    st.info(
        "No detectors selected. Raise **Top detectors** or pick some under "
        "**Also show** in the sidebar."
    )

plotted = series
if series.ndim == 2 and series.shape[1] > 1:
    channel_names = channel_labels(BENCH, KIND, filename, series.shape[1])
    # One widget per series, as with the anomaly picker. A multiselect keeps
    # its choice as the displayed labels, so under one key the next series'
    # channel names did not match and came back as strings (TypeError).
    key = f"wb_channels_{filename}"
    channels = st.multiselect(
        f"Channels ({series.shape[1]} in this series)", list(range(series.shape[1])),
        default=list(range(min(DEFAULT_CHANNELS, series.shape[1]))),
        max_selections=MAX_CHANNELS, key=key, format_func=lambda c: channel_names[c],
        help="One plot row per channel. Detector scores are for the whole "
             "multivariate series, whichever channels are drawn.")
    channels = [c for c in channels if isinstance(c, int)]
    plotted = series[:, channels] if channels else series[:, :1]

figure = plot_series_plotly(
    plotted, labels,
    title=filename,
    detector_scores=traces or None,
    detector_names=names or None,
    highlight=(int(starts[picked]), int(ends[picked])) if picked is not None else None,
)
n_channel_rows = plotted.shape[1] if plotted.ndim == 2 else 1
figure.update_layout(height=max(400, 150 * (len(traces) + n_channel_rows)))
st.plotly_chart(figure, width='stretch')
st.caption(
    "Top row(s): the series, one per channel drawn, anomalies in red. Below, one "
    "row per detector, scores as the detector emitted them."
)

# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

notes = load_notes()
# TSB-AD notes keep the bare file name they were saved under; elsewhere the key
# says which benchmark and kind, since file names repeat across benchmarks.
note_key = filename if BENCH == "tsb-ad" else f"{BENCH}:{KIND}:{filename}"
existing = notes.get(note_key, {})

with st.expander(f"📝 Notes{' (saved)' if existing else ''}", expanded=bool(existing)):
    text = st.text_area(
        "What did you see?",
        value=existing.get("note", ""),
        key=f"note_{note_key}",
        height=120,
        label_visibility="collapsed",
        placeholder="e.g. MatrixProfile fires 12 points before the anomaly, "
                    "not on it.",
    )
    left, right = st.columns([1, 4])
    if left.button("Save note", width='stretch'):
        save_note(note_key, text)
        st.rerun()
    if existing:
        right.caption(f"Last saved {existing['updated']}")

    if notes:
        st.caption(f"{len(notes)} series with notes:")
        st.dataframe(
            pd.DataFrame(
                [{"series": name, "note": value["note"], "updated": value["updated"]}
                 for name, value in sorted(notes.items())]
            ),
            width='stretch', hide_index=True,
        )

takeaway("Look at your data before you trust a number.")
