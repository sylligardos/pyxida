#!/usr/bin/env bash
# Step 4 over every step-3 shard that exists. Cheap and idempotent -- re-run it
# whenever the sweep produces more shards. Runs in tsbad (no GPU needed).
set -u
cd "$(dirname "$0")/../.."
KIND="${1:-uni}"
for SHARD in data/divergence/combos_${KIND}_*.parquet; do
  DS=$(basename "$SHARD" .parquet); DS=${DS#combos_${KIND}_}
  [ "$DS" = "detectors" ] && continue
  OUT="data/divergence/heuristics_${KIND}_${DS}.parquet"
  # Step 4 reads the detection and agreement tables as well as the combination
  # shard, so a rebuild of either of those has to invalidate it too. Comparing
  # against the shard alone silently kept stale output when detection_uni was
  # recomputed.
  STALE=0
  for INPUT in "$SHARD" "data/divergence/detection_${KIND}.parquet" \
               "data/divergence/pair_agreement_${KIND}.parquet"; do
    [ -f "$INPUT" ] && [ "$INPUT" -nt "$OUT" ] && STALE=1
  done
  if [ -f "$OUT" ] && [ "$STALE" -eq 0 ]; then echo "skip $DS"; continue; fi
  echo "=== $DS ==="
  conda run -n tsbad python src/divergence/step4_heuristics.py --kind "$KIND" --dataset "$DS" \
    2>&1 | tr '\r' '\n' | grep -E "rows,|Missing|Error" | head -2
done
echo "step 4 done"
