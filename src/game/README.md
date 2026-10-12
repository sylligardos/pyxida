# Needle

The ICDE 2027 demo game: a player marks anomalies in a real series, then sees
the labels and what a team of detectors flagged, and both are scored. Brief:
`references/GAME_BRIEF.md`. Design: `references/needle-design/` (the arcade
screens).

## Run

```bash
python src/game/make_dev_pack.py     # once: 20 synthetic series in data/game/dev
python src/game/server.py            # http://localhost:8000
```

`?screen=board` opens on the leaderboard, for the booth monitor.

For real data, build a pack from the benchmark (needs the data, so on the work
laptop), then point the server at it:

```bash
python src/game/build_pack.py --detectors Sub_PCA KShapeAD POLY Series2Graph MOMENT_FT \
    --tiers data/divergence/tiers_uni.csv --out data/game/tsb-ad
python src/game/server.py --pack data/game/tsb-ad --db data/game/icde.sqlite
```

The server needs only `starlette` and `uvicorn` (both in the `tsbad` env) and
`numpy`; it never reads the benchmark.

## Files

| File | What |
| --- | --- |
| `scoring.py` | The rules: hits, false alarms, the detectors' flags, verdicts |
| `pack.py` | Content pack format, read and write |
| `build_pack.py` | Pack from a benchmark: windows, labels, detector scores, tiers |
| `make_dev_pack.py` | Synthetic pack, for working without the benchmark |
| `store.py` | SQLite play log and leaderboard |
| `server.py` | Starlette app: the page and the JSON API |
| `web/` | The five screens (`app.js`), the chart (`chart.js`), sounds (`sfx.js`), styles |

## Rules as built

- A **hit** is a labeled anomaly that any player range overlaps, counted once
  per anomaly. A **false alarm** is a range that overlaps no anomaly. A decoy
  left unmarked is +1.
- The **detectors** decide on their own, whatever the player marked. Their
  scores are averaged (each min-max normalised over the window first), and
  the team flags every point where that average is more than 3 standard
  deviations above its mean, with points close together (within 0.5% of the
  series) joined into one range. Each range is scored like a player's.
  `DETECTOR_RULE = "pooled"` in `scoring.py` switches to every detector on
  its own threshold with all their flags counted together.
- The player can mark up to five ranges (the Round screen's five slots).
- The Reveal draws the scored team-average lane, then one lane per detector,
  each with its threshold dashed. A detector's name is lit when its own
  flags touch the anomaly; when the average misses what one caught alone,
  the sub-line says so. The rule in force is logged with each play
  (`view.det_rule`).

- Each series has a **40 s time limit** (`TIME_LIMIT_S` in `web/app.js`;
  `?time=60` in the URL overrides it). The last 10 s tick quietly, the last
  3 s faster; at zero the marks are submitted as they stand and the play is
  logged with `timed_out`. The "Now that you've seen it" answer is optional.
- **Quit** (or `Esc`) leaves a round at any point, after an "are you sure";
  the clock pauses while it asks. A left round never reaches the
  leaderboard; the series already played stay in the log.

## Sound

Effects are synthesised in `web/sfx.js` (no files); the game uses the
`arcade` style, `laser` is the alternative. Music, only on Start, Summary
and the Leaderboard: "8-Bit Battle Loop" (CC0, see `web/audio/LICENSE.md`).
While marking, a quiet background builds as the clock runs down
(`AMBIENT` in `web/app.js`: march, heartbeat, sonar, drone, muffled or none;
`?ambient=sonar` in the URL tries another). `/static/audition.html` plays
every sound, style and background side by side. The "Sound on/off" button
in every screen's top row (or `M`) mutes music and effects together; the
choice is remembered per browser.

## Logged

Per series: the player's ranges, "Nothing here", time spent, zoom and pan
counts, the detectors' flags, both results, which labeled anomalies each side
hit, and the "Now that you've seen it" answer. Tables in `store.py`.
