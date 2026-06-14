#!/bin/sh
# Freeze a seen / held-out skill split (+ confusable pairs) for OOD eval.
#   scripts/06_split.sh                 (15% held-out, seed 1234)
#   scripts/06_split.sh --heldout-frac 0.20 --seed 7
. "$(dirname "$0")/00_env.sh"
"$PY" src/exp/split.py "$@"
