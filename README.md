# TSB-AD

Python parser for the **TSB-AD** benchmark (Time Series Benchmark for Anomaly Detection), a large-scale evaluation suite for time series anomaly detection published at NeurIPS 2024.

## What is TSB-AD?

TSB-AD ships with:

- **Raw time series** with ground-truth anomaly labels
- **Pre-computed anomaly scores** for 30+ detectors
- **Evaluation metrics** (VUS-PR, AUC-ROC, etc.) per detector and series
- **Runtime** measurements per detector
- **Official train/eval/label splits**

Both **univariate** (`uni`) and **multivariate** (`multi`) variants are included.

See the [official TSB-AD repository](https://github.com/thedatumorg/TSB-AD) for the full benchmark description and data downloads.

This repo provides:

- A **Python parser** (`tsbadparser`) for loading time series, scores, metrics, and splits
- An **interactive Streamlit explorer app** for inspecting results, comparing detectors, and browsing anomalies

```bash
streamlit run src/app/explorer.py
```

## Repository layout

```
tsb-ad-parser/
├── data/
│   ├── raw/uni|multi/                    # Raw time series CSVs (values + label column)  [gitignored]
│   ├── scores/uni|multi/                 # Per-detector .npy score files                 [gitignored]
│   ├── metrics/uni|multi/                # Per-detector metric CSVs                      [gitignored]
│   ├── runtime/uni|multi/                # Per-detector runtime CSVs                     [gitignored]
│   ├── splits/                           # Official TSB-AD-U / TSB-AD-M split CSVs
│   ├── anomaly_features_uni.parquet      # Precomputed anomaly features (uni)            [gitignored]
│   └── anomaly_features_multi.parquet    # Precomputed anomaly features (multi)          [gitignored]
├── src/
│   ├── app/                              # Streamlit explorer app
│   │   ├── explorer.py                   # Entry point
│   │   ├── precompute.py                 # One-time feature precomputation
│   │   ├── utils.py                      # Shared helpers and plot utilities
│   │   └── pages/
│   │       ├── global_summary.py         # Benchmark-wide performance overview
│   │       ├── edge_cases.py             # Hardest / easiest series viewer
│   │       ├── series_browser.py         # Random sampling + saved-series review
│   │       └── anomaly_clusters.py       # Per-anomaly clustering and inspection
│   └── tsbadparser/                      # The parser package
├── tests/                                # Parser unit tests
├── saved_series.json                     # User-bookmarked series
├── environment.yml                       # Conda environment
└── pyproject.toml                        # Makes tsbadparser pip-installable
```

The bulk of the data (raw/, scores/, metrics/, runtime/) is gitignored because of its size. Only the split CSVs are tracked.

## Setup

### 1. Clone this repo

```bash
git clone https://github.com/sylligardos/tsb-ad-parser.git
cd tsb_ad_parser
```

### 2. Download the benchmark data

Download the data from the [official TSB-AD repository](https://github.com/thedatumorg/TSB-AD) and place the files under `data/` following the structure above.

### 3. Create the environment

```bash
conda env create -f environment.yml
conda activate tsbad
```

This installs `tsbadparser` as an editable package. `from tsbadparser import TSBADParser` is available in any script run under the `tsbad` environment, without any extra install step.

## Explorer app

An interactive Streamlit app for exploring the benchmark. It has four pages:

| Page | What it shows |
|------|---------------|
| **Global Summary** | Benchmark-wide box plots and heatmaps (per dataset, per entity type) for any metric, from both a time-series and a detector perspective |
| **Edge Cases** | The hardest and easiest series (or detector edge cases) for a chosen metric, with a Prev / Next viewer |
| **Series Browser** | Randomly sample or review bookmarked series; shows anomaly labels and detector scores side by side |
| **Anomaly Clusters** | Per-anomaly detectability ranking, grouping by best detector, and PCA + KMeans clustering with click-to-inspect |

A **Kind** selector (`uni` / `multi`) is present in the sidebar of every page.

### 1. Precompute anomaly features (one-time, per kind)

The Anomaly Clusters page requires a precomputed parquet file. Run once per kind you want to explore:

```bash
# from the project root
python src/app/precompute.py --kind uni   # → data/anomaly_features_uni.parquet
python src/app/precompute.py --kind multi # → data/anomaly_features_multi.parquet
```

### 2. Launch the app

```bash
# from the project root
streamlit run src/app/explorer.py
```

---

## Usage

```python
from tsbadparser import TSBADParser

# Looks for data/ next to this repo by default
parser = TSBADParser(kind="uni")   # or kind="multi"

# Metadata
print(parser.get_datasets())    # ['NAB', 'YAHOO', ...]
print(parser.get_detectors())   # ['AnomalyTransformer', 'IForest', ...]

# Load time series
fnames, timeseries, labels = parser.load_timeseries(dataset=["NAB"])

# Load anomaly scores
scores, bad = parser.load_scores(detectors=["IForest", "LOF"], filenames=fnames)
# scores[i] has shape (n_detectors, T)

# Load scores and drop problematic files (mutates fnames/timeseries/labels in-place)
fnames, timeseries, labels = parser.load_timeseries(dataset=["NAB"])
scores, bad = parser.load_scores_and_delete(fnames, timeseries, labels)

# Metrics and runtime
df_metrics = parser.load_metrics()
df_runtime = parser.load_runtime()

# Official splits
splits = parser.load_splits()   # {'eval': [...], 'label': [...]}

# Visualize
parser.visualize_timeseries(
    timeseries[0],
    anomaly_labels=labels[0],
    title=fnames[0],
    detector_scores=[scores[0][0], scores[0][1]],
    detector_names=["IForest", "LOF"],
)
```

## Benchmark citation

```bibtex
@article{liu2024elephant,
  title     = {The elephant in the room: Towards a reliable time-series anomaly detection benchmark},
  author    = {Liu, Qinghua and Paparrizos, John},
  journal   = {Advances in Neural Information Processing Systems},
  volume    = {37},
  pages     = {108231--108261},
  year      = {2024}
}
```

## Credits

- **Benchmark data**: Qinghua Liu & John Paparrizos (NeurIPS 2024)
- **This parser**: Emmanouil Sylligardos, 3rd year PhD, Paris, 2026
