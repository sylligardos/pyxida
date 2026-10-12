"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Shared helpers for the Pyxida demo.

Everything the pages share: which benchmark is open, the cached parser and
metrics, the series plot, the VUS buffer slider, the combination tables the
Workbench reads, and the two conventions every page follows (a question at the
top, a takeaway at the bottom).
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402

from app.parser import TSBADParser  # noqa: E402


# ---------------------------------------------------------------------------
# Which benchmark, and the cached parser and metrics
# ---------------------------------------------------------------------------
# The demo can show any benchmark in the common format. The choice lives in
# st.session_state[BENCHMARK_KEY], set by the sidebar. Every cached loader
# takes the benchmark as an argument: reading the session inside a cached
# function would freeze the first benchmark into the cache.

BENCHMARK_KEY = "benchmark"
DEFAULT_BENCHMARK = "tsb-ad"
DATA_DIR = REPO_ROOT / "data"
DIVERGENCE_DIR = DATA_DIR / "divergence"

# Collections a benchmark ships that the demo leaves out. TimeEval's download
# includes 12k TSB-UAD series that are not in TimeEval's own index or paper,
# and they would be 93% of "TimeEval".
HIDDEN_DATASETS = {
    "timeeval": {"TSB-UAD-artificial", "TSB-UAD-synthetic"},
}


def current_benchmark() -> str:
    return st.session_state.get(BENCHMARK_KEY, DEFAULT_BENCHMARK)


def is_tsb_ad() -> bool:
    """Only TSB-AD has the combination tables in data/divergence."""
    return current_benchmark() == DEFAULT_BENCHMARK


@st.cache_resource
def _parser(benchmark: str, kind: str) -> TSBADParser:
    if benchmark == DEFAULT_BENCHMARK:
        parser = TSBADParser(path=str(DATA_DIR), kind=kind)
    else:
        parser = TSBADParser(benchmark=benchmark, kind=kind)
    hidden = HIDDEN_DATASETS.get(benchmark)
    if hidden:
        parser.meta = parser.meta[~parser.meta.dataset.isin(hidden)]
    return parser


def get_parser(kind: str = "uni") -> TSBADParser:
    return _parser(current_benchmark(), kind)


@st.cache_data
def _metrics(benchmark: str, kind: str) -> pd.DataFrame:
    parser = _parser(benchmark, kind)
    metrics = parser.load_metrics(models=parser.get_all_models())
    if metrics.empty:
        return metrics
    return metrics[metrics["File Name"].isin(set(parser.meta.filename))]


def cached_metrics(kind: str = "uni") -> pd.DataFrame:
    return _metrics(current_benchmark(), kind)


@st.cache_resource
def _cache_generation() -> dict:
    """Process-wide box remembering which data the caches were filled from."""
    return {}


def drop_caches_if_data_changed() -> None:
    """Clear every @st.cache_data if the combination tables were rebuilt.

    The app usually outlives the pipeline: a table is rebuilt while the server
    is up, and every cached frame then describes a file that no longer exists
    on disk. Checked once per rerun in main.py.
    """
    stamp = tuple(sorted((p.name, p.stat().st_mtime)
                         for p in DIVERGENCE_DIR.glob("*.parquet")))
    box = _cache_generation()
    if box.get("stamp") != stamp:
        if "stamp" in box:            # not the first run: caches hold old data
            st.cache_data.clear()
        box["stamp"] = stamp


# ---------------------------------------------------------------------------
# VUS buffers
# ---------------------------------------------------------------------------

MAX_VUS_BUFFER = 256
DEFAULT_VUS_BUFFER = 128
# The buffers TSB-AD's metric files hold. The combination tables hold all 257.
TSBAD_VUS_BUFFERS = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256]


