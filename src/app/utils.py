import sys
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from tsbadparser import TSBADParser


VALID_METRICS = [
    'AUC-PR',
    'VUS-PR (L: 0)', 'VUS-PR (L: 1)', 'VUS-PR (L: 2)', 'VUS-PR (L: 4)',
    'VUS-PR (L: 8)', 'VUS-PR (L: 16)', 'VUS-PR (L: 32)', 'VUS-PR (L: 64)',
    'VUS-PR (L: 128)', 'VUS-PR (L: 256)',
]
DEFAULT_METRIC = 'VUS-PR (L: 128)'

# Superseded. compute_detectability() below sweeps absolute score thresholds,
# but detector scores are min-max normalised to [0, 1] with wildly different
# distributions, so `score >= 0.5` means "very confident" for one detector and
# "below average" for another -- the resulting numbers are not comparable
# between detectors. src/divergence/step2_detection.py replaces this with a
# rank-based measure. Kept only so precompute.py still runs.
DETECTABILITY_THRESHOLDS = np.linspace(0, 1, 21)
DETECTABILITY_BUFFERS = [0, 4, 16, 64, 128]

SAVED_FILE = Path(__file__).parent.parent.parent / 'saved_series.json'


# ---------------------------------------------------------------------------
# Kind selector + cached parser + data loaders
# ---------------------------------------------------------------------------

def get_kind() -> str:
    return st.sidebar.selectbox("Kind", ["uni", "multi"], key="kind_selector")


# ---------------------------------------------------------------------------
# Which benchmark
# ---------------------------------------------------------------------------
# The demo can show any benchmark in the common format. The choice lives in
# st.session_state[BENCHMARK_KEY] (set by the demo's sidebar); without it,
# everything is TSB-AD, which keeps the exploratory app unchanged.
#
# Every cached loader takes the benchmark as an argument. Reading the session
# inside a cached function would freeze the first benchmark into the cache.

BENCHMARK_KEY = 'benchmark'
DEFAULT_BENCHMARK = 'tsb-ad'

# Collections a benchmark ships that the demo leaves out. TimeEval's download
# includes 12k TSB-UAD series that are not in TimeEval's own index or paper,
# and they would be 93% of "TimeEval".
HIDDEN_DATASETS = {
    'timeeval': {'TSB-UAD-artificial', 'TSB-UAD-synthetic'},
}


def current_benchmark() -> str:
    return st.session_state.get(BENCHMARK_KEY, DEFAULT_BENCHMARK)


def is_tsb_ad() -> bool:
    """Only TSB-AD has the combination tables in data/divergence."""
    return current_benchmark() == DEFAULT_BENCHMARK


@st.cache_resource
def _parser(benchmark: str, kind: str) -> TSBADParser:
    if benchmark == DEFAULT_BENCHMARK:
        parser = TSBADParser(path='data', kind=kind)
    else:
        parser = TSBADParser(benchmark=benchmark, kind=kind)
    hidden = HIDDEN_DATASETS.get(benchmark)
    if hidden:
        parser.meta = parser.meta[~parser.meta.dataset.isin(hidden)]
    return parser


def get_parser(kind: str = 'uni') -> TSBADParser:
    return _parser(current_benchmark(), kind)


@st.cache_data
def _metrics(benchmark: str, kind: str) -> pd.DataFrame:
    parser = _parser(benchmark, kind)
    metrics = parser.load_metrics(models=parser.get_all_models())
    if metrics.empty:
        return metrics
    return metrics[metrics['File Name'].isin(set(parser.meta.filename))]


def cached_metrics(kind: str = 'uni') -> pd.DataFrame:
    return _metrics(current_benchmark(), kind)


@st.cache_data
def _runtime(benchmark: str, kind: str) -> pd.DataFrame:
    parser = _parser(benchmark, kind)
    return parser.load_runtime(models=parser.get_all_models())


def cached_runtime(kind: str = 'uni') -> pd.DataFrame:
    return _runtime(current_benchmark(), kind)


def cached_meta(kind: str = 'uni') -> pd.DataFrame:
    return get_parser(kind).meta.reset_index()


DIVERGENCE_DIR = Path(__file__).parent.parent.parent / 'data' / 'divergence'


@st.cache_resource
def _cache_generation() -> dict:
    """Process-wide box remembering which data the caches were filled from."""
    return {}


def drop_caches_if_data_changed() -> None:
    """Clear every @st.cache_data if the divergence tables were rebuilt.

    The app usually outlives the pipeline: a step is re-run while the server
    is up, and every cached frame then describes a file that no longer exists
    on disk. That is not a stale number, it is a crash -- rebuilding step 2 at
    different buffers left `cached_detection` holding columns the pages then
    asked for by name (KeyError: 'd2'). Checked once per rerun in explorer.py.
    """
    stamp = tuple(sorted((p.name, p.stat().st_mtime)
                         for p in DIVERGENCE_DIR.glob('*.parquet')))
    box = _cache_generation()
    if box.get('stamp') != stamp:
        if 'stamp' in box:            # not the first run: caches hold old data
            st.cache_data.clear()
        box['stamp'] = stamp

# Tolerance windows the agreement table was built at (see src/divergence/utils.py).
# w1 is pointwise; larger windows credit a detector that fires nearby, the same
# way VUS-PR credits a detection inside its buffer.
WINDOWS = [1, 4, 16, 64, 128, 256]
DEFAULT_WINDOW = 64


