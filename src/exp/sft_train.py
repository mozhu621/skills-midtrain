"""Tool-use SFT trainer (completion-only loss), shared recipe for arms B0 and A.

Arm B0 (SFT-only):  --model Qwen/Qwen3.5-4B-Base
Arm A  (SSM->SFT):  --model checkpoints/ssm_qwen3p5_4b/final
Both arms use the SAME --data, --config and hyperparameters, so the only difference
is the base weights — that is what isolates the midtrain effect.

Single GPU smoke:  python src/exp/sft_train.py --config configs/sft_qwen3p5_4b.yaml --smoke
8x GPU:            torchrun --nproc_per_node=8 src/exp/sft_train.py --config configs/sft_qwen3p5_4b.yaml --model <base-or-midtrained>
"""
import argparse
import json
from pathlib import Path

import torch
import yaml
from torch.utils.data import Dataset

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import ROOT, read_jsonl
from src.exp.chat_format import encode_completion_only


class ChatSFTDataset(Dataset):
    def __init__(self, path, tok, max_len: int):
        self.rows, self.tok, self.max_len = [], tok, max_len
        skipped = 0
        for r in read_jsonl(path):
            enc = encode_completion_only(tok, r["messages"], max_len)
            if enc is None:
                skipped += 1
                continue
            self.rows.append(enc)
        print(f"[sft] {path}: {len(self.rows)} examples ({skipped} skipped)")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        ids, labels = self.rows[i]
        return {"input_ids": ids, "labels": labels}


class PadCollator:
    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, batch):
        maxlen = max(len(b["input_ids"]) for b in batch)
        input_ids, labels, attn = [], [], []
        for b in batch:
            n = maxlen - len(b["input_ids"])
            input_ids.append(b["input_ids"] + [self.pad_id] * n)
            labels.append(b["labels"] + [-100] * n)
            attn.append([1] * len(b["input_ids"]) + [0] * n)
        return {"input_ids": torch.tensor(input_ids), "labels": torch.tensor(labels),
                "attention_mask": torch.tensor(attn)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs/sft_qwen3p5_4b.yaml"))
    ap.add_argument("--model", default="", help="override config model (selects the arm)")
    ap.add_argument("--data", default="", help="override config data_train")
    ap.add_argument("--output-dir", default="", help="override config output_dir")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    model_id = args.model or cfg["model"]
    data_train = args.data or cfg["data_train"]
    output_dir = args.output_dir or cfg["output_dir"]

    from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer,
                              TrainingArguments)

    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    max_len = cfg.get("max_len", 2048)
    train_ds = ChatSFTDataset(data_train, tok, max_len)
    val_path = cfg.get("data_val", "")
    val_ds = ChatSFTDataset(val_path, tok, max_len) if val_path and Path(val_path).exists() else None

    attn = cfg.get("attn_implementation", "flash_attention_2")
    try:
        import flash_attn  # noqa: F401
    except ImportError:
        attn = "sdpa"
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.bfloat16, attn_implementation=attn, trust_remote_code=True)
    model.config.use_cache = False
    if cfg.get("gradient_checkpointing", True):
        model.gradient_checkpointing_enable()

    max_steps = 4 if args.smoke else cfg.get("max_steps", -1)
    targs = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=1 if args.smoke else cfg.get("per_device_batch_size", 2),
        gradient_accumulation_steps=1 if args.smoke else cfg.get("grad_accum", 8),
        num_train_epochs=cfg.get("epochs", 3),
        max_steps=max_steps,
        learning_rate=float(cfg.get("lr", 1e-5)),
        lr_scheduler_type=cfg.get("lr_scheduler", "cosine"),
        warmup_ratio=cfg.get("warmup_ratio", 0.03),
        weight_decay=cfg.get("weight_decay", 0.0),
        max_grad_norm=cfg.get("max_grad_norm", 1.0),
        bf16=True,
        logging_steps=1 if args.smoke else cfg.get("logging_steps", 10),
        save_steps=cfg.get("save_steps", 500),
        save_total_limit=cfg.get("save_total_limit", 2),
        eval_strategy="steps" if val_ds is not None and not args.smoke else "no",
        eval_steps=cfg.get("eval_steps", 200),
        per_device_eval_batch_size=1,
        report_to=cfg.get("report_to", []),
        ddp_find_unused_parameters=False,
        dataloader_num_workers=2,
        seed=cfg.get("seed", 1234),
    )
    trainer = Trainer(model=model, args=targs, train_dataset=train_ds, eval_dataset=val_ds,
                      data_collator=PadCollator(tok.pad_token_id), processing_class=tok)
    trainer.train(resume_from_checkpoint=cfg.get("resume", None))
    if not args.smoke:
        final = Path(output_dir) / "final"
        trainer.save_model(str(final))
        tok.save_pretrained(str(final))
        (final / "sft_meta.json").write_text(json.dumps(
            {"base_model": model_id, "data_train": data_train}, indent=2))
    print("[sft] done")


if __name__ == "__main__":
    main()