def _sticky(state_key: str, default, widget):
    """Draw a sidebar widget defaulting to whatever it was last set to.

    Streamlit gives a widget its identity from the page it is drawn on, so the
    same control on two pages is two widgets, each reverting to its default on
    navigation. Our own session key makes the pages behave as one workspace.
    """
    current = st.session_state.get(state_key, default)
    value = widget(current)
    st.session_state[state_key] = value
    return value


def vus_buffer_selector(label: str = "VUS buffer (L)",
                        continuous: bool | None = None) -> int:
    """Sidebar control for which VUS buffer every number on the page is read at.

    TSB-AD's combination tables hold all 257 buffers; metric files only have
    ten, so without the tables the slider snaps. `continuous` says whether the
    page reads the tables (default: whenever the benchmark is TSB-AD).
    """
    if continuous is None:
        continuous = is_tsb_ad()
    if not continuous:
        return _sticky("combo_buffer", DEFAULT_VUS_BUFFER, lambda current: (
            st.sidebar.select_slider(
                label, options=TSBAD_VUS_BUFFERS,
                value=min(TSBAD_VUS_BUFFERS, key=lambda b: abs(b - int(current))),
                help=("VUS-PR averages AUC-PR over buffers 0..L. L=0 is strict "
                      "pointwise; larger L forgives timing error. This "
                      "benchmark has VUS-PR at these ten buffers."),
            )))
    return _sticky("combo_buffer", DEFAULT_VUS_BUFFER, lambda current: (
        st.sidebar.slider(
            label, 0, MAX_VUS_BUFFER,
            value=int(current) if 0 <= current <= MAX_VUS_BUFFER
            else DEFAULT_VUS_BUFFER,
            help=("VUS-PR averages AUC-PR over buffers 0..L. L=0 is strict "
                  "pointwise; larger L forgives timing error. Every VUS on "
                  "this page, and the ranking used to pick the sets, is read "
                  "at this L. All 257 buffers are precomputed."),
        )))


# ---------------------------------------------------------------------------
# Combination tables (TSB-AD univariate only; built by the divergence study,
# now in archive/divergence/)
# ---------------------------------------------------------------------------

def combo_datasets(kind: str = "uni") -> list[str]:
    """Datasets whose combination shard exists. TSB-AD only; empty elsewhere."""
    return _combo_datasets(kind) if is_tsb_ad() else []


@st.cache_data
def _combo_datasets(kind: str = "uni") -> list[str]:
    shards = DIVERGENCE_DIR.glob(f"combos_{kind}_*.parquet")
    names = [s.stem.replace(f"combos_{kind}_", "") for s in shards]
    return sorted(n for n in names if n != "detectors")


def cached_combo_detectors(kind: str = "uni") -> list[str]:
    """Detector roster the d0/d1/d2 columns index into. TSB-AD only."""
    return _combo_detectors(kind) if is_tsb_ad() else []


@st.cache_data
def _combo_detectors(kind: str = "uni") -> list[str]:
    path = DIVERGENCE_DIR / f"combos_{kind}_detectors.parquet"
    if not path.exists():
        return []
    return pd.read_parquet(path)["detector"].tolist()


def cached_combos(kind: str, dataset: str, buffer: int) -> pd.DataFrame:
    """Every combination for one dataset at one buffer. TSB-AD only."""
    return _combos(kind, dataset, buffer) if is_tsb_ad() else pd.DataFrame()


@st.cache_data
def _combos(kind: str, dataset: str, buffer: int) -> pd.DataFrame:
    """Every combination for one dataset, with VUS at one buffer only.

    The shard stores all 257 buffers as separate columns precisely so this can
    read one of them: pulling the whole file would be hundreds of MB per
    dataset for a number the slider changes constantly.
    """
    path = DIVERGENCE_DIR / f"combos_{kind}_{dataset}.parquet"
    if not path.exists():
        return pd.DataFrame()
    columns = ["filename", "dataset", "k", "d0", "d1", "d2", "n_constant",
               f"vus_{buffer}"]
    frame = pd.read_parquet(path, columns=columns)
    return frame.rename(columns={f"vus_{buffer}": "vus"})


