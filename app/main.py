"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Pyxida -- the demo. Entry point.

Three pages: Start, Landscape (which datasets and anomaly types are still
open) and Workbench (one series, its labels and the detectors' scores). The
Needle game (game/) is the fourth part of the demo and runs as its own server.

Every page reads the benchmark chosen in the sidebar: any folder in the data
format under $TSAD_BENCHMARKS, or the repo's data/ for TSB-AD.

Run, from the repo root:
    streamlit run app/main.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root

import streamlit as st

st.set_page_config(page_title="Pyxida", page_icon="🧭", layout="wide")

from app.lib import benchmark_selector, drop_caches_if_data_changed, keep_widget_state

keep_widget_state()
drop_caches_if_data_changed()
benchmark_selector()

pages = [
    st.Page("pages/1_start.py",       title="Start",       icon="🧭", default=True),
    st.Page("pages/2_landscape.py",   title="Landscape",   icon="🗺️"),
    st.Page("pages/4_workbench.py",   title="Workbench",   icon="🔬"),
]
st.navigation(pages).run()
