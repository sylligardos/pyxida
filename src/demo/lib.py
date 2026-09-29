"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Shared helpers for the Pyxida demo.

Analysis helpers are imported from `app.utils` rather than copied, so a fix
lands in both apps. This module holds only what the demo itself needs: the
author block, the headline numbers, and the two conventions every page follows
(a question at the top, a takeaway at the bottom).
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import streamlit as st  # noqa: E402

from app.utils import (  # noqa: E402,F401  (re-exported for the pages)
    BENCHMARK_KEY,
    DEFAULT_BENCHMARK,
    DEFAULT_VUS_BUFFER,
    TSBAD_VUS_BUFFERS,
    TSBADParser,
    _metrics,
    _parser,
    current_benchmark,
    is_tsb_ad,
    cached_combo_detectors,
    cached_combos,
    cached_metrics,
    cached_heuristics,
    cached_pair_agreement,
    cached_solo_baseline,
    chart_selection,
    combined_score,
    combo_datasets,
    drop_caches_if_data_changed,
    get_parser,
    plot_series_plotly,
    vus_buffer_selector,
)

TITLE = "Pyxida"
TAGLINE = "A compass for time-series anomaly detection"
ONE_SENTENCE = (
    "Jump-start your work on a correct foundation. The parser gives you the data "
    "and the evaluation, the template gives you the project, and this demo tells "
    "you what to run and where to look."
)

PAPER_TEX = REPO_ROOT / "references" / "pyxida-paper" / "main.tex"
SUMMARY_PATH = REPO_ROOT / "data" / "benchmark_summary.json"

REPO_PARSER = "https://github.com/sylligardos/tsb-ad-parser"
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
}
BENCHMARK_NOTES = {
    "tsb-ad": "Complete: every detector on every series, plus the exhaustive "
              "combination search.",
    "tsb-uad": "12 detectors, with the scores TSB-UAD ships (rounded to two "
               "decimals).",
    "timeeval": "Examples only: a few collections, 6 fast detectors. "
                "TimeEval's TSB-UAD collections are left out.",
    "tab": "Examples only: a few collections, 6 fast detectors.",
}

# Page state that points into one benchmark and is meaningless in another.
# Dropped when the benchmark changes, so no widget is handed a value it lacks.
_PER_BENCHMARK_STATE = [
    "wb_dataset", "wb_series", "wb_pins", "wb_anomaly", "wb_combos",
    "ls_scope", "combo_dataset", "combo_series", "scope_dataset", "scope_type",
]


KIND_KEY = "demo_kind"
KIND_LABELS = {"uni": "univariate", "multi": "multivariate"}


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
        for key in _PER_BENCHMARK_STATE:
            st.session_state.pop(key, None)
    st.session_state["_last_view"] = where
    return chosen


def demo_series(kind: str = "uni") -> str:
    """Default series for the current benchmark: the Start page's NAB series on
    TSB-AD, otherwise the shortest series of NAB (or of the first dataset)."""
    meta = get_parser(kind).meta
    if meta.empty:
        return None
    if is_tsb_ad() and DEMO_SERIES in set(meta.filename):
        return DEMO_SERIES
    lengths = benchmark_summary(kind).get("lengths", {})
    pool = meta[meta.dataset == "NAB"]
    pool = pool if len(pool) else meta[meta.dataset == meta.dataset.iloc[0]]
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
        import pandas as pd
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
# Scores, shared by Redundancy and Get started
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
    import pandas as pd

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
    import pandas as pd

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


def set_scores(kind: str, buffer: int, k: int):
    """Every k-set's VUS on every series. TSB-AD only; empty elsewhere."""
    if not has_combos(kind):
        import pandas as pd
        return pd.DataFrame()
    return _set_scores(kind, buffer, k)


@st.cache_data(show_spinner="Reading combinations ...")
def _set_scores(kind: str, buffer: int, k: int):
    import pandas as pd

    roster = cached_combo_detectors(kind)
    members = [f"d{i}" for i in range(k)]
    rows = []
    for dataset in combo_datasets(kind):
        frame = cached_combos(kind, dataset, buffer)
        if frame.empty:
            continue
        sets = frame[(frame.k == k) & (frame.n_constant == 0)]
        if sets.empty:
            continue
        rows.append(pd.DataFrame({
            "filename": sets.filename.to_numpy(),
            "dataset": sets.dataset.to_numpy(),
            "combination": [" + ".join(roster[i] for i in indices)
                            for indices in sets[members].to_numpy()],
            "vus": sets.vus.to_numpy(),
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


MIN_COVERAGE = 0.5     # a recommendation has to apply to most of the scope


def coverage_of(frame, by: str):
    """Share of the scope's series where each `by` value was actually scored.

    A detector or a set is only scored where no member emits a constant, and
    POLY is constant on 40% of the benchmark. Without this, the global
    recommendation is "start with POLY" -- ranked on the 60% of series that
    happen to suit it.
    """
    in_scope = frame.groupby("dataset", observed=True).filename.nunique()
    per_dataset = (frame.groupby([by, "dataset"], observed=True)
                   .filename.nunique() / in_scope)
    return per_dataset.groupby(level=0, observed=True).mean().rename("coverage")


def ranked(frame, by: str, columns: list, min_coverage: float = MIN_COVERAGE):
    """Macro-averaged leaderboard with the thin coverage dropped."""
    board = macro(frame, by, columns).join(coverage_of(frame, by))
    return board[board.coverage >= min_coverage]


def macro(frame, by: str, columns: list):
    """Mean of `columns` grouped by `by`, every dataset counting once.

    YAHOO is 30% of the benchmark's series and UCR 26%, so a plain mean over a
    multi-dataset scope is a recommendation for those two. Averaging within
    each dataset first and then across datasets gives each one an equal vote.
    Inside a single dataset there is nothing to balance, so it is a plain mean.
    """
    if frame.dataset.nunique() > 1:
        per_dataset = frame.groupby([by, "dataset"], observed=True)[columns].mean()
        return per_dataset.groupby(level=0, observed=True).mean()
    return frame.groupby(by, observed=True)[columns].mean()


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
    """Start and end index of every contiguous run of 1s, end exclusive.

    Written here rather than imported from divergence/utils.py: that module
    shares its name with app/utils.py, and importing both by name has bitten
    this repo before.
    """
    import numpy as np

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


def stub(title: str, question: str, plan: str) -> None:
    """Placeholder for a page that is not built yet.

    The demo is built one page at a time, but navigation has to work from the
    first commit -- a link into a page that does not exist is worse than a link
    into an honest placeholder.
    """
    page_header(title, question)
    st.info(f"Not built yet. Planned: {plan}")