def combined_score(parser, filename: str, detectors: list[str]) -> np.ndarray | None:
    """Mean of the re-normalised scores of `detectors` on one series.

    Re-scaling to [0, 1] first is not cosmetic: SR's median maximum across the
    benchmark is 0.303, so a raw average would silently under-weight it.
    """
    vectors = []
    for detector in detectors:
        _, loaded, _ = parser.load_scores(
            detectors=[detector], filenames=[filename],
            drop_missing=False, return_filenames=True,
        )
        if not loaded or len(loaded[0]) == 0:
            return None
        score = np.asarray(loaded[0][0], dtype=np.float64).ravel()
        lo, hi = score.min(), score.max()
        vectors.append(np.zeros_like(score) if hi <= lo else (score - lo) / (hi - lo))
    return np.mean(vectors, axis=0) if vectors else None


# ---------------------------------------------------------------------------
# Plot and selections
# ---------------------------------------------------------------------------

def chart_selection(event) -> list:
    """Selected points from a plotly_chart event, as a list.

    Streamlit hands the app an object with a .selection attribute, while
    AppTest hands back the plain dict it was given. Accepting both is what
    makes the click path testable.
    """
    if event is None:
        return []
    selection = event.get("selection") if isinstance(event, dict) else \
        getattr(event, "selection", None)
    if not selection:
        return []
    points = (selection.get("points") if isinstance(selection, dict)
              else getattr(selection, "points", None))
    return list(points or [])


def extract_anomaly_segments(labels):
    """Return list of (start, end) for each contiguous anomaly segment."""
    diff = np.diff(np.concatenate([[0], labels.astype(int), [0]]))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    return list(zip(starts.tolist(), ends.tolist()))