# Buffers the detection table was built at (see src/divergence/utils.py).
BUFFERS = [0, 1, 2, 4, 8, 16, 32, 64]
# Buffer 0 by default. Detection density is a ramp-weighted mean percentile
# over the dilated anomaly, so on a length-1 anomaly -- 77.5% of TSB-AD-U --
# widening the window leaves one informative point among 2b+1, and even a
# perfect detector falls from 0.97 to 0.48 by buffer 16. Slack is worth having
# when a detector fires beside an anomaly rather than on it, but it has to be
# chosen deliberately rather than inherited from a default.
DEFAULT_BUFFER = 0


# Detection density is a mean percentile, so a detector that ignores an anomaly
# still scores about 0.5 and almost nothing scores exactly 0. Both "did it
# respond" and "did anything solve this" have to be read against chance rather
# than against zero, and they need different bars.
#
#   0.5  chance. Above it the detector responded at all.
#   0.9  a strong response. With 32 detectors at least one clears 0.5 on every
#        single anomaly in the benchmark, so 0.5 cannot answer "did anything
#        find this". At 0.9 the answer is 1.6% of anomalies; at 0.95 it is 8%
#        and at 0.99 it is 51%, which measures the bar rather than the data.
RESPONSE_THRESHOLD = 0.5
STRONG_RESPONSE = 0.9


def buffer_selector(label: str = 'Detection buffer') -> int:
    """Sidebar control for how much timing slack a detector gets credit for."""
    return st.sidebar.select_slider(
        label, options=BUFFERS, value=DEFAULT_BUFFER,
        format_func=lambda b: 'on the anomaly' if b == 0 else f'+/- {b} pts',
        help=('How far from an anomaly a detector still earns credit, ramped '
              'down with distance as in VUS. Chance is 0.5 at every buffer, '
              'but a wider window on a short anomaly is mostly normal points, '
              'so every detector is pulled towards 0.5. Compare detectors at '
              'one buffer, not values across buffers.'),
    )


@st.cache_data
def cached_detection(kind: str = 'uni') -> pd.DataFrame:
    """Step 2 output: per-anomaly detection density for every detector (long).

    Empty DataFrame if the file has not been built yet, so pages can show
    instructions instead of raising.
    """
    path = DIVERGENCE_DIR / f'detection_{kind}.parquet'
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def density_column(long: pd.DataFrame, buffer: int) -> str:
    """Name of the density column for a buffer, checked against the table.

    BUFFERS here has to match the list step 2 was run with. When it does not,
    the honest failure is a message naming the two lists, not a KeyError from
    inside pivot_table.
    """
    column = f'd{buffer}'
    if column not in long.columns:
        built = [c[1:] for c in long.columns if c.startswith('d') and c[1:].isdigit()]
        raise KeyError(
            f'detection table has no buffer {buffer}. It was built at '
            f'[{", ".join(built)}]; the app expects {BUFFERS}. Re-run '
            f'src/divergence/step2_detection.py, or fix BUFFERS.')
    return column


@st.cache_data
def cached_detection_wide(kind: str = 'uni', buffer: int = DEFAULT_BUFFER) -> pd.DataFrame:
    """One row per anomaly, one column per detector, at a chosen buffer.

    Adds entity_type from the parser, plus `overall_detectability` (mean across
    detectors) and `best_detector` (argmax). Both of those are only meaningful
    because density is rank-based: the previous version compared raw scores at
    absolute thresholds, which are not comparable between detectors.
    """
    long = cached_detection(kind)
    if long.empty:
        return pd.DataFrame()

    keys = ['filename', 'dataset', 'anomaly_idx', 'start', 'end', 'length',
            'anomaly_rate', 'ts_length']
    keys = [k for k in keys if k in long.columns]

    wide = long.pivot_table(index=keys, columns='detector',
                            values=density_column(long, buffer)).reset_index()
    wide.columns.name = None

    chance_col = f'chance{buffer}'
    if chance_col in long.columns:
        chance = long.groupby(keys, observed=True)[chance_col].first().reset_index()
        wide = wide.merge(chance, on=keys, how='left').rename(columns={chance_col: 'chance'})

    detectors = [c for c in wide.columns if c not in keys and c != 'chance']
    wide['overall_detectability'] = wide[detectors].mean(axis=1)

    # An anomaly nothing responded to has no winner. Density is a mean
    # percentile now, so "nothing responded" means every detector sat at or
    # below chance rather than at zero; testing against 0 would hand every such
    # anomaly to whichever detector happened to be a hair above the rest.
    best = wide[detectors].idxmax(axis=1)
    strongest = wide[detectors].max(axis=1)
    wide['best_detector'] = best.where(strongest > RESPONSE_THRESHOLD, "none")
    wide['best_density'] = strongest

    entity = cached_meta(kind)[['filename', 'entity_type']]
    return wide.merge(entity, on='filename', how='left')


