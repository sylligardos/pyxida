<p align="center"><img src="web/app/icon.svg" alt="Pyxida" width="120"></p>

<h1 align="center">Pyxida</h1>

The demo behind the ICDE 2027 demo paper *Pyxida*. It is a web app that
reads a time-series anomaly detection benchmark series by series (which
datasets are still open, which detectors matter, what they did on any one
series), plus **the game**, where you mark anomalies against the best
detector.

It ships with TSB-AD, TSB-UAD and small examples from TimeEval, TAB and
mTSBench, and runs on any benchmark in the same format.

## Try the demo

You need `git` and [Node.js](https://nodejs.org) 20.9 or newer (we use 22).

1. Get the code.
   ```bash
   git clone https://github.com/sylligardos/pyxida.git
   cd pyxida
   ```
2. Get the data. Download `pyxida-data.zip` from
   [Zenodo](https://doi.org/10.5281/zenodo.23419645) (3 GB, about 10 GB
   unpacked, the exported series and scores rather than the raw benchmarks)
   and unzip it from the repo root, so that it fills `data/`.
   ```bash
   unzip /path/to/pyxida-data.zip
   ```
3. Run it.
   ```bash
   cd web
   npm install
   npm run dev
   ```
4. Open http://localhost:3000. The game is at http://localhost:3000/play.
   If port 3000 is taken, use `PORT=3001 npm run dev`.

## Your own benchmark

You need the scores of your detectors on your series, and the Python side.

```bash
conda env create -f environment.yml
conda activate pyxida
```

1. **Format.** One folder per benchmark, in TSB-AD's layout, under
   `$TSAD_BENCHMARKS` (default `~/Documents/tsad-benchmarks`).
   ```
   <name>/
   ├── raw/{uni,multi}/<file>.csv                 a header row, the value column(s), then Label (0/1)
   ├── scores/{uni,multi}/<Detector>/<file>.npy   one anomaly score per timestamp
   └── metrics/{uni,multi}/<Detector>.csv         optional, step 2 writes it
   ```
   A file is named `<num>_<Dataset>_id_<k>_<Domain>_tr_<train>_1st_<first>.csv`
   with its number, its dataset, its index in that dataset, a domain tag,
   the length of the train prefix (`tr_0` if none) and the index of the
   first anomaly (`1st_0` if none). No field may contain `_`. Converters for
   TSB-UAD, TAB, TimeEval and mTSBench are in `app/convert/`.
2. **Metrics.** If you have no AUC-PR and VUS-PR yet, compute them.
   ```bash
   python scripts/compute_metrics.py --benchmark <name>
   ```
3. **Export for the demo.** This writes `data/web/<name>/`.
   ```bash
   python scripts/export_web.py --benchmark <name> --kind uni --all
   python scripts/export_graph.py --benchmark <name> --kind uni
   ```
   Use `--kind multi` for multivariate series.
4. **The game** (optional, univariate series only; code name Needle).
   ```bash
   python scripts/needle/build_pack.py --benchmark <name> --per-tier 100 --out data/game/<name>
   ```
   A round plays up to 10 series, and decoys are cut from the series left
   over once the tiers are filled, so keep `--per-tier` well under your
   number of series. For a handful of short series, try
   `--per-tier 2 --min-len 200`.
5. Run the demo as above and pick `<name>` in the top bar.

Every view works on a new benchmark. Only the top-k against best set part of
Redundancy needs the exhaustive combination search, which exists for TSB-AD
univariate. Needle starts on TSB-AD and offers the new pack on its Start
screen.

## Layout

```
pyxida/
├── web/        the demo (Next.js): Graph, Explore, Workbench, and Needle at /play
├── scripts/    the pipeline (metrics, export for the web); needle/ builds the game's packs
├── app/        parser.py (reads a benchmark) and convert/ (other benchmarks into the format)
├── data/       the data (from the zip, or from the scripts)
└── tests/
```

More in `web/README.md`, `scripts/needle/README.md`, and each script's header.

## Test

```bash
pytest tests        # VUS-PR, Needle's rules and pack builder, and the parser
cd web && npm test  # the web tests
```

The parser tests need TSB-AD in `$TSAD_BENCHMARKS` (default
`~/Documents/tsad-benchmarks`) and are skipped without it. `npm test` also
checks Needle's TypeScript scoring against the Python one once the reference
file exists, which `python scripts/needle/make_dev_pack.py && python scripts/scoring_golden.py`
creates.

## Cite

The paper is under submission. Until it is out, please cite the data.

```bibtex
@dataset{sylligardos2026pyxida,
  author    = {Sylligardos, Emmanouil},
  title     = {Pyxida: demo data (series, detector scores and processed data)},
  publisher = {Zenodo},
  year      = {2026},
  version   = {1.0},
  doi       = {10.5281/zenodo.23419645}
}
```

## Credits

The series, labels and scores come from these benchmarks. Please cite them
when you use the data.

- **TSB-AD.** Q. Liu, J. Paparrizos. *The Elephant in the Room: Towards A
  Reliable Time-Series Anomaly Detection Benchmark.* NeurIPS 2024.
  https://github.com/TheDatumOrg/TSB-AD
- **TSB-UAD.** J. Paparrizos, Y. Kang, P. Boniol, R. S. Tsay, T. Palpanas,
  M. J. Franklin. *TSB-UAD: An End-to-End Benchmark Suite for Univariate
  Time-Series Anomaly Detection.* PVLDB 15(8), 2022.
- **TimeEval.** S. Schmidl, P. Wenig, T. Papenbrock. *Anomaly Detection in
  Time Series: A Comprehensive Evaluation.* PVLDB 15(9), 2022.
- **TAB.** X. Qiu, Z. Li, W. Qiu, S. Hu, L. Zhou, X. Wu, Z. Li, C. Guo,
  A. Zhou, Z. Sheng, J. Hu, C. S. Jensen, B. Yang. *TAB: Unified
  Benchmarking of Time Series Anomaly Detection Methods.* PVLDB 18(9), 2025.
- **mTSBench.** X. Zhou, C. Brif, I. Lourentzou. *mTSBench: Benchmarking
  Multivariate Time Series Anomaly Detection and Model Selection at Scale.*
  TMLR, 2026.

VUS-PR is computed with TSB-AD's own code, copied into `scripts/vus.py`
under its Apache 2.0 license (`scripts/LICENSE-TSB-AD`).

- J. Paparrizos, P. Boniol, T. Palpanas, R. S. Tsay, A. Elmore,
  M. J. Franklin. *Volume Under the Surface: A New Accuracy Evaluation
  Measure for Time-Series Anomaly Detection.* PVLDB 15(11), 2022.
- P. Boniol, A. K. Krishna, M. Bruel, Q. Liu, M. Huang, T. Palpanas,
  R. S. Tsay, A. Elmore, M. J. Franklin, J. Paparrizos. *VUS: Effective and
  Efficient Accuracy Measures for Time-Series Anomaly Detection.* The VLDB
  Journal 34(3), 2025.

## License

The code is MIT, see `LICENSE`. The data on Zenodo is CC BY 4.0.
