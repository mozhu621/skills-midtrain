#!/bin/sh
# Synthesize tool-use SFT data from seen skills (shared by arms B0 and A).
#   scripts/07_build_sft.sh --specs data/debug/specs_pilot_v1.jsonl --limit 5   (pilot)
#   scripts/07_build_sft.sh                                                       (all seen)
. "$(dirname "$0")/00_env.sh"
"$PY" src/exp/build_sft.py "$@"