def anomaly_page_setup(need_clusters: bool = False):
    """Shared sidebar, data load and filtering for the Anomalies pages.

    Every Anomalies page asks the same three questions -- which kind, how much
    timing slack, and which datasets -- so they are answered in one place and
    the pages stay comparable when you switch between them.

    Returns:
        (kind, buffer, df_all, df, detectors), or None after rendering a
        build-instructions message when the table is missing.
    """
    kind = get_kind()
    buffer = buffer_selector()

    df_all = cached_detection_wide(kind, buffer)
    if df_all.empty:
        st.warning(
            f"No detection table for kind = `{kind}`.\n\n"
            f"Build it first:\n\n"
            f"```bash\npython src/divergence/step2_detection.py --kind {kind}\n```"
        )
        return None

    detectors = detection_detectors(df_all)

    with st.sidebar:
        datasets = sorted(df_all['dataset'].dropna().unique().tolist())
        entities = sorted(df_all['entity_type'].dropna().unique().tolist())
        sel_datasets = st.multiselect("Dataset", datasets, default=datasets)
        sel_entities = st.multiselect("Entity type", entities, default=entities)

    df = df_all[
        df_all['dataset'].isin(sel_datasets)
        & df_all['entity_type'].isin(sel_entities)
    ].reset_index(drop=True)

    if df.empty:
        st.info("No anomalies left after filtering.")
        return None

    return kind, buffer, df_all, df, detectors


def detector_heatmap(matrix: pd.DataFrame, title: str, y_title: str = "") -> go.Figure:
    """Heatmap of detectors (x) against groups (y), sized so labels stay legible.

    Detector names are long and there are 32 of them, so the ticks are rotated
    and the figure is meant to be given the full page width. Earlier versions
    put two of these side by side with horizontal ticks, which overlapped into
    an unreadable smear.
    """
    column_means = matrix.mean(axis=0)
    order = column_means.sort_values(ascending=False).index
    matrix = matrix[order]
    column_means = column_means[order]

    labels = [f"{name}  ({value:.2f})" for name, value in column_means.items()]

    fig = go.Figure(go.Heatmap(
        z=matrix.values,
        x=labels,
        y=[str(v) for v in matrix.index],
        colorscale='YlGnBu',
        text=[[f"{v:.2f}" if pd.notna(v) else "" for v in row] for row in matrix.values],
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorbar=dict(thickness=14, title=dict(text="density", side="right")),
        hovertemplate="%{y}<br>%{x}<br>density = %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        height=max(320, 42 * len(matrix) + 190),
        margin=dict(l=140, r=20, t=60, b=170),
        xaxis=dict(tickangle=-60, tickfont=dict(size=11), side='bottom'),
        yaxis=dict(title=y_title, autorange='reversed', tickfont=dict(size=11)),
        font=dict(size=13),
    )
    return fig


# ---------------------------------------------------------------------------
# Step 3 combination tables (one shard per dataset, written as they finish)
# ---------------------------------------------------------------------------

MAX_VUS_BUFFER = 256
DEFAULT_VUS_BUFFER = 128
# Every buffer from 0 to 256 is stored by step 3, so the slider is continuous.
VUS_BUFFERS = list(range(MAX_VUS_BUFFER + 1))
# The subset TSB-AD reports, used where a curve needs points rather than a
# single value.
TSBAD_VUS_BUFFERS = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256]


def combo_datasets(kind: str = 'uni') -> list[str]:
    """Datasets whose step-3 shard exists. TSB-AD only; empty elsewhere."""
    return _combo_datasets(kind) if is_tsb_ad() else []


@st.cache_data
def _combo_datasets(kind: str = 'uni') -> list[str]:
    """Datasets whose step-3 shard exists. Grows as the sweep finishes."""
    shards = DIVERGENCE_DIR.glob(f'combos_{kind}_*.parquet')
    names = [s.stem.replace(f'combos_{kind}_', '') for s in shards]
    return sorted(n for n in names if n != 'detectors')


def cached_combo_detectors(kind: str = 'uni') -> list[str]:
    """Detector roster the d0/d1/d2 columns index into. TSB-AD only."""
    return _combo_detectors(kind) if is_tsb_ad() else []


@st.cache_data
def _combo_detectors(kind: str = 'uni') -> list[str]:
    """Detector roster the d0/d1/d2 columns index into."""
    path = DIVERGENCE_DIR / f'combos_{kind}_detectors.parquet'
    if not path.exists():
        return []
    return pd.read_parquet(path)['detector'].tolist()


def cached_combos(kind: str, dataset: str, buffer: int) -> pd.DataFrame:
    """Every combination for one dataset at one buffer. TSB-AD only."""
    return _combos(kind, dataset, buffer) if is_tsb_ad() else pd.DataFrame()


@st.cache_data
def _combos(kind: str, dataset: str, buffer: int) -> pd.DataFrame:
    """Every combination for one dataset, with VUS at one buffer only.

    The shard stores all 257 buffers as separate columns precisely so this can
    read one of them -- pulling the whole file would be hundreds of MB per
    dataset for a number the slider changes constantly.
    """
    path = DIVERGENCE_DIR / f'combos_{kind}_{dataset}.parquet'
    if not path.exists():
        return pd.DataFrame()
    columns = ['filename', 'dataset', 'k', 'd0', 'd1', 'd2', 'n_constant',
               f'vus_{buffer}']
    frame = pd.read_parquet(path, columns=columns)
    return frame.rename(columns={f'vus_{buffer}': 'vus'})


ANOMALY_LENGTH_MODES = {
    'All anomalies': 'all',
    'Point only (length 1)': 'point',
    'Subsequences only': 'subsequence',
}


