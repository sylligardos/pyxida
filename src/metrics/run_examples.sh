#!/usr/bin/env bash
# Example detector runs on TimeEval and TAB for the Pyxida demo: a few small
# collections, fast unsupervised TSB-AD detectors, then metrics. Resumable.
# Run from the repo root.
set -e
UNI="SR POLY Sub_PCA IForest MatrixProfile KShapeAD"
MULTI="PCA HBOS IForest COPOD CBLOF"
RUN="conda run -n tsbad-run python src/metrics/run_detectors.py"

$RUN --benchmark timeeval --kind uni   --datasets NAB NASA-MSL NASA-SMAP MGAB Dodgers --detectors $UNI
$RUN --benchmark timeeval --kind multi --datasets SMD Daphnet --detectors $MULTI
$RUN --benchmark tab --kind uni   --datasets NAB YAHOO NASA-MSL-new NASA-SMAP-new MGAB --detectors $UNI
$RUN --benchmark tab --kind multi --datasets ASD SKAB TAO --detectors $MULTI

for b in timeeval tab; do
  conda run -n ffvus python src/metrics/compute_metrics.py --benchmark $b
done
echo "=== examples done"
