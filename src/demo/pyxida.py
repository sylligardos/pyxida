"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Pyxida -- the demo. Entry point.

Five pages telling one story: the benchmark's landscape is uneven, the
detectors you would naturally pick are redundant, so here is what to run and
the project to run it in, plus a sixth comparing benchmarks. See
references/DEMO_PLAN.md.

Every page reads the benchmark chosen in the sidebar. TSB-AD is complete; the
others are shown with what has been computed for them.

Run:
    streamlit run src/demo/pyxida.py

The exploratory app (src/app/explorer.py) is a separate, still-runnable thing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src
sys.path.insert(0, str(Path(__file__).resolve().parent))       # demo

import streamlit as st

st.set_page_config(page_title="Pyxida", page_icon="🧭", layout="wide")

from lib import benchmark_selector, drop_caches_if_data_changed

drop_caches_if_data_changed()
benchmark_selector()

pages = [
    st.Page("pages/1_start.py",       title="Start",       icon="🧭", default=True),
    st.Page("pages/2_landscape.py",   title="Landscape",   icon="🗺️"),
    st.Page("pages/3_redundancy.py",  title="Redundancy",  icon="🔁"),
    st.Page("pages/4_workbench.py",   title="Workbench",   icon="🔬"),
    st.Page("pages/5_get_started.py", title="Get started", icon="🚀"),
    st.Page("pages/6_benchmarks.py",  title="Across benchmarks", icon="⚖️"),
]
st.navigation(pages).run()