def _agreement_one(wide: pd.DataFrame) -> dict:
    """Spearman between detectors over one dataset's anomalies."""
    caught = (wide > RESPONSE_THRESHOLD).sum(axis=1)
    best = wide.max(axis=1)
    varying = wide.columns[wide.nunique() > 1]
    dead = sorted(set(wide.columns) - set(varying))

    usable = wide[varying]
    ranks = usable.rank(axis=0)
    z = (ranks - ranks.mean()) / ranks.std(ddof=0)
    matrix = (z.T @ z) / len(z)

    return {
        'matrix': matrix,
        'density': usable.mean(),
        'n_anomalies': int(wide.shape[0]),
        'n_detectors': int(wide.shape[1]),
        'dead': dead,
        'found_by_none': float((best < STRONG_RESPONSE).mean()),
        'median_caught': float(caught.median()),
        'best_median': float(best.median()),
        'zero_cells': float((wide == 0).to_numpy().mean()),
    }


@st.cache_data(show_spinner='Correlating detectors over anomalies ...')
def cached_anomaly_agreement(kind: str, dataset: str, buffer: int,
                             length_mode: str = 'all') -> dict:
    """Detector-vs-detector Spearman computed over anomalies, not timestamps.

    Score-level correlation is dominated by the ~95% of timestamps that are
    normal, so two detectors can look independent while catching exactly the
    same anomalies. This uses one value per anomaly instead: the detection
    density from step 2.

    The unit is the dataset, not the series. The median series holds 2
    anomalies and a correlation over 2 points is noise, so anomalies are pooled
    within a dataset.

    Detectors whose density never varies are dropped and returned separately.
    Their correlation is undefined, and undefined must never be displayed as
    uncorrelated -- that is what made naive minimum-correlation a strawman.
    """
    long = cached_detection(kind)
    if long.empty:
        return {}

    frame = long.copy()
    frame['dataset'] = frame.filename.str.split('_').str[1]
    if length_mode == 'point':
        frame = frame[frame.length == 1]
    elif length_mode == 'subsequence':
        frame = frame[frame.length > 1]
    if frame.empty:
        return {}

    column = density_column(frame, buffer)

    def to_wide(block: pd.DataFrame) -> pd.DataFrame | None:
        wide = block.pivot_table(index=['filename', 'anomaly_idx'],
                                 columns='detector', values=column)
        wide = wide.dropna(axis=1, how='all')
        if wide.shape[0] < 3 or wide.shape[1] < 2:
            return None
        return wide.fillna(0.0)

    if dataset != 'All datasets':
        wide = to_wide(frame[frame.dataset == dataset])
        if wide is None:
            return {}
        result = _agreement_one(wide)
        result['macro'] = False
        result['n_datasets'] = 1
    else:
        # Macro average: correlate within each dataset, then average the
        # matrices with every dataset counting once. Pooling instead would make
        # this a chart about Stock, which is 72% of all anomaly events.
        parts, densities, stats = [], [], []
        for name, block in frame.groupby('dataset', observed=True):
            wide = to_wide(block)
            if wide is None:
                continue
            one = _agreement_one(wide)
            parts.append(one['matrix'])
            densities.append(one['density'])
            stats.append(one)
        if not parts:
            return {}

        detectors = sorted(set().union(*(p.columns for p in parts)))
        stack = np.stack([p.reindex(index=detectors, columns=detectors).to_numpy()
                          for p in parts])
        with np.errstate(invalid='ignore'):
            averaged = np.nanmean(stack, axis=0)
        result = {
            'matrix': pd.DataFrame(averaged, index=detectors, columns=detectors),
            'density': pd.concat(densities, axis=1).mean(axis=1),
            'n_anomalies': sum(s['n_anomalies'] for s in stats),
            'n_detectors': len(detectors),
            'dead': sorted(set.intersection(*(set(s['dead']) for s in stats))),
            'found_by_none': float(np.mean([s['found_by_none'] for s in stats])),
            'median_caught': float(np.mean([s['median_caught'] for s in stats])),
            'zero_cells': float(np.mean([s['zero_cells'] for s in stats])),
            'macro': True,
            'n_datasets': len(stats),
        }

    density = result['density'].sort_values(ascending=False)
    order = density.index.tolist()
    result['density'] = density
    result['order'] = order
    result['matrix'] = result['matrix'].loc[order, order]
    return result


@st.cache_data
def cached_score_agreement_median(kind: str, dataset: str) -> float:
    """Median score-level Spearman, for contrast with the anomaly-level number.

    Macro-averaged over datasets when all are selected, matching how
    cached_anomaly_agreement aggregates. Pooling here would weight by series
    count (YAHOO alone is 259 of 866) and the two numbers would not be
    comparable.
    """
    pairs = cached_pair_agreement(kind)
    if pairs.empty:
        return float('nan')
    if dataset != 'All datasets':
        pairs = pairs[pairs.dataset == dataset]
        return float(pairs.spearman.median()) if len(pairs) else float('nan')
    per_dataset = pairs.groupby('dataset', observed=True).spearman.median()
    return float(per_dataset.mean()) if len(per_dataset) else float('nan')


HEURISTIC_LABELS = {
    'best': 'Best (exhaustive)',
    'top_k': 'Top-k by solo VUS',
    'least_corr': 'Least correlated',
    'least_corr_top10': 'Least correlated, top-10',
    'max_coverage': 'Max coverage (greedy)',
}
HEURISTIC_COLORS = {
    'best': '#2b8a3e', 'top_k': '#4C78A8', 'least_corr': '#b0b0b0',
    'least_corr_top10': '#9467bd', 'max_coverage': '#e07b00',
}


def cached_heuristics(kind: str = 'uni') -> pd.DataFrame:
    """Step 4 output. TSB-AD only; empty elsewhere."""
    return _heuristics(kind) if is_tsb_ad() else pd.DataFrame()


