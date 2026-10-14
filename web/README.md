# Pyxida, the web demo

The four pages (Intro, Landscape, Workbench, Game) and Needle, in one
Next.js app. It reads nothing from the benchmark itself: everything comes
from the files `scripts/export_web.py` writes, and the game's pack and play
log. Built to run locally first; the same app goes online later (Vercel,
with the data files in object storage and the play log in Postgres).

## Run

From the repo root, once per benchmark:

```bash
conda activate tsbad
python scripts/export_web.py --benchmark tsb-ad --kind uni --all      # data/web/tsb-ad/uni
python scripts/export_web.py --benchmark tsb-ad --kind multi --all
python scripts/export_web.py --benchmark tsb-uad --kind uni --all
```

`--all` writes every series and every detector score (about 2 GB for TSB-AD
univariate); without it only the summary, the landscape table and the demo
series are written, which is enough for the Intro and the Landscape.

Then:

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

Needle plays at `/play` (the booth monitor opens `/play?screen=board`). It
needs a pack: `data/game/tsb-ad` by default (`PYXIDA_PACK` to change it; see
`game/README.md` for how a pack is built). Plays are logged to
`data/game/plays.sqlite` (`PYXIDA_GAME_DB`). `PYXIDA_ALL_TIME=1` makes the
board cover every day, not just today.

## Layout

```
web/
├── app/
│   ├── page.tsx                 Intro
│   ├── landscape/, workbench/, game/
│   ├── api/data/[...path]       serves data/web/ to the browser
│   └── api/game/                Needle's API (the routes game/server.py had)
├── components/                  top bar, footer, the views, the lane chart
├── lib/
│   ├── model.ts                 types, constants, URL state (client-safe)
│   ├── data.ts                  reads data/web/ (server only)
│   └── game/                    scoring.ts (port of game/scoring.py), pack.ts, store.ts (SQLite)
├── public/play -> ../../game/web   Needle's screens, served as they are
└── tests/scoring.test.ts        the scoring port against the Python reference
```

State that every page shares (benchmark, univariate or multivariate) lives in
the URL: `?b=tsb-ad&k=uni`. A link to the Workbench names its series with `s=`.

`next.config.ts` rewrites `/static/*` and `/api/stats`, `/api/round/*` to
what Needle's `app.js` expects, so `game/web/` is unchanged.

## Test

```bash
python game/make_dev_pack.py           # from the repo root, once
python scripts/scoring_golden.py       # what game/scoring.py says, as JSON
cd web && npm test                     # the TypeScript port must say the same
```

The test is skipped when the golden file is missing.

## Data files

`data/web/<benchmark>/<kind>/`:

| File | What |
| --- | --- |
| `summary.json` | counts, the detector list, one row per series (file, dataset, type, length, anomalies) |
| `landscape.json` | AUC-PR and VUS-PR of every detector on every series (buffer 10 on TSB-AD univariate, nearest buffer elsewhere) |
| `series/<file>.json` | values (5 significant digits) and label runs; multivariate: up to 8 channels |
| `scores/<file>/<Detector>.u16` | one detector's score, min-max scaled to uint16 |
