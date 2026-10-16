# Needle

The booth game: a player marks anomalies in a real series, then sees the
labels and what the best detector on that series flagged, and both are
scored. It plays inside the web demo at `/play`; its screens are in
`web/public/play/`, its API in `web/app/api/game/`, its rules in
`web/lib/game/scoring.ts`.

This folder builds what it plays: one **pack** per benchmark under
`data/game/<benchmark>/`.

## Build a pack

```bash
python scripts/needle/make_dev_pack.py         # synthetic pack, data/game/dev (no benchmark needed)

# from a benchmark (needs its raw series, scores and metrics)
python scripts/needle/build_pack.py --benchmark <name> --per-tier 100 --out data/game/<name>
python scripts/needle/check_pack.py data/game/<name> --list    # what is in it, how the opponents do
```

For TSB-AD the tiers come from the exhaustive combination study
(`make_tiers.py` writes `data/divergence/tiers_uni.csv`, then pass
`--tiers` to `build_pack.py`). Without `--tiers`, a series is easy when at
least half of the detectors reach VUS-PR 0.5 on it, unsolved when none does,
medium in between.

## Files

| File | What |
| --- | --- |
| `scoring.py` | The rules, in Python: the reference the TypeScript port is tested against |
| `pack.py` | The pack format, read and write |
| `build_pack.py` | A pack from a benchmark: windows, labels, the opponent's score, tiers |
| `check_pack.py` | A pack's windows and decoys, and the opponents' results under the rules |
| `make_tiers.py` | TSB-AD tiers from the combination study |
| `pick_team.py` | Detectors ranked by Shapley value against the per-series best |
| `make_dev_pack.py` | The synthetic pack, for tests and for working without data |

## Rules

- Ten series a round. Easy: 6 easy, 2 medium, 2 decoys, 60 s each. Normal:
  3 easy, 3 medium, 2 unsolved, 2 decoys, 45 s. Hard: 2 medium, 6 unsolved,
  2 decoys, 30 s. A decoy has no anomaly.
- A **hit** is a labeled anomaly any of the player's ranges overlaps, counted
  once. A **false alarm** is a range that overlaps none, or one wider than a
  tenth of the window. An unmarked decoy is +1. Up to five ranges.
- The **opponent** is the best detector on that series by VUS-PR, out of the
  whole pool. It flags every point where its score is more than 3 standard
  deviations above its mean (points close together joined into one range),
  scored like the player.
- A series adds +1, 0 or -1 to the round (the sign of hits minus false
  alarms), so one bad series cannot sink a round.
- Windows hold at most 10 000 points around the first anomaly and no other;
  windows more than 10% anomalous are skipped.

Every finished round is logged to `data/game/plays.sqlite` and
`data/game/plays.csv` (local, never committed).

Music: "8-Bit Battle Loop" (CC0, `web/public/play/audio/LICENSE.md`); the
effects are synthesised in `sfx.js`.
