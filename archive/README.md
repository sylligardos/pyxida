# archive/

Earlier work, parked when the repo was reorganised around the demo
(October 2026). Nothing here is maintained or wired into the live code; the
paths and imports inside are the old ones (`src/...`, `tsbadparser`). To run
any of it as it was, check out the tag `v0-explorer`.

| Folder | What it was |
| --- | --- |
| `explorer/` | The first Streamlit app, `src/app/`: twelve exploratory pages (global summary, edge cases, series browser, anomaly clusters, agreement, combinations) and `utils.py`, the helpers both apps shared. The demo's `app/lib.py` now carries the ones it uses. |
| `divergence/` | The study pipeline, `src/divergence/`: four steps that build the tables in `data/divergence/` (per-anomaly detection, pairwise agreement, the exhaustive combination search, and the heuristics). The demo's Workbench and the game's `make_tiers.py` and `pick_team.py` still read those tables; the pipeline that builds them lives here. |
| `demo-pages/` | The three demo pages dropped on 2026-10-12: Redundancy, Get started, Across benchmarks. Their helpers (`set_scores`, `ranked`, `macro`, `coverage_of`, `scope_selectbox`, `stub`) were in `src/demo/lib.py` at the tag. |
| `pyproject.toml` | The parser used to be pip-installable as `tsbadparser`. It is now `app/parser.py`, imported from the repo root. |
| `src-README.md`, `data-README.md` | The old per-folder READMEs, folded into the root README. |
