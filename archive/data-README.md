# data/

Benchmark data for TSB-AD. The data itself lives in the benchmarks root
(`$TSAD_BENCHMARKS`, default `~/Documents/tsad-benchmarks/tsb-ad/`), next to the
other benchmarks in the same format; see the README there for the format. Here,
`raw/`, `scores/`, `metrics/` and `runtime/` are local links into that folder
(gitignored), and only `splits/` is tracked.

To set up the links on a new machine:

```bash
for d in raw scores metrics runtime; do ln -s ~/Documents/tsad-benchmarks/tsb-ad/$d data/$d; done
```

## Expected structure

```
data/
├── raw/
│   ├── uni/    ← univariate CSVs  (values columns + binary label column)
│   └── multi/  ← multivariate CSVs
├── scores/
│   ├── uni/    ← one subdir per detector, each containing .npy score files
│   └── multi/
├── metrics/
│   ├── uni/    ← one CSV per detector with evaluation metrics
│   └── multi/
├── runtime/
│   ├── uni/    ← one CSV per detector with wall-clock runtimes
│   └── multi/
└── splits/     ← official TSB-AD splits, {U,M}-{Eval,Label}.csv (tracked)
```

## Download

The full benchmark is published alongside the NeurIPS 2024 paper:

> Liu, Q. & Paparrizos, J., *The elephant in the room: Towards a reliable
> time-series anomaly detection benchmark*, NeurIPS 2024.

Download the data from the official repository and place the files in the
subdirectories above, preserving this layout. The parser will find everything
automatically once the structure matches.

## Other benchmarks and custom paths

Any benchmark in the common format under the benchmarks root loads by name, and
any folder in the format loads by path:

```python
from tsbadparser import TSBADParser
TSBADParser.list_benchmarks()                      # ['tab', 'timeeval', 'tsb-ad', 'tsb-uad']
parser = TSBADParser(benchmark="tab", kind="multi")
parser = TSBADParser("/path/to/a/benchmark", kind="uni")
```
