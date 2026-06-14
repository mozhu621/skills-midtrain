#!/bin/sh
# Stage 0b: parse all sources into unified data/skills.jsonl.
. "$(dirname "$0")/00_env.sh"
"$PY" src/collect/parse_skills.py "$@"
