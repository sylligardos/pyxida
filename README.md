<p align="center"><img src="web/app/icon.svg" alt="Pyxida" width="120"></p>

<h1 align="center">Pyxida</h1>

The demo behind the ICDE 2027 demo paper *Pyxida*: a web app that reads a
time-series anomaly detection benchmark series by series (which datasets are
still open, which detectors matter, what they did on any one series), plus
**Needle**, a game where you mark anomalies against the best detector.

It ships with TSB-AD, TSB-UAD and small examples from TimeEval, TAB and
mTSBench, and runs on any benchmark in the same format.

## Try the demo

You need `git` and [Node.js](https://nodejs.org) 20.9 or newer (we use 22).

1. Get the code:
   ```bash
   git clone https://github.com/sylligardos/pyxida.git
   cd pyxida
   ```
2. Get the data: download `pyxida-data.zip` from **ZENODO_LINK** (3 GB,
   about 10 GB unpacked: the exported series and scores, not the raw
   benchmarks) and unzip it from the repo root, so it fills `data/`:
   ```bash
   unzip /path/to/pyxida-data.zip
   ```
3. Run it:
   ```bash
   cd web
   npm install
   npm run dev
   ```
4. Open http://localhost:3000. Needle is at http://localhost:3000/play.
   (If port 3000 is taken: `PORT=3001 npm run dev`.)

## Your own benchmark

You need the scores of your detectors on your series, and the Python side:

```bash
conda env create -f environment.yml
conda activate pyxida
```

1. **Format.** One folder per benchmark, in TSB-AD's layout, under
   `$TSAD_BENCHMARKS` (default `~/Documents/tsad-benchmarks`):
   ```
   <name>/
   ├── raw/{uni,multi}/<file>.csv                 a header row, the value column(s), then Label (0/1)
   ├── scores/{uni,multi}/<Detector>/<file>.npy   one anomaly score per timestamp
   └── metrics/{uni,multi}/<Detector>.csv         optional, step 2 writes it
   ```
   A file is named `<num>_<Dataset>_id_<k>_<Domain>_tr_<train>_1st_<first>.csv`:
   its number, its dataset, its index in that dataset, a domain tag, the
   length of the train prefix (`tr_0` if none) and the index of the first
   anomaly (`1st_0` if none), with no `_` inside a field. Converters for TSB-UAD, TAB, TimeEval
   and mTSBench are in `app/convert/`.
2. **Metrics** (AUC-PR and VUS-PR, if you have none):
   ```bash
   python scripts/compute_metrics.py --benchmark <name>
   ```
3. **Export for the demo** (writes `data/web/<name>/`):
   ```bash
   python scripts/export_web.py --benchmark <name> --kind uni --all
   python scripts/export_graph.py --benchmark <name> --kind uni
   ```
   Use `--kind multi` for multivariate series.
4. **Needle** (optional, univariate series only):
   ```bash
   python scripts/needle/build_pack.py --benchmark <name> --per-tier 100 --out data/game/<name>
   ```
   A round plays up to 10 series, and decoys are cut from the series left
   over once the tiers are filled, so keep `--per-tier` well under your
   number of series. For a handful of short series, for example:
   `--per-tier 2 --min-len 200`.
5. Run the demo as above and pick `<name>` in the top bar.

Every view works on a new benchmark. Only Redundancy's top-k against the
best set needs the exhaustive combination search, which exists for TSB-AD
univariate. Needle starts on TSB-AD; the new pack is offered on its Start
screen.

## Layout

```
pyxida/
├── web/        the demo (Next.js): Graph, Explore, Workbench, and Needle at /play
├── scripts/    the pipeline: metrics, export for the web; needle/ builds the game's packs
├── app/        parser.py (reads a benchmark) and convert/ (other benchmarks into the format)
├── data/       the data (from the zip, or from the scripts)
└── tests/
```

More in `web/README.md`, `scripts/needle/README.md`, and each script's header.

## Test

```bash
pytest tests        # VUS-PR, Needle's rules and pack builder; the parser tests need TSB-AD in $TSAD_BENCHMARKS (default ~/Documents/tsad-benchmarks)
cd web && npm test  # the web tests
```

`npm test` also checks Needle's TypeScript scoring against the Python one once
the reference file exists: `python scripts/needle/make_dev_pack.py && python scripts/scoring_golden.py`.

## Credits

- TSB-AD: Q. Liu, J. Paparrizos. *The Elephant in the Room: Towards A
  Reliable Time-Series Anomaly Detection Benchmark.* NeurIPS 2024.
  https://github.com/TheDatumOrg/TSB-AD
- VUS-PR: J. Paparrizos, P. Boniol, T. Palpanas, R. S. Tsay, A. Elmore,
  M. J. Franklin. *Volume Under the Surface: A New Accuracy Evaluation Measure
  for Time-Series Anomaly Detection.* PVLDB 15(11), 2022. And P. Boniol,
  A. K. Krishna, M. Bruel, Q. Liu, M. Huang, T. Palpanas, R. S. Tsay,
  A. Elmore, M. J. Franklin, J. Paparrizos. *VUS: Effective and Efficient
  Accuracy Measures for Time-Series Anomaly Detection.* The VLDB Journal
  34(3), 2025. The code in
  `scripts/vus.py` is TSB-AD's, under its Apache 2.0 license
  (`scripts/LICENSE-TSB-AD`).

## License

MIT, see `LICENSE`.
