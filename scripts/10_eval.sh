#!/bin/sh
# Run + score one model on the E1-E6 battery (mean +/- stderr per E-type).
#   B0:  scripts/10_eval.sh --model checkpoints/sft_b0/final --tag B0
#   A :  scripts/10_eval.sh --model checkpoints/sft_a/final  --tag A
#   B1:  scripts/10_eval.sh --model Qwen/Qwen3.5-4B-Base --in-context --tag B1
#   OOD only, 3 epochs:  scripts/10_eval.sh --model ... --etypes E2,E3,E4,E5,E6 --epochs 3
. "$(dirname "$0")/00_env.sh"
"$PY" src/exp/run_eval.py "$@"
