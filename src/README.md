# src/

Contains the `tsbadparser` package and the Streamlit explorer app.

```
src/
├── app/                   # Streamlit explorer (run from project root)
│   ├── explorer.py        # Entry point: streamlit run src/app/explorer.py
│   ├── precompute.py      # One-time anomaly feature builder
│   ├── utils.py           # Shared helpers, cached loaders, plot utilities
│   └── pages/
│       ├── global_summary.py
│       ├── edge_cases.py
│       ├── series_browser.py
│       └── anomaly_clusters.py
└── tsbadparser/           # pip-installable parser for the TSB-AD benchmark
    ├── __init__.py
    └── parser.py
```

Install the parser from the repo root:
```bash
pip install -e .
```
