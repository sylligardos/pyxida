# Needle

The ICDE 2027 demo game: a player marks anomalies in a real series, then sees
the labels and what a team of detectors flagged, and both are scored. Brief:
`references/GAME_BRIEF.md`. Design: `references/needle-design/` (the arcade
screens).

## Run

```bash
python game/make_dev_pack.py     # once: 20 synthetic series in data/game/dev
python game/server.py            # http://localhost:8000
```

`?screen=board` opens on the leaderboard, for the booth monitor.

For real data, build a pack from the benchmark (needs the data and the
divergence tables, so on the work laptop), then point the server at it:

```bash
python game/make_tiers.py          # data/divergence/tiers_uni.csv, from the study's oracle
python game/pick_team.py           # ranks the detectors; the top five by Shapley are the team
python game/build_pack.py --detectors KShapeAD Sub_LOF MatrixProfile LOF MOMENT_FT \
    --tiers data/divergence/tiers_uni.csv --out data/game/tsb-ad
python game/check_pack.py data/game/tsb-ad --list    # windows, decoys, how the detectors do
python game/server.py --pack data/game/tsb-ad --db data/game/icde.sqlite
```

The server needs only `starlette` and `uvicorn` (both in the `tsbad` env) and
`numpy`; it never reads the benchmark.

## Files

| File | What |
| --- | --- |
| `scoring.py` | The rules: hits, false alarms, the detectors' flags, verdicts |
| `pack.py` | Content pack format, read and write |
| `make_tiers.py` | Tiers (easy, medium, unsolved) from the divergence study's oracle |
| `pick_team.py` | Detectors ranked by Shapley value against the oracle, to pick the team |
| `build_pack.py` | Pack from a benchmark: windows, labels, detector scores, tiers |
| `check_pack.py` | A pack's windows and decoys, and the detectors' results under the game's rules |
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
- **Tiers** (`make_tiers.py`): a detector solves a series when its VUS-PR at
  L=128 reaches 0.5. Easy: at least half of the 30 detectors solve it.
  Medium: at least one detector, or one averaged combination of up to three
  (the study's oracle), does. Unsolved: nothing does. On TSB-AD univariate
  that is 312 / 497 / 57 of 866 series. At the demo's 0.9 bar only 19
  would be easy, too few for a pack.
- **Windows** (`build_pack.py`): at most 10 000 points around the first
  anomaly and, by default, no other (`--max-labels 1`: every screen is
  designed around one anomaly). Decoys are cut from the longest clean
  stretch of a series. Flat windows are passed over.
- **Team** (`pick_team.py`): the Shapley value of each detector for the
  oracle (the best single VUS-PR per series) has a closed form; the top
  five on TSB-AD univariate are KShapeAD, Sub_LOF, MatrixProfile, LOF and
  MOMENT_FT. MOMENT_FT is first by mean VUS-PR and only fifth here; KShapeAD
  alone solves 23 series nobody else does.
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

## Status and decisions

Where the game stands (October 2026), for whoever picks it up next.

**Built and tested** on the synthetic dev pack: all five screens, scoring,
the play log, sound, the timer, Quit. `tests/test_game.py` covers the rules,
the API and `build_pack.py` on a fake benchmark. Screens are checked to fit
one viewport from 1280x720 to 2560x1440.

**Done 2026-10-12** on the work laptop: the team (Shapley top five), the
tiers CSV, and a real pack (`data/game/tsb-ad`, 120 series, 30 per tier,
all single-anomaly windows; built in 5 s). A full round runs through the
API on it. `check_pack.py` on that pack found:

- Under the **average rule at mean + 3 std** the detectors raise 2 to 4
  false alarms per series and take the bait on 28 of 30 decoys, so a
  player who marks nothing at all beats them on most rounds (one smoke
  round: player +1, detectors -14). The same rule at 4 std, or keeping only
  the team's single highest range, finds nearly as much with under one
  false alarm and leaves most decoys alone:

  | rule | easy found / FA | medium found / FA | unsolved found / FA | decoys clean |
  | --- | --- | --- | --- | --- |
  | average, 3 std (current) | 0.80 / 2.0 | 0.87 / 3.1 | 0.60 / 2.9 | 2 of 30 |
  | average, 4 std | 0.63 / 0.7 | 0.83 / 0.9 | 0.50 / 0.7 | 21 of 30 |
  | average, 5 std | 0.40 / 0.3 | 0.60 / 0.5 | 0.37 / 0.4 | 25 of 30 |
  | average, top range only | 0.73 / 0.2 | 0.73 / 0.2 | 0.43 / 0.6 | 2 of 30 |
  | pooled, 3 std | 0.97 / 16.6 | 0.93 / 26.0 | 0.93 / 42.7 | 0 of 30 |

  The threshold is `THRESHOLD_STD` in `scoring.py`; not changed, the
  author decides.
- "Unsolved" by VUS-PR is not "missed" under the game's rule: the team's
  flags touch the anomaly on 60% of unsolved series, because a flag only
  has to overlap. The tier note on the Reveal ("even the best detector
  misses this one") can read as wrong there.
- Easy series are mostly YAHOO: point anomalies (median 14 labeled points)
  in short windows. 68 easy candidates were passed over because the next
  anomaly came within 1 000 points.
- Unsolved series are almost all UCR: one long anomaly (median 360 points)
  in a 10 000 point window of a periodic signal.

**Open, in order:**

1. Decide the detectors' rule from the table above (and whether the Reveal's
   tier notes should talk about VUS-PR or about the game's flags).
2. Game modes and choosing a specific dataset: the author wants to go back to
   design first. Discuss before building.
3. The design's open items: a summary card for several anomalies (moot
   while `--max-labels 1`), light mode, motion.

**Decisions so far:**

- The detectors are scored on their team-average score with a mean + 3 std
  threshold. Pooling every detector's own flags was tried and dropped as
  less clean (the detectors' false alarms pile up and they lose almost every
  round). The author may switch again, which is why `DETECTOR_RULE` exists.
- The player marks freely, but the UI caps them at five ranges.
- The "Now that you've seen it" question is optional; never force it.
- Arcade look from the design comps (magenta = player, cyan = detectors,
  yellow = labels). Say "detectors", never "CPU".
- Every screen fits one viewport on desktop sizes; no page scroll.
- Audio must be free: synthesised effects (`arcade` style chosen, `laser` to
  try), CC0 music only on Start, Summary and the Leaderboard, the "march"
  under a round.
- The game and the analysis of the plays (label audit, hardness) stay
  separate; the server never touches the benchmark.

**Working with the author:** design changes go screen by screen, with a
review after each; show a proposal and discuss before touching code when
asked to; commit and push only when asked.
