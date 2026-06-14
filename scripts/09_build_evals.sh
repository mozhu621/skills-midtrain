#!/bin/sh
# Generate the E1-E6 eval battery from specs (seen->E1, held-out->E2-E6).
#   scripts/09_build_evals.sh --specs data/debug/specs_pilot_v1.jsonl   (pilot)
#   scripts/09_build_evals.sh                                            (all specs)
. "$(dirname "$0")/00_env.sh"
"$PY" src/exp/build_evals.py "$@"