def plot_series_plotly(
    timeseries: np.ndarray,
    anomaly_labels: np.ndarray | None,
    title: str = "",
    detector_scores: list[np.ndarray] | None = None,
    detector_names: list[str] | None = None,
    context_start: int = 0,
    show_anomalies: bool = True,
    highlight: tuple[int, int] | None = None,
) -> go.Figure:
    """Series with optional detector scores stacked underneath.

    `highlight` is an absolute (start, end) span. When given, that anomaly is
    drawn solid and every other one is faded, which is what lets a whole series
    be shown at once without losing the anomaly you actually picked.
    """
    ts_2d = timeseries if timeseries.ndim == 2 else timeseries.reshape(-1, 1)
    n_channels = ts_2d.shape[1]
    n_detectors = len(detector_scores) if detector_scores else 0
    n_rows = n_channels + n_detectors

    # A full TSB-AD series runs to 900k points, which the SVG renderer cannot
    # handle interactively. WebGL can.
    scatter = go.Scattergl if ts_2d.shape[0] > 30_000 else go.Scatter
    dim_red, bright_red = 'rgba(214,39,40,0.28)', '#d62728'

    row_heights = [3] * n_channels + [1] * n_detectors
    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.02,
    )

    T = ts_2d.shape[0]
    x = np.arange(context_start, context_start + T)

    for ch in range(n_channels):
        fig.add_trace(
            scatter(x=x, y=ts_2d[:, ch], mode='lines', line=dict(width=1.2, color='#1f77b4'),
                    name=f'C{ch}' if n_channels > 1 else 'Series', showlegend=False),
            row=ch + 1, col=1,
        )

        if anomaly_labels is not None and show_anomalies:
            segments = extract_anomaly_segments(anomaly_labels)
            for seg_start, seg_end in segments:
                seg_x = x[seg_start:seg_end]
                seg_y = ts_2d[seg_start:seg_end, ch]
                chosen = (highlight is not None
                          and seg_start + context_start == highlight[0]
                          and seg_end + context_start == highlight[1])
                # Without a highlight every anomaly is equally the subject, so
                # they all stay solid.
                color = bright_red if (chosen or highlight is None) else dim_red
                # Same renderer as the series itself, not go.Scatter. WebGL
                # traces are drawn on a canvas that sits above the SVG layer,
                # so on a series long enough to switch to Scattergl an SVG
                # overlay ends up *under* the blue line: the anomalies on the
                # 35k-point Power series were almost invisible.
                if len(seg_x) == 1:
                    fig.add_trace(
                        scatter(x=seg_x, y=seg_y, mode='markers',
                                marker=dict(size=11 if chosen else 6, color=color,
                                            line=dict(width=1.5, color='#7a0d0d')
                                            if chosen else None),
                                showlegend=False),
                        row=ch + 1, col=1,
                    )
                else:
                    fig.add_trace(
                        scatter(x=seg_x, y=seg_y, mode='lines',
                                line=dict(width=3 if chosen else 1.5, color=color),
                                showlegend=False),
                        row=ch + 1, col=1,
                    )

    for di, score in enumerate(detector_scores or []):
        name = (detector_names[di] if detector_names else f'D{di}')
        row_idx = n_channels + di + 1
        color = '#e07b00' if di == 0 else None
        fig.add_trace(
            scatter(x=x, y=score, mode='lines',
                    line=dict(width=1.2, color=color) if color else dict(width=1.2),
                    name=name, showlegend=True),
            row=row_idx, col=1,
        )
        if highlight is not None:
            # layer='above' for the same reason: a shape belongs to the SVG
            # layer, which a WebGL trace would otherwise cover completely.
            fig.add_vrect(x0=highlight[0], x1=max(highlight[1], highlight[0] + 1),
                          fillcolor=bright_red, opacity=0.18, line_width=0,
                          layer='above', row=row_idx, col=1)
        fig.update_yaxes(range=[-0.02, 1.02], title_text='', row=row_idx, col=1)

        axis_key = 'yaxis' if row_idx == 1 else f'yaxis{row_idx}'
        domain = fig.layout[axis_key].domain
        y_center = (domain[0] + domain[1]) / 2

        if ' (' in name:
            det_label, val_part = name.rsplit(' (', 1)
            ann_text = f"{det_label}<br>({val_part}"
        else:
            ann_text = name
        fig.add_annotation(
            text=ann_text,
            xref='paper', yref='paper',
            x=-0.02, y=y_center,
            xanchor='right', yanchor='middle',
            textangle=-90,
            showarrow=False,
            font=dict(size=11),
        )

    for ch in range(n_channels):
        label = f'C{ch}' if n_channels > 1 else 'Value'
        fig.update_yaxes(title_text=label, row=ch + 1, col=1)

    fig.update_layout(
        title=title,
        height=max(300, 150 * n_rows),
        margin=dict(l=80, r=20, t=50, b=40),
        font=dict(size=13),
    )
    fig.update_xaxes(title_text='Time', row=n_rows, col=1)
    return fig


TITLE = "Pyxida"
TAGLINE = "A compass for time-series anomaly detection"
ONE_SENTENCE = (
    "Jump-start your work on a correct foundation. The parser gives you the data "
    "and the evaluation, the template gives you the project, and this demo tells "
    "you what to run and where to look."
)

PAPER_TEX = REPO_ROOT / "references" / "pyxida-paper" / "main.tex"
SUMMARY_PATH = REPO_ROOT / "data" / "benchmark_summary.json"

REPO_PARSER = "https://github.com/sylligardos/pyxida"
REPO_TEMPLATE = "https://github.com/sylligardos/tsad-template"
REPO_DATA = "https://github.com/thedatumorg/TSB-AD"

# The series the Start page loads. Small enough to draw instantly, three
# anomalies of visibly different shape.
DEMO_SERIES = "001_NAB_id_1_Facility_tr_1007_1st_2014.csv"


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

