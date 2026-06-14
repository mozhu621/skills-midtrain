#!/bin/sh
# Shared env for pipeline scripts. Usage: . scripts/00_env.sh
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=/raid/longhorn/yuhao/envs/living-lm/bin/python
export PYTHONUNBUFFERED=1
cd "$ROOT" || exit 1
