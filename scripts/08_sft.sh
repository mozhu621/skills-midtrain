#!/bin/sh
# Tool-use SFT for one arm. Choose the arm with --model / --output-dir.
#   B0 smoke:  scripts/08_sft.sh --smoke --model Qwen/Qwen3.5-4B-Base --output-dir checkpoints/sft_b0
#   A  (8x) :  NGPU=8 scripts/08_sft.sh --model checkpoints/ssm_qwen3p5_4b/final --output-dir checkpoints/sft_a
. "$(dirname "$0")/00_env.sh"
if [ -n "$NGPU" ] && [ "$NGPU" -gt 1 ]; then
  "$PY" -m torch.distributed.run --nproc_per_node="$NGPU" \
    src/exp/sft_train.py --config configs/sft_qwen3p5_4b.yaml "$@"
else
  "$PY" src/exp/sft_train.py --config configs/sft_qwen3p5_4b.yaml "$@"
fi
