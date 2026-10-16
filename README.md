<p align="center"><img src="web/app/icon.svg" alt="Pyxida" width="120"></p>

<h1 align="center">Pyxida</h1>

The demo behind the ICDE 2027 demo paper *Pyxida*: a web app that reads a
time-series anomaly detection benchmark series by series (which datasets are
still open, which detectors matter, what they did on any one series), plus
**Needle**, a booth game where a person marks anomalies against the best
detector.

Runs on TSB-AD out of the box, and on any benchmark in the same format.

## Layout

```
pyxida/
├── web/        the demo (Next.js): Graph, Explore, Workbench, and Needle at /play
├── scripts/    the data pipeline: run detectors, metrics, export for the web;
│               needle/ builds the game's packs
├── app/        parser.py (reads a benchmark) and convert/ (other benchmarks into the format)
├── data/       the data (see below)
└── tests/
```

## Run

```bash
conda env create -f environment.yml && conda activate tsbad
cd web && npm install && npm run dev      # http://localhost:3000
```

The app only reads `data/web/` (exported series and tables) and `data/game/`
(Needle packs). If you have them, that is all you need.

## Data

Benchmarks sit in `$TSAD_BENCHMARKS` (default `~/Documents/tsad-benchmarks`),
one folder each, in TSB-AD's layout:

```
<benchmark>/
├── raw/{uni,multi}/<file>.csv                 values, then a binary Label column
├── scores/{uni,multi}/<Detector>/<file>.npy   one score per timestamp
└── metrics/{uni,multi}/<Detector>.csv         one row per series: AUC-PR, VUS-PR
```

`data/raw`, `scores`, `metrics` and `runtime` are links into
`$TSAD_BENCHMARKS/tsb-ad/`:

```bash
for d in raw scores metrics runtime; do ln -s ~/Documents/tsad-benchmarks/tsb-ad/$d data/$d; done
```

To rebuild what the app reads, from the repo root:

```bash
python scripts/export_web.py --benchmark tsb-ad --kind uni --all   # data/web/
python scripts/export_graph.py --benchmark tsb-ad --kind uni       # the Graph page
python scripts/needle/build_pack.py --tiers data/divergence/tiers_uni.csv --out data/game/tsb-ad
```

Details: `web/README.md`, `scripts/needle/README.md`, and each script's header.

## Test

```bash
pytest tests                 # parser and Needle's rules and pack builder
cd web && npm test           # the TypeScript scoring against the Python one
```

## License

MIT, see `LICENSE`.