@st.cache_data
def _heuristics(kind: str = 'uni') -> pd.DataFrame:
    """Step 4 output for every dataset computed so far, concatenated.

    One row per (series, k, VUS buffer, heuristic). Small enough to hold whole
    -- the point of step 4 is that the global pages never touch the multi-GB
    combination shards.
    """
    shards = sorted(DIVERGENCE_DIR.glob(f'heuristics_{kind}_*.parquet'))
    if not shards:
        return pd.DataFrame()
    frames = [pd.read_parquet(s) for s in shards]
    table = pd.concat(frames, ignore_index=True)
    for column in ['dataset', 'heuristic', 'filename']:
        if column in table.columns:
            table[column] = table[column].astype('category')
    return table


def cached_solo_baseline(kind: str = 'uni',
                         buffers: tuple[int, ...] = ()) -> pd.DataFrame:
    """Best single detector per (series, buffer). TSB-AD only."""
    return _solo_baseline(kind, buffers) if is_tsb_ad() else pd.DataFrame()


@st.cache_data
def _solo_baseline(kind: str = 'uni',
                   buffers: tuple[int, ...] = ()) -> pd.DataFrame:
    """Best single detector per (series, buffer) -- what every set is read against.

    Taken from the k=1 rows of the combination shards, so it is the same number
    the exhaustive search used rather than a separately computed one.

    `buffers` is a tuple because st.cache_data needs a hashable argument. Only
    the requested columns are read: the shards store all 257 buffers, so asking
    for every one of them would pull gigabytes to answer a single-buffer
    question.
    """
    wanted = list(buffers) if buffers else [DEFAULT_VUS_BUFFER]
    rows = []
    for dataset in combo_datasets(kind):
        path = DIVERGENCE_DIR / f'combos_{kind}_{dataset}.parquet'
        value_columns = [f'vus_{b}' for b in wanted]
        frame = pd.read_parquet(
            path, columns=['filename', 'dataset', 'k', 'd0', 'n_constant']
            + value_columns)
        frame = frame[(frame.k == 1) & (frame.n_constant == 0)]
        melted = frame.melt(id_vars=['filename', 'dataset', 'd0'],
                            value_vars=value_columns,
                            var_name='buffer', value_name='vus')
        melted['buffer'] = melted.buffer.str.replace('vus_', '').astype(int)
        best = melted.loc[melted.groupby(['filename', 'buffer'])['vus'].idxmax()]
        rows.append(best)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).rename(columns={'vus': 'solo_vus'})


# Shared settings for the Combinations group. Streamlit gives a widget its
# identity from the page it is drawn on, so the same control on two pages is
# two different widgets and each reverts to its default when you navigate.
# Keeping the chosen value under our own session-state key, and feeding it back
# as the default, makes the three pages behave as one workspace.

def _sticky(state_key: str, default, widget):
    """Draw a sidebar widget defaulting to whatever it was last set to."""
    current = st.session_state.get(state_key, default)
    value = widget(current)
    st.session_state[state_key] = value
    return value


def vus_buffer_selector(label: str = 'VUS buffer (L)') -> int:
    """Sidebar control for which VUS buffer every number on the page is read at.

    TSB-AD's combination tables hold all 257 buffers; every other benchmark
    only has the ten its metric files report, so there the slider snaps.
    """
    if not is_tsb_ad():
        return _sticky('combo_buffer', DEFAULT_VUS_BUFFER, lambda current: (
            st.sidebar.select_slider(
                label, options=TSBAD_VUS_BUFFERS,
                value=min(TSBAD_VUS_BUFFERS, key=lambda b: abs(b - int(current))),
                help=('VUS-PR averages AUC-PR over buffers 0..L. L=0 is strict '
                      'pointwise; larger L forgives timing error. This '
                      'benchmark has VUS-PR at these ten buffers.'),
            )))
    return _sticky('combo_buffer', DEFAULT_VUS_BUFFER, lambda current: (
        st.sidebar.slider(
            label, 0, MAX_VUS_BUFFER,
            value=int(current) if 0 <= current <= MAX_VUS_BUFFER
            else DEFAULT_VUS_BUFFER,
            help=('VUS-PR averages AUC-PR over buffers 0..L. L=0 is strict '
                  'pointwise; larger L forgives timing error. Every VUS on '
                  'this page, and the ranking used to pick the sets, is read '
                  'at this L. All 257 buffers are precomputed.'),
        )))


def combo_k_selector(label: str = 'Combination size') -> int:
    """Sidebar control for k, shared across the Combinations pages."""
    return _sticky('combo_k', 2, lambda current: (
        st.sidebar.radio(label, [2, 3], horizontal=True,
                         index=1 if current == 3 else 0)))


def combo_dataset_selector(datasets: list[str], label: str = 'Dataset') -> str:
    """Sidebar dataset picker that survives a page change."""
    return _sticky('combo_dataset', datasets[0], lambda current: (
        st.sidebar.selectbox(
            label, datasets,
            index=datasets.index(current) if current in datasets else 0)))


def combo_series_selector(series: list[str], label: str = 'Series') -> str:
    """Sidebar series picker that survives a page change."""
    return _sticky('combo_series', series[0], lambda current: (
        st.sidebar.selectbox(
            label, series,
            index=series.index(current) if current in series else 0)))


