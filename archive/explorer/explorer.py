import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))   # pages import `utils` directly

import streamlit as st

st.set_page_config(page_title="TSB-AD Explorer", layout="wide")

from utils import drop_caches_if_data_changed

drop_caches_if_data_changed()

pages = {
    "Benchmark": [
        st.Page("pages/global_summary.py", title="Global Summary"),
        st.Page("pages/edge_cases.py",     title="Edge Cases"),
    ],
    "Series": [
        st.Page("pages/series_browser.py", title="Series Browser"),
    ],
    "Anomalies": [
        st.Page("pages/anomaly_rank.py", title="Hardest & Easiest"),
        st.Page("pages/anomaly_detectors.py", title="Which Detector Wins"),
        st.Page("pages/anomaly_clusters.py", title="Clusters"),
    ],
    "Divergence": [
        st.Page("pages/divergence_agreement.py", title="Agreement (scores)"),
        st.Page("pages/anomaly_agreement.py", title="Agreement (anomalies)"),
        st.Page("pages/divergence_inspect.py", title="Where They Split"),
    ],
    "Combinations": [
        st.Page("pages/combinations_overview.py", title="Overview"),
        st.Page("pages/combinations_datasets.py", title="By Dataset"),
        st.Page("pages/combinations.py", title="Inspect a Series"),
    ],
}
st.navigation(pages).run()
