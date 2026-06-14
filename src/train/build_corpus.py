"""Pack SSM docs (+ optional replay corpus) into fixed-length token blocks for midtraining."""
import argparse
import json
import random
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, read_jsonl


def load_texts(path, text_key="text"):
    rows = read_jsonl(path)
    return [r[text_key] for r in rows if r.get(text_key, "").strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=str(DATA / "docs/docs_clean.jsonl"))
    ap.add_argument("--replay", default="", help="optional general-corpus jsonl ({'text':...}) for replay mixing")
    ap.add_argument("--replay-ratio", type=float, default=0.10, help="fraction of final tokens from replay")
    ap.add_argument("--tokenizer", default="Qwen/Qwen3.5-4B-Base")
    ap.add_argument("--seq-len", type=int, default=4096)
    ap.add_argument("--val-frac", type=float, default=0.005)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out-dir", default=str(DATA / "corpus"))
    args = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    eos = tok.eos_token_id
    assert eos is not None, "tokenizer has no eos token"

    docs = load_texts(args.docs)
    rng = random.Random(args.seed)
    rng.shuffle(docs)
    print(f"[corpus] ssm docs: {len(docs)}")

    def encode_all(texts, desc):
        ids = []
        from tqdm import tqdm
        for t in tqdm(texts, desc=desc):
            ids.extend(tok.encode(t) + [eos])
        return ids

    ssm_ids = encode_all(docs, "tokenize-ssm")
    all_ids = ssm_ids
    n_replay = 0
    if args.replay:
        target = int(len(ssm_ids) * args.replay_ratio / max(1e-9, (1 - args.replay_ratio)))
        replay_texts = load_texts(args.replay)
        rng.shuffle(replay_texts)
        replay_ids: list[int] = []
        for t in replay_texts:
            if len(replay_ids) >= target:
                break
            replay_ids.extend(tok.encode(t) + [eos])
        n_replay = len(replay_ids)
        # interleave at block granularity later via shuffle of blocks
        all_ids = ssm_ids + replay_ids[:target]
    else:
        print("[corpus] WARNING: no replay corpus given; corpus is 100% SSM docs "
              "(fine for smoke tests, NOT for real midtraining runs)")

    L = args.seq_len
    n_blocks = len(all_ids) // L
    arr = np.array(all_ids[: n_blocks * L], dtype=np.uint32).reshape(n_blocks, L)
    perm = np.random.RandomState(args.seed).permutation(n_blocks)
    arr = arr[perm]

    n_val = max(1, int(n_blocks * args.val_frac)) if n_blocks > 1 else 0
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    arr[n_val:].tofile(out / "train.bin")
    if n_val:
        arr[:n_val].tofile(out / "val.bin")
    meta = {"tokenizer": args.tokenizer, "seq_len": L, "dtype": "uint32",
            "n_train_blocks": int(n_blocks - n_val), "n_val_blocks": int(n_val),
            "n_ssm_tokens": len(ssm_ids), "n_replay_tokens": n_replay,
            "total_tokens": int(n_blocks * L)}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[corpus] {meta}")


if __name__ == "__main__":
    main()
