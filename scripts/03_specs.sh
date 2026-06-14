#!/bin/sh
# Stage A: skill -> five-element Skill Spec. Pass --limit N for partial runs.
. "$(dirname "$0")/00_env.sh"
"$PY" src/synth/gen_specs.py --prompt-version v1 --render-md "$@"
