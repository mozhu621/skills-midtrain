#!/bin/sh
# Stage B: Spec -> multi-genre discussion docs, then quality gate.
. "$(dirname "$0")/00_env.sh"
"$PY" src/synth/gen_docs.py --prompt-version v2 "$@" && \
"$PY" src/synth/quality.py