def combined_score(parser, filename: str, detectors: list[str]) -> np.ndarray | None:
    """Mean of the re-normalised scores of `detectors` on one series.

    Re-scaling to [0, 1] first is not cosmetic: SR's median maximum across the
    benchmark is 0.303, so a raw average would silently under-weight it.
    """
    vectors = []
    for detector in detectors:
        _, loaded, _ = parser.load_scores(
            detectors=[detector], filenames=[filename],
            drop_missing=False, return_filenames=True,
        )
        if not loaded or len(loaded[0]) == 0:
            return None
        score = np.asarray(loaded[0][0], dtype=np.float64).ravel()
        lo, hi = score.min(), score.max()
        vectors.append(np.zeros_like(score) if hi <= lo else (score - lo) / (hi - lo))
    return np.mean(vectors, axis=0) if vectors else None


def render_anomaly_inspector(kind: str, row: pd.Series, detectors: list[str],
                             n_traces: int = 2, subtitle: str = "",
                             show_detectors: list[str] | None = None) -> None:
    """Plot one anomaly in its series, with detector scores underneath.

    Shared by every page that lets you pick a single anomaly, so a click on a
    scatter point and a click on a table row land on the same view.

    By default the traces are the detectors that scored this anomaly best. Pass
    `show_detectors` to force a specific set instead, which is what a page
    comparing a chosen pair needs: the point of that view is those two
    detectors, not whichever two happened to win here.
    """
    parser = get_parser(kind)
    try:
        _, series_list, label_list = parser.load_timeseries(filename=[row['filename']])
    except ValueError:
        st.error(f"Could not load {row['filename']}")
        return

    series, labels = series_list[0], label_list[0]
    n_points = len(series)
    context = max(100, int(row['length']))
    lo = int(max(0, row['start'] - context))
    hi = int(min(n_points, row['end'] + context))

    # Numeric only: a non-detector column reaching here makes sorted() compare
    # a float against a string, and the traceback points at the sort rather
    # than at whoever built the column list.
    densities = {}
    for detector in detectors:
        value = row.get(detector)
        if pd.notna(value) and isinstance(value, (int, float, np.integer, np.floating)):
            densities[detector] = float(value)
    if show_detectors:
        top = [d for d in show_detectors if d in densities]
    else:
        top = sorted(densities, key=densities.get, reverse=True)[:n_traces]

    traces, names_out = [], []
    for detector in top:
        _, loaded, _ = parser.load_scores(
            detectors=[detector], filenames=[row['filename']],
            drop_missing=False, return_filenames=True,
        )
        if not loaded:
            continue
        traces.append(loaded[0][0][lo:hi])
        names_out.append(f"{detector}<br>{densities[detector]:.3f}")

    title = (f"{row['filename']} — anomaly #{int(row['anomaly_idx'])}, "
             f"length {int(row['length'])}")
    if subtitle:
        title += f", {subtitle}"

    st.plotly_chart(
        plot_series_plotly(
            series[lo:hi] if series.ndim == 1 else series[lo:hi, :],
            labels[lo:hi],
            title=title,
            detector_scores=traces or None,
            detector_names=names_out or None,
            context_start=lo,
        ),
        width='stretch',
    )

    summary = {
        'dataset': row['dataset'],
        'entity type': row.get('entity_type', '-'),
        'anomaly': f"{int(row['start'])} - {int(row['end'])} ({int(row['length'])} pts)",
        'series length': int(row['ts_length']) if 'ts_length' in row else '-',
        'best detector': row['best_detector'],
        'mean detectability': f"{row['overall_detectability']:.3f}",
        'chance': f"{row['chance']:.3f}" if 'chance' in row else '-',
    }
    st.table(pd.DataFrame([summary]).T.rename(columns={0: 'value'}).astype(str))


def chart_selection(event) -> list:
    """Selected points from a plotly_chart event, as a list.

    Streamlit hands the app an object with a .selection attribute, while
    AppTest hands back the plain dict it was given. Accepting both is what
    makes the click path testable, which is the only reason a bug in it gets
    caught before a user finds it.
    """
    if event is None:
        return []
    selection = event.get('selection') if isinstance(event, dict) else \
        getattr(event, 'selection', None)
    if not selection:
        return []
    points = (selection.get('points') if isinstance(selection, dict)
              else getattr(selection, 'points', None))
    return list(points or [])


def detection_detectors(wide: pd.DataFrame) -> list[str]:
    """Detector columns of a wide detection table, in order.

    Names are blocklisted, but the blocklist is only as good as its last
    update, so numeric dtype is required as well. A caller that adds a helper
    column and forgets to list it here otherwise gets that column treated as a
    detector, which fails far away from the cause.
    """
    non_detector = {
        'filename', 'dataset', 'ds', 'entity_type', 'anomaly_idx', 'start',
        'end', 'length', 'anomaly_rate', 'ts_length', 'chance',
        'overall_detectability', 'best_detector', 'best_density',
        'PC1', 'PC2', 'cluster',
        'type_label', 'anomaly_count', 'length_bin', 'anomaly_count_bin',
        'ts_length_bin',
    }
    return [c for c in wide.columns
            if c not in non_detector and pd.api.types.is_numeric_dtype(wide[c])]


