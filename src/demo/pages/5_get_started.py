"""Get started: the three commands, and what to run once they finish.

The recommendation is computed exactly as on the Redundancy page -- same
functions, same macro-average -- so the two pages cannot tell a reader
different things.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import (
    REPO_DATA,
    REPO_PARSER,
    REPO_TEMPLATE,
    benchmark_label,
    KIND_LABELS,
    current_benchmark,
    current_kind,
    get_parser,
    has_combos,
    page_header,
    ranked,
    set_scores,
    solo_scores,
    takeaway,
    vus_buffer_selector,
)

KIND = current_kind()
MIN_COVERAGE = 0.5

page_header("🚀 Get started", "How do I begin, right now?")

# ---------------------------------------------------------------------------
# What each piece is
# ---------------------------------------------------------------------------

st.markdown(
    f"""
| | what it is | you do |
|---|---|---|
| [**tsb-ad-parser**]({REPO_PARSER}) | the data and the loaders, plus every detector's scores | `pip install -e` |
| [**tsad-template**]({REPO_TEMPLATE}) | a TSAD project that already runs: conda env, SLURM scripts, a working `src/main.py` | copy the directory |
| [**TSB-AD**]({REPO_DATA}) | where the benchmark itself comes from | point `TSB_AD_DATA` at it |
"""
)

st.subheader("Three commands")
st.code(
    f"""git clone {REPO_TEMPLATE} my-project
conda env create -f my-project/environment.yml --name my-project
pip install -e /path/to/tsb-ad-parser""",
    language="bash",
)
st.caption(
    "The parser is deliberately not in `environment.yml`: installing it "
    "editable from a clone means a fix to the parser reaches your experiments "
    "without a reinstall. Then `export TSB_AD_DATA=/path/to/TSB-AD/data` and "
    "`python src/main.py` loads and plots real series before you have written "
    "anything."
)

st.divider()

# ---------------------------------------------------------------------------
# What to run
# ---------------------------------------------------------------------------

st.subheader("What to run on your data")

if not has_combos(KIND):
    st.info(
        f"The recommendation comes from the exhaustive search over pairs of "
        f"detectors, run on TSB-AD univariate only. Switch the sidebar to "
        f"TSB-AD, univariate, to see it. "
        f"(Current: {benchmark_label(current_benchmark())}, {KIND_LABELS[KIND]}.)"
    )
    st.stop()

buffer = vus_buffer_selector()
solo = solo_scores(KIND, buffer)
sets = set_scores(KIND, buffer, 2)

if solo.empty or sets.empty:
    st.info("No combination shards yet, so there is nothing to recommend.")
    st.stop()

types = get_parser(KIND).meta.reset_index()[["filename", "entity_type"]]
solo = solo.merge(types, on="filename", how="left")
sets = sets.merge(types, on="filename", how="left")

left, right = st.columns(2)
datasets = ["All datasets"] + sorted(sets.dataset.unique())
entity_types = ["All types"] + sorted(sets.entity_type.dropna().unique())
dataset_scope = left.selectbox("Closest dataset", datasets, key="scope_dataset")
type_scope = right.selectbox("Your data looks like", entity_types, key="scope_type")


def scope(frame):
    if dataset_scope != "All datasets":
        frame = frame[frame.dataset == dataset_scope]
    if type_scope != "All types":
        frame = frame[frame.entity_type == type_scope]
    return frame


scoped_solo, scoped_sets = scope(solo), scope(sets)

if scoped_solo.empty or scoped_sets.empty:
    st.info("No series match that scope.")
    st.stop()

singles = ranked(scoped_solo, "detector", ["vus"]).sort_values("vus", ascending=False)
pairs = ranked(scoped_sets, "combination", ["vus"]).sort_values("vus", ascending=False)

if singles.empty:
    st.info("No detector covers enough of this scope.")
    st.stop()
single_name = str(singles.index[0])
single_vus = float(singles.vus.iloc[0])

pair_name = str(pairs.index[0]) if len(pairs) else None
pair_vus = float(pairs.vus.iloc[0]) if len(pairs) else float("nan")
gain = pair_vus - single_vus
scope_label = (type_scope if type_scope != "All types"
               else dataset_scope if dataset_scope != "All datasets"
               else "the whole benchmark")

columns = st.columns(3)
columns[0].metric("Start with", single_name, help=f"Mean VUS-PR {single_vus:.3f}")
columns[1].metric("Best pair", pair_name or "--",
                  delta=f"{gain:+.3f} vs the single")
columns[2].metric("Series behind this", f"{scoped_sets.filename.nunique():,}")

if gain > 0.01:
    st.success(
        f"**On {scope_label}: start with `{single_name}` ({single_vus:.3f}). "
        f"If you can afford two detectors, `{pair_name}` gets {gain:+.3f}.**"
    )
else:
    st.success(
        f"**On {scope_label}: run `{single_name}` alone ({single_vus:.3f}). "
        f"No pair beats it -- the best is {pair_vus:.3f}. Spend the second "
        f"detector's runtime somewhere else.**"
    )
st.caption(
    "Every dataset counts once in that average, so the recommendation is not "
    "just a recommendation for YAHOO and UCR, which are 56% of the benchmark's "
    "series. Both numbers are read at the L in the sidebar, and they are the "
    "same ones the Redundancy page ranks with."
)

st.divider()

# ---------------------------------------------------------------------------
# The code
# ---------------------------------------------------------------------------

st.subheader("The first thing to write")
recommended = [single_name] + (pair_name.split(" + ") if pair_name else [])
st.code(
    f'''from tsbadparser import TSBADParser

parser = TSBADParser(path="data", kind="uni")

# Where this benchmark stands on data like yours.
baseline = {sorted(set(recommended))}
names, series, labels = parser.load_timeseries(dataset=["{
    dataset_scope if dataset_scope != "All datasets" else "NAB"}"])
scores = parser.load_scores(detectors=baseline, filenames=names)

# Now your own detector, on the same series, scored the same way.
my_score = my_detector(series[0])

# VUS-PR lives in TSB-AD itself -- check the import against your version:
# {REPO_DATA}
''',
    language="python",
)
st.caption(
    "The parser calls are the ones this demo runs. The evaluation line is not: "
    "TSB-AD is not installed here, so rather than print an import we have not "
    "executed, it points at the repository that owns the metric."
)

takeaway("Three commands and you are running experiments.")