# Display order and names. TSB-AD is complete; the others are shown with what
# has been computed for them (see README.md in the benchmarks root).
BENCHMARK_LABELS = {
    "tsb-ad": "TSB-AD",
    "tsb-uad": "TSB-UAD",
    "timeeval": "TimeEval",
    "tab": "TAB",
    "mtsbench": "mTSBench",
}
BENCHMARK_NOTES = {
    "tsb-ad": "Complete: every detector on every series, plus the exhaustive "
              "combination search.",
    "tsb-uad": "12 detectors, with the scores TSB-UAD ships (rounded to two "
               "decimals).",
    "timeeval": "Examples only: a few collections, 6 fast detectors. "
                "TimeEval's TSB-UAD collections are left out.",
    "tab": "Examples only: a few collections, 6 fast detectors.",
    "mtsbench": "Multivariate only. Examples: 10 collections, 5 fast detectors.",
}

# Page state that points into one benchmark and is meaningless in another.
# Dropped when the benchmark changes, so no widget is handed a value it lacks.
_PER_BENCHMARK_STATE = [
    "wb_dataset", "wb_series", "wb_pins", "wb_anomaly", "wb_combos",
    "ls_scope", "combo_dataset", "combo_series", "scope_dataset", "scope_type",
]


KIND_KEY = "demo_kind"
KIND_LABELS = {"uni": "univariate", "multi": "multivariate"}

# Widget values that have to outlive a st.switch_page. Streamlit reruns into
# the new page without the browser's widget states, and on a page change it
# then drops every widget's value -- the sidebar's benchmark included. Every
# jump into the Workbench used to land on TSB-AD, where the series it was sent
# to does not exist. A shadow copy, refreshed at the start of every run and
# written back whenever Streamlit has dropped a key, keeps them.
_PERSISTENT_STATE = [
    BENCHMARK_KEY, KIND_KEY,
    "wb_dataset", "wb_series", "wb_pins", "wb_top_n", "wb_only_scored",
    "scope_dataset", "scope_type",
]
_SHADOW_KEY = "_persisted_state"


def keep_widget_state() -> None:
    """Restore what a page switch dropped, then remember the current values.
    Called first thing on every run, before any widget is drawn."""
    shadow = st.session_state.setdefault(_SHADOW_KEY, {})
    for key in _PERSISTENT_STATE:
        if key in st.session_state:
            shadow[key] = st.session_state[key]
        elif key in shadow:
            st.session_state[key] = shadow[key]


def benchmark_label(name: str) -> str:
    return BENCHMARK_LABELS.get(name, name)


def current_kind() -> str:
    return st.session_state.get(KIND_KEY, "uni")


def has_combos(kind: str) -> bool:
    """Is there an exhaustive combination search for this benchmark and kind?
    Only TSB-AD univariate, today."""
    return is_tsb_ad() and bool(combo_datasets(kind))


def scored_series(kind: str) -> set:
    return _scored_series(current_benchmark(), kind)


@st.cache_data
def _scored_series(benchmark: str, kind: str) -> set:
    """Series with at least one detector score."""
    parser = _parser(benchmark, kind)
    stems = set()
    for detector in parser.get_detectors():
        folder = parser.scores_path / detector
        if folder.is_dir():
            stems |= {p.stem for p in folder.glob("*.npy")}
    return {f for f in parser.meta.filename if f[:-4] in stems}