@st.cache_data
def cached_detector_quality(kind: str = 'uni', metric: str = DEFAULT_METRIC) -> pd.DataFrame:
    """Mean metric per (dataset, detector).

    Used to weed out pairs where both detectors are bad: two detectors that
    both score 0.05 VUS-PR agreeing, or disagreeing, tells us nothing.

    Returns:
        DataFrame with columns dataset, detector, quality.
    """
    metrics = cached_metrics(kind)
    if metrics.empty or metric not in metrics.columns:
        return pd.DataFrame(columns=['dataset', 'detector', 'quality'])
    df = metrics.copy()
    df['dataset'] = df['File Name'].str.split('_').str[1]
    return (
        df.groupby(['dataset', 'Model Name'])[metric].mean()
        .reset_index()
        .rename(columns={'Model Name': 'detector', metric: 'quality'})
    )


def attach_quality(cells: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    """Add quality_a, quality_b and worse (the weaker of the two) to a cell table."""
    if quality.empty:
        return cells.assign(quality_a=np.nan, quality_b=np.nan, worse=np.nan)
    out = cells
    for side in ('a', 'b'):
        out = (
            out.merge(quality, left_on=['dataset', f'detector_{side}'],
                      right_on=['dataset', 'detector'], how='left')
            .rename(columns={'quality': f'quality_{side}'})
            .drop(columns='detector')
        )
    out['worse'] = out[['quality_a', 'quality_b']].min(axis=1)
    return out


def window_selector(label: str = 'Tolerance window') -> int:
    """Sidebar control for how much timing slack to allow between detectors."""
    return st.sidebar.select_slider(
        label, options=WINDOWS, value=DEFAULT_WINDOW,
        format_func=lambda w: 'pointwise' if w == 1 else f'+/- {w} pts',
        help=('Pointwise correlation calls a detector that fires 20 points early '
              '"wrong". Widening the window forgives that, so what survives is '
              'genuine disagreement.'),
    )


def cached_pair_agreement(kind: str = 'uni') -> pd.DataFrame:
    """Step 1 output. TSB-AD only; empty elsewhere."""
    return _pair_agreement(kind) if is_tsb_ad() else pd.DataFrame()


@st.cache_data
def _pair_agreement(kind: str = 'uni') -> pd.DataFrame:
    """Step 1 output: Spearman correlation of every detector pair on every series.

    Returns an empty DataFrame if the file has not been built yet, so pages can
    show instructions instead of raising.
    """
    path = DIVERGENCE_DIR / f'pair_agreement_{kind}.parquet'
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Anomaly helpers (ported from review_anomalies.py)
# ---------------------------------------------------------------------------

def extract_anomaly_segments(labels):
    """Return list of (start, end) for each contiguous anomaly segment."""
    diff = np.diff(np.concatenate([[0], labels.astype(int), [0]]))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    return list(zip(starts.tolist(), ends.tolist()))


def compute_detectability(labels, score,
                          thresholds=DETECTABILITY_THRESHOLDS,
                          buffers=DETECTABILITY_BUFFERS):
    """Per-anomaly TP density for one detector score array.

    Returns:
        detectabilities: ndarray of shape (n_anomalies,)
        segments:        list of (start, end) tuples
    """
    segments = extract_anomaly_segments(labels)
    T = len(labels)
    detectabilities = []
    for start, end in segments:
        tp_fracs = []
        for buf in buffers:
            pad_start = max(0, start - buf)
            pad_end = min(T, end + buf)
            pad_len = pad_end - pad_start
            for thr in thresholds:
                pred = (score >= thr).astype(int)
                tp = pred[pad_start:pad_end].sum()
                tp_fracs.append(tp / pad_len if pad_len > 0 else 0.0)
        detectabilities.append(float(np.mean(tp_fracs)))
    return np.array(detectabilities), segments


def build_anomaly_table(parser, fnames, timeseries, labels, all_scores, detectors):
    """Build a DataFrame with one row per anomaly and per-detector detectability features."""
    from tqdm import tqdm
    rows = []
    for fname, ts, lab, file_scores in tqdm(
        zip(fnames, timeseries, labels, all_scores), total=len(fnames), desc="Processing time series"
    ):
        segments = extract_anomaly_segments(lab)
        if not segments:
            continue

        det_scores = {}
        for d_idx, det in enumerate(detectors):
            d_det, _ = compute_detectability(lab, file_scores[d_idx])
            det_scores[det] = d_det

        meta_row = parser.meta[parser.meta.filename == fname]
        dataset = meta_row['dataset'].iloc[0] if not meta_row.empty else 'Unknown'
        entity_type = meta_row['entity_type'].iloc[0] if not meta_row.empty else 'Unknown'

        ts_total_length = ts.shape[0]
        for j, (start, end) in enumerate(segments):
            row = {
                'filename': fname,
                'dataset': dataset,
                'entity_type': entity_type,
                'anomaly_idx': j,
                'start': start,
                'end': end,
                'length': end - start,
                'ts_total_length': ts_total_length,
            }
            for det in detectors:
                row[det] = det_scores[det][j] if j < len(det_scores[det]) else 0.0
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df['overall_detectability'] = df[detectors].mean(axis=1)
        df['best_detector'] = df[detectors].idxmax(axis=1)
    return df


# ---------------------------------------------------------------------------
# Saved-series helpers (ported from review_random.py)
# ---------------------------------------------------------------------------

def load_saved() -> list[dict]:
    """Load saved entries. Migrates old list-of-strings format transparently."""
    if SAVED_FILE.exists():
        with open(SAVED_FILE, 'r') as f:
            data = json.load(f)
        if data and isinstance(data[0], str):
            data = [{'filename': s, 'notes': ''} for s in data]
        return data
    return []


def append_saved(fname: str, notes: str = '') -> None:
    """Upsert a saved entry. Updates notes if the series was already saved."""
    saved = load_saved()
    for entry in saved:
        if entry['filename'] == fname:
            entry['notes'] = notes
            with open(SAVED_FILE, 'w') as f:
                json.dump(saved, f, indent=2)
            return
    saved.append({'filename': fname, 'notes': notes})
    with open(SAVED_FILE, 'w') as f:
        json.dump(saved, f, indent=2)


# ---------------------------------------------------------------------------
# Plotly time-series helper
# ---------------------------------------------------------------------------

def plot_series_plotly(
    timeseries: np.ndarray,
    anomaly_labels: np.ndarray | None,
    title: str = "",
    detector_scores: list[np.ndarray] | None = None,
    detector_names: list[str] | None = None,
    context_start: int = 0,
    show_anomalies: bool = True,
    highlight: tuple[int, int] | None = None,
) -> go.Figure:
    """Series with optional detector scores stacked underneath.

    `highlight` is an absolute (start, end) span. When given, that anomaly is
    drawn solid and every other one is faded, which is what lets a whole series
    be shown at once without losing the anomaly you actually picked.
    """
    ts_2d = timeseries if timeseries.ndim == 2 else timeseries.reshape(-1, 1)
    n_channels = ts_2d.shape[1]
    n_detectors = len(detector_scores) if detector_scores else 0
    n_rows = n_channels + n_detectors

    # A full TSB-AD series runs to 900k points, which the SVG renderer cannot
    # handle interactively. WebGL can.
    scatter = go.Scattergl if ts_2d.shape[0] > 30_000 else go.Scatter
    dim_red, bright_red = 'rgba(214,39,40,0.28)', '#d62728'

    row_heights = [3] * n_channels + [1] * n_detectors
    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.02,
    )

    T = ts_2d.shape[0]
    x = np.arange(context_start, context_start + T)

    for ch in range(n_channels):
        fig.add_trace(
            scatter(x=x, y=ts_2d[:, ch], mode='lines', line=dict(width=1.2, color='#1f77b4'),
                    name=f'C{ch}' if n_channels > 1 else 'Series', showlegend=False),
            row=ch + 1, col=1,
        )

        if anomaly_labels is not None and show_anomalies:
            segments = extract_anomaly_segments(anomaly_labels)
            for seg_start, seg_end in segments:
                seg_x = x[seg_start:seg_end]
                seg_y = ts_2d[seg_start:seg_end, ch]
                chosen = (highlight is not None
                          and seg_start + context_start == highlight[0]
                          and seg_end + context_start == highlight[1])
                # Without a highlight every anomaly is equally the subject, so
                # they all stay solid.
                color = bright_red if (chosen or highlight is None) else dim_red
                # Same renderer as the series itself, not go.Scatter. WebGL
                # traces are drawn on a canvas that sits above the SVG layer,
                # so on a series long enough to switch to Scattergl an SVG
                # overlay ends up *under* the blue line: the anomalies on the
                # 35k-point Power series were almost invisible.
                if len(seg_x) == 1:
                    fig.add_trace(
                        scatter(x=seg_x, y=seg_y, mode='markers',
                                marker=dict(size=11 if chosen else 6, color=color,
                                            line=dict(width=1.5, color='#7a0d0d')
                                            if chosen else None),
                                showlegend=False),
                        row=ch + 1, col=1,
                    )
                else:
                    fig.add_trace(
                        scatter(x=seg_x, y=seg_y, mode='lines',
                                line=dict(width=3 if chosen else 1.5, color=color),
                                showlegend=False),
                        row=ch + 1, col=1,
                    )

    for di, score in enumerate(detector_scores or []):
        name = (detector_names[di] if detector_names else f'D{di}')
        row_idx = n_channels + di + 1
        color = '#e07b00' if di == 0 else None
        fig.add_trace(
            scatter(x=x, y=score, mode='lines',
                    line=dict(width=1.2, color=color) if color else dict(width=1.2),
                    name=name, showlegend=True),
            row=row_idx, col=1,
        )
        if highlight is not None:
            # layer='above' for the same reason: a shape belongs to the SVG
            # layer, which a WebGL trace would otherwise cover completely.
            fig.add_vrect(x0=highlight[0], x1=max(highlight[1], highlight[0] + 1),
                          fillcolor=bright_red, opacity=0.18, line_width=0,
                          layer='above', row=row_idx, col=1)
        fig.update_yaxes(range=[-0.02, 1.02], title_text='', row=row_idx, col=1)

        axis_key = 'yaxis' if row_idx == 1 else f'yaxis{row_idx}'
        domain = fig.layout[axis_key].domain
        y_center = (domain[0] + domain[1]) / 2

        if ' (' in name:
            det_label, val_part = name.rsplit(' (', 1)
            ann_text = f"{det_label}<br>({val_part}"
        else:
            ann_text = name
        fig.add_annotation(
            text=ann_text,
            xref='paper', yref='paper',
            x=-0.02, y=y_center,
            xanchor='right', yanchor='middle',
            textangle=-90,
            showarrow=False,
            font=dict(size=11),
        )

    for ch in range(n_channels):
        label = f'C{ch}' if n_channels > 1 else 'Value'
        fig.update_yaxes(title_text=label, row=ch + 1, col=1)

    fig.update_layout(
        title=title,
        height=max(300, 150 * n_rows),
        margin=dict(l=80, r=20, t=50, b=40),
        font=dict(size=13),
    )
    fig.update_xaxes(title_text='Time', row=n_rows, col=1)
    return fig
