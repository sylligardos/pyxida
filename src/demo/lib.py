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
    DEFAULT_VUS_BUFFER,
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

@st.cache_data
def benchmark_summary(kind: str = "uni") -> dict:
    """Size of the benchmark, from build_summary.py.

    Counting anomaly events means reading every label file, which is a minute
    the demo cannot spend on page load. If the file is missing the counts that
    are free (series, datasets, detectors) are still returned, so the page
    degrades to fewer numbers instead of an error.
    """
    if SUMMARY_PATH.exists():
        summary = json.loads(SUMMARY_PATH.read_text()).get(kind)
        if summary:
            return summary

    parser = get_parser(kind)
    detectors = parser.get_detectors()
    return {
        "kind": kind,
        "n_series": len(parser.meta),
        "n_datasets": parser.meta.dataset.nunique(),
        "n_detectors": len(detectors),
        "n_entity_types": parser.meta.entity_type.nunique(),
    }


# ---------------------------------------------------------------------------
# Scores, shared by Redundancy and Get started
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Reading solo scores ...")
def solo_scores(kind: str, buffer: int):
    """Every detector's VUS on every series, with its rank on that series."""
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


@st.cache_data(show_spinner="Reading combinations ...")
def set_scores(kind: str, buffer: int, k: int):
    """Every k-set's VUS on every series."""
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