def benchmark_selector() -> str:
    """The sidebar controls every page shares: which benchmark, which kind."""
    available = TSBADParser.list_benchmarks() or [DEFAULT_BENCHMARK]
    options = ([b for b in BENCHMARK_LABELS if b in available]
               + [b for b in available if b not in BENCHMARK_LABELS])
    if DEFAULT_BENCHMARK not in options:
        options.insert(0, DEFAULT_BENCHMARK)
    st.session_state.setdefault(BENCHMARK_KEY, DEFAULT_BENCHMARK)
    if st.session_state[BENCHMARK_KEY] not in options:
        st.session_state[BENCHMARK_KEY] = DEFAULT_BENCHMARK

    with st.sidebar:
        chosen = st.radio("Benchmark", options, key=BENCHMARK_KEY,
                          format_func=benchmark_label)
        st.caption(BENCHMARK_NOTES.get(chosen, ""))
        st.session_state.setdefault(KIND_KEY, "uni")
        kind = st.radio("Series", list(KIND_LABELS), key=KIND_KEY, horizontal=True,
                        format_func=KIND_LABELS.get)
        st.divider()

    where = (chosen, kind)
    if st.session_state.get("_last_view") not in (None, where):
        shadow = st.session_state.get(_SHADOW_KEY, {})
        for key in _PER_BENCHMARK_STATE:
            st.session_state.pop(key, None)
            shadow.pop(key, None)
    st.session_state["_last_view"] = where
    return chosen


def demo_series(kind: str = "uni") -> str:
    """Default series for the current benchmark: the Start page's NAB series on
    TSB-AD, otherwise the shortest scored series of NAB (or of the whole
    benchmark). Not "the first dataset": on TimeEval multivariate that is
    CATSv2, and drawing it sent 1.5 GB to the browser."""
    meta = get_parser(kind).meta
    if meta.empty:
        return None
    if is_tsb_ad() and DEMO_SERIES in set(meta.filename):
        return DEMO_SERIES
    lengths = benchmark_summary(kind).get("lengths", {})
    pool = meta[meta.dataset == "NAB"]
    pool = pool if len(pool) else meta
    scored = pool[pool.filename.isin(scored_series(kind))]
    pool = scored if len(scored) else pool
    return min(pool.filename, key=lambda f: lengths.get(f, 10 ** 12))


# ---------------------------------------------------------------------------
# Author block
# ---------------------------------------------------------------------------

FALLBACK_AUTHOR = {
    "name": "Emmanouil Sylligardos",
    "affiliation": "DI ENS, ENS, PSL Univ., CNRS, Inria",
    "location": "Paris, France",
    "email": "emmanouil.sylligardos@ens.fr",
}


@st.cache_data
def paper_author() -> dict:
    """Author, affiliation and contact, read out of the paper's LaTeX source.

    Read rather than retyped so the demo and the submission cannot drift apart.
    Falls back to the last known values if the paper is not checked out.
    """
    if not PAPER_TEX.exists():
        return FALLBACK_AUTHOR

    tex = PAPER_TEX.read_text(errors="ignore")
    name = re.search(r"\\IEEEauthorblockN\{([^}]*)\}", tex)
    block = re.search(r"\\IEEEauthorblockA\{(.*?)\n\}", tex, re.DOTALL)
    if not name or not block:
        return FALLBACK_AUTHOR

    lines = [line.strip().rstrip("\\").strip()
             for line in block.group(1).split("\\\\")]
    lines = [re.sub(r"\\textit\{([^}]*)\}", r"\1", line) for line in lines if line]
    return {
        "name": name.group(1).strip(),
        "affiliation": lines[0] if lines else FALLBACK_AUTHOR["affiliation"],
        "location": lines[1] if len(lines) > 1 else FALLBACK_AUTHOR["location"],
        "email": lines[2] if len(lines) > 2 else FALLBACK_AUTHOR["email"],
    }


# ---------------------------------------------------------------------------
# Headline numbers
# ---------------------------------------------------------------------------

def benchmark_summary(kind: str = "uni") -> dict:
    return _benchmark_summary(current_benchmark(), kind)


