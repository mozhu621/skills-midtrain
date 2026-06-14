#!/bin/sh
# Stage C: pack corpus then midtrain Qwen3.5-4B-Base.
#   smoke:  scripts/05_train.sh --smoke          (single GPU, 4 steps)
#   full:   NGPU=8 scripts/05_train.sh           (torchrun, 8x)
. "$(dirname "$0")/00_env.sh"
"$PY" src/train/build_corpus.py || exit 1
if [ -n "$NGPU" ] && [ "$NGPU" -gt 1 ]; then
  "$PY" -m torch.distributed.run --nproc_per_node="$NGPU" \
    src/train/train_midtrain.py --config configs/train_qwen3p5_4b.yaml "$@"
else
  "$PY" src/train/train_midtrain.py --config configs/train_qwen3p5_4b.yaml "$@"
fi
