#!/bin/sh
# Stage 0a: download skill sources (repos + website harvest + tool datasets).
. "$(dirname "$0")/00_env.sh"
"$PY" src/collect/download.py "$@"