@st.cache_data
def _benchmark_summary(benchmark: str, kind: str = "uni") -> dict:
    """Size of the benchmark.

    TSB-AD's comes from build_summary.py: counting anomaly events means reading
    every label file, which is a minute the demo cannot spend on page load.
    Converted benchmarks have series lengths in their _source_map.csv. Anything
    not available is left out, so the page degrades to fewer numbers instead of
    an error.
    """
    if benchmark == DEFAULT_BENCHMARK and SUMMARY_PATH.exists():
        summary = json.loads(SUMMARY_PATH.read_text()).get(kind)
        if summary:
            return summary

    parser = _parser(benchmark, kind)
    meta = parser.meta
    summary = {
        "kind": kind,
        "n_series": len(meta),
        "n_datasets": meta.dataset.nunique(),
        "n_detectors": len(parser.get_detectors()),
        "n_entity_types": meta.entity_type.nunique(),
    }
    source_map = parser.path / "_source_map.csv"
    if source_map.exists():
        lengths = pd.read_csv(source_map, usecols=["file_name", "length"])
        lengths = lengths[lengths.file_name.isin(set(meta.filename))]
        summary["lengths"] = dict(zip(lengths.file_name, lengths.length.astype(int)))
        summary["n_points"] = int(lengths.length.sum())
    scores = parser.scores_path
    summary["n_scored_series"] = len({p.stem for d in parser.get_detectors()
                                      if (scores / d).is_dir()
                                      for p in (scores / d).glob("*.npy")}
                                     & {f[:-4] for f in meta.filename})
    return summary


# ---------------------------------------------------------------------------
# Solo scores, for the Landscape
# ---------------------------------------------------------------------------

def solo_scores(kind: str, buffer: int):
    """Every detector's VUS on every series, with its rank on that series.

    Where the combination search exists (TSB-AD univariate) it reads its k=1
    rows; everywhere else the metric files, which hold the same number at ten
    buffers.
    """
    if has_combos(kind):
        return _solo_scores_combos(kind, buffer)
    return _solo_scores_metrics(current_benchmark(), kind, buffer)


@st.cache_data(show_spinner="Reading solo scores ...")
def _solo_scores_metrics(benchmark: str, kind: str, buffer: int):
    metrics = _metrics(benchmark, kind)
    column = f"VUS-PR (L: {buffer})"
    if metrics.empty or column not in metrics.columns:
        return pd.DataFrame()
    parser = _parser(benchmark, kind)
    metrics = metrics[metrics["Model Name"].isin(set(parser.get_detectors()))]
    datasets = parser.meta.set_index("filename").dataset
    table = pd.DataFrame({
        "filename": metrics["File Name"].to_numpy(),
        "dataset": metrics["File Name"].map(datasets).to_numpy(),
        "detector": metrics["Model Name"].to_numpy(),
        "vus": metrics[column].to_numpy(),
    }).dropna(subset=["vus"])
    table["rank"] = table.groupby("filename").vus.rank(ascending=False, method="first")
    return table


@st.cache_data(show_spinner="Reading solo scores ...")
def _solo_scores_combos(kind: str, buffer: int):
    roster = cached_combo_detectors(kind)
    rows = []
    for dataset in combo_datasets(kind):
        frame = cached_combos(kind, dataset, buffer)
        if frame.empty:
            continue
        solo = frame[(frame.k == 1) & (frame.n_constant == 0)]
        rows.append(pd.DataFrame({
            "filename": solo.filename.to_numpy(),
            "dataset": solo.dataset.to_numpy(),
            "detector": [roster[i] for i in solo.d0],
            "vus": solo.vus.to_numpy(),
        }))
    if not rows:
        return pd.DataFrame()
    table = pd.concat(rows, ignore_index=True)
    table["rank"] = table.groupby("filename").vus.rank(ascending=False, method="first")
    return table


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------

def page_header(title: str, question: str) -> None:
    """Title plus the one question this page exists to answer."""
    st.title(title)
    st.caption(question)


def takeaway(text: str) -> None:
    """The single actionable line a page leaves the reader with.

    Every page ends with exactly one, phrased as an instruction. A page that
    cannot state one is a page that does not belong in the demo.
    """
    st.success(f"**{text}**")


