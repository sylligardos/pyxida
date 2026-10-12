# Pyxida

The demo behind the ICDE 2027 submission *Pyxida*: an interactive tour of a
time-series anomaly detection benchmark (which datasets and anomaly types are
still open, and what the detectors actually did on any one series), and
**Needle**, the booth game where a person marks anomalies against a team of
detectors.

It runs on TSB-AD out of the box, and on any data in the format below.

## Layout

```
pyxida/
├── app/            the demo (Streamlit): main.py, pages/, lib.py
│   ├── parser.py   reads a benchmark in the data format
│   └── convert/    converters into the format (TSB-UAD, TAB, TimeEval, mTSBench)
├── game/           Needle, the booth game (Starlette + vanilla JS); see game/README.md
├── scripts/        produce the data: run detectors, compute metrics, build the summary
├── data/           the data, in the format (links into the benchmarks root; see below)
├── tests/
└── archive/        earlier work, kept but not maintained; see archive/README.md
```

## Run

```bash
conda env create -f environment.yml
conda activate tsbad

streamlit run app/main.py          # the demo, http://localhost:8501
python game/make_dev_pack.py       # once: a synthetic pack for Needle
python game/server.py              # the game, http://localhost:8000
```

Everything is run from the repo root. `pytest tests` runs the parser and
game tests.

## Data format

One folder per benchmark. Univariate series go under `uni`, multivariate
under `multi`.

```
<benchmark>/
├── raw/{uni,multi}/<file>.csv                 value column(s), then a binary `Label` column
├── scores/{uni,multi}/<Detector>/<file>.npy   one anomaly score per timestamp
├── metrics/{uni,multi}/<Detector>.csv         one row per series: File Name, Model Name, AUC-PR, VUS-PR (L: 0..256)
├── runtime/{uni,multi}/<Detector>.csv         optional: wall-clock per series
└── splits/{U,M}-{Eval,Label}.csv              optional: which series are for evaluation
```

A file is named `<num>_<Dataset>_id_<k>_<Domain>_tr_<train>_1st_<first>.csv`:
its number, the collection it comes from, its index in that collection, a
domain tag, the length of the train prefix (`tr_0` when there is none) and the
index of the first anomaly. No `_` inside a field.

This is TSB-AD's layout ([Liu & Paparrizos, NeurIPS 2024](https://github.com/thedatumorg/TSB-AD)),
unchanged, so TSB-AD drops in as is.

### Where the data lives

Benchmarks sit side by side in one folder, `$TSAD_BENCHMARKS` (default
`~/Documents/tsad-benchmarks`), one sub-folder each. The repo's `data/` is
TSB-AD: `raw/`, `scores/`, `metrics/` and `runtime/` are links into
`$TSAD_BENCHMARKS/tsb-ad/` (gitignored), and only `splits/` and
`benchmark_summary.json` are tracked.

```bash
for d in raw scores metrics runtime; do ln -s ~/Documents/tsad-benchmarks/tsb-ad/$d data/$d; done
```

Any other folder in the format loads by name or by path:

```python
from app.parser import TSBADParser
TSBADParser.list_benchmarks()                      # ['mtsbench', 'tab', 'timeeval', 'tsb-ad', 'tsb-uad']
parser = TSBADParser(benchmark="tab", kind="multi")
parser = TSBADParser("/path/to/a/benchmark", kind="uni")
```

## Run it on your data

1. **Convert.** Write your series as `raw/uni/<file>.csv` (or `multi`) in the
   format above. `app/convert/` has one module per benchmark we converted;
   `tab.py` is the shortest to copy. `common.py` does the validation, the
   numbering and the bookkeeping.
2. **Score.** `scripts/run_detectors.py` runs TSB-AD's detectors on a
   benchmark and writes `scores/`; `scripts/compute_metrics.py` turns scores
   into `metrics/`.
3. **Open.** Put the folder under `$TSAD_BENCHMARKS` and pick it in the
   demo's sidebar. The Workbench shows every series with at least one score;
   the Landscape needs metrics.

## Credits

- Benchmark data: Qinghua Liu and John Paparrizos, *The elephant in the room:
  Towards a reliable time-series anomaly detection benchmark*, NeurIPS 2024.
- Pyxida and Needle: Emmanouil Sylligardos, 3rd year PhD, Paris, 2026.
