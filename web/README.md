# Pyxida, the web demo

The demo and Needle, in one Next.js app. It reads nothing from the benchmark
itself: everything comes from the files `scripts/export_web.py` and
`scripts/export_graph.py` write under `data/web/`, and from Needle's packs
under `data/game/`.

Pages: **Intro** (`/`), **Graph**, **Explore** (Landscape, Rankings and
Redundancy, one switch), **Workbench** (with the "I'm feeling lucky"
one-liners), and **Needle** (`/game`, played at `/play`). Every page has a
"?" popup that says what it shows and how it is computed.

## Run

From the repo root, once per benchmark:

```bash
conda activate pyxida
python scripts/export_web.py --benchmark tsb-ad --kind uni --all      # data/web/tsb-ad/uni
python scripts/export_graph.py --benchmark tsb-ad --kind uni          # adds graph.json
```

`--all` writes every series and every detector score (about 2 GB for TSB-AD
univariate); without it only the tables and the demo series are written.

Then:

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

Needle plays at `/play` (the booth monitor opens `/play?screen=board`). It
reads every pack under `data/game/` except `dev` (`PYXIDA_PACKS=a,b` to pick
some, `PYXIDA_PACK` for one); see `scripts/needle/README.md` for how a pack is built.
Plays are logged to `data/game/plays.sqlite` (`PYXIDA_GAME_DB`) and appended
to `data/game/plays.csv`. `PYXIDA_ALL_TIME=1` makes the board cover every
day, not just today.

## Layout

```
web/
├── app/
│   ├── page.tsx                 Intro
│   ├── graph/, explore/, workbench/, game/
│   ├── api/data/[...path]       serves data/web/ to the browser
│   ├── api/game/                Needle's API
│   ├── api/notes                the Workbench notes (data/notes.json)
│   └── api/help                 the "?" text, for the Needle screens
├── components/                  top bar, footer, the views, the lane chart
├── lib/
│   ├── model.ts                 types, constants, URL state (client-safe)
│   ├── data.ts                  reads data/web/ (server only)
│   ├── help.ts                  the "?" popups
│   ├── oneliners.ts             Wu & Keogh's one-liners, as scores
│   └── game/                    scoring.ts (port of scripts/needle/scoring.py), pack.ts, store.ts (SQLite)
├── public/play/                  Needle's screens (plain JS), served as they are
└── tests/                       the scoring port against Python, the one-liners
```

State that every page shares (benchmark, univariate or multivariate) lives in
the URL: `?b=tsb-ad&k=uni`. A link to the Workbench names its series with `s=`.
The old `/landscape`, `/rankings` and `/redundancy` redirect to Explore.

`next.config.ts` rewrites `/static/*` and `/api/stats`, `/api/round/*` to
what Needle's `app.js` expects.

## Test

```bash
python scripts/needle/make_dev_pack.py   # from the repo root, once
python scripts/scoring_golden.py         # what scripts/needle/scoring.py says, as JSON
cd web && npm test                     # the TypeScript port must say the same
```

The scoring test is skipped when the golden file is missing.

## Data files

`data/web/<benchmark>/<kind>/`:

| File | What |
| --- | --- |
| `summary.json` | counts, the detector list, one row per series (file, dataset, type, length, anomalies) |
| `landscape.json` | AUC-PR and VUS-PR of every detector on every series (buffer 10 on TSB-AD univariate, nearest buffer elsewhere) |
| `redundancy.json` | pair agreement and top-k versus best-k (TSB-AD univariate only) |
| `graph.json` | the series graph, one per scope (from `export_graph.py`) |
| `series/<file>.json` | values (5 significant digits) and label runs; multivariate: up to 8 channels |
| `scores/<file>/<Detector>.u16` | one detector's score, min-max scaled to uint16 |