def goto_workbench(filename: str,
                   detectors: list | None = None,
                   anomaly: int | None = None,
                   combos: list | None = None) -> None:
    """Send the reader to the Workbench with a series already loaded.

    Every jump in the demo goes through here, so there is one way to arrive and
    the Workbench honours one contract:

      * `detectors` **replaces** the pinned set, it never appends -- otherwise
        pins accumulate from wherever the reader has been.
      * naming detectors also drops the automatic top-N to 0. You clicked a
        pair, you get the pair; turning the slider back up is one drag.
      * a link with no detectors leaves the slider alone, or "show me this hard
        series" would land on a plot with no detectors at all.
      * `anomaly` arrives already highlighted.
      * `combos` are sets to draw as their averaged score, one extra row each --
        the ensemble a VUS was actually computed on, rather than its members.
    """
    st.session_state[WORKBENCH_KEY] = filename
    if detectors is not None:
        st.session_state[WORKBENCH_PINS_KEY] = list(detectors)
    if anomaly is not None:
        st.session_state[WORKBENCH_ANOMALY_KEY] = int(anomaly)
    if combos is not None:
        st.session_state[WORKBENCH_COMBOS_KEY] = [list(c) for c in combos]
    try:
        st.switch_page("pages/4_workbench.py")
    except Exception:
        # Only st.navigation registers page paths. Running a page on its own --
        # a headless test, or `streamlit run` on the file itself -- has no
        # registry, and the handover state is already written, so a failed jump
        # should not take the click down with it.
        pass


# ---------------------------------------------------------------------------
# Series geometry and notes
# ---------------------------------------------------------------------------

# What a link hands over. Kept separate from the widget keys the Workbench owns
# (wb_series, wb_pins, wb_top_n, wb_anomaly) so an arrival is an explicit event
# the page consumes once, rather than a silent write into live widget state.
WORKBENCH_KEY = "wb_filename"
WORKBENCH_PINS_KEY = "wb_arrival_pins"
WORKBENCH_ANOMALY_KEY = "wb_arrival_anomaly"
WORKBENCH_COMBOS_KEY = "wb_arrival_combos"
WORKBENCH_SAMPLE_KEY = "wb_arrival_sample"   # arrive on a random series

NOTES_PATH = REPO_ROOT / "demo_notes.json"


def table_selection(event) -> list:
    """Selected row indices from a st.dataframe selection event.

    The dataframe twin of chart_selection(): Streamlit hands back an object,
    AppTest a plain dict, and a click path that only works in one of them is a
    click path nobody tests.
    """
    if event is None:
        return []
    selection = (event.get("selection") if isinstance(event, dict)
                 else getattr(event, "selection", None))
    if not selection:
        return []
    rows = (selection.get("rows") if isinstance(selection, dict)
            else getattr(selection, "rows", None))
    return list(rows or [])


def anomaly_bounds(labels) -> tuple:
    """Start and end index of every contiguous run of 1s, end exclusive."""
    flags = np.asarray(labels).astype(int)
    edges = np.diff(np.r_[0, flags, 0])
    return np.where(edges == 1)[0], np.where(edges == -1)[0]


def load_notes() -> dict:
    """Every note, keyed by filename. Not cached -- the file is tiny and it is
    written from the same page that reads it."""
    if not NOTES_PATH.exists():
        return {}
    try:
        return json.loads(NOTES_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def save_note(filename: str, text: str) -> None:
    """Write or clear one series' note. Empty text removes the entry."""
    from datetime import datetime, timezone

    notes = load_notes()
    if text.strip():
        notes[filename] = {
            "note": text.strip(),
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    else:
        notes.pop(filename, None)
    NOTES_PATH.write_text(json.dumps(notes, indent=2, sort_keys=True) + "\n")
