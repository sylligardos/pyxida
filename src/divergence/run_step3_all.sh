#!/usr/bin/env bash
# Full step-3 sweep, one shard per dataset so a crash costs one dataset, not the run.
# Run from the repo root, in the ffvus environment (torch+CUDA).
set -u
cd "$(dirname "$0")/../.."
LOG=data/divergence/step3_run.log
: > "$LOG"
for DS in $(cat src/divergence/datasets.txt); do
  OUT="data/divergence/combos_uni_${DS}.parquet"
  if [ -f "$OUT" ]; then echo "skip $DS (exists)" | tee -a "$LOG"; continue; fi
  echo "=== $DS  $(date +%H:%M:%S) ===" | tee -a "$LOG"
  conda run -n ffvus python src/divergence/step3_combos.py --dataset "$DS" --max-k 3 \
    2>&1 | tr '\r' '\n' | grep -viE "it/s\]|^[[:space:]]*$" | tail -4 | tee -a "$LOG"
done
echo "ALL DONE $(date +%H:%M:%S)" | tee -a "$LOG"
