"""Skill Spec Midtraining: continued pretraining of a base LM on packed SSM corpus.

Single GPU:  python src/train/train_midtrain.py --config configs/train_qwen3p5_4b.yaml --smoke
8x GPU:      torchrun --nproc_per_node=8 src/train/train_midtrain.py --config configs/train_qwen3p5_4b.yaml
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
import yaml
from torch.utils.data import Dataset

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import ROOT


class PackedDataset(Dataset):
    def __init__(self, bin_path: Path, seq_len: int):
        self.data = np.memmap(bin_path, dtype=np.uint32, mode="r")
        self.seq_len = seq_len
        self.n = len(self.data) // seq_len

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        chunk = torch.from_numpy(self.data[i * self.seq_len:(i + 1) * self.seq_len].astype(np.int64))
        return {"input_ids": chunk, "labels": chunk.clone()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs/train_qwen3p5_4b.yaml"))
    ap.add_argument("--smoke", action="store_true", help="tiny run: few steps, small seq slices")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))

    from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer,
                              TrainingArguments)

    corpus = Path(cfg["corpus_dir"])
    meta = json.loads((corpus / "meta.json").read_text())
    seq_len = meta["seq_len"]
    train_ds = PackedDataset(corpus / "train.bin", seq_len)
    val_path = corpus / "val.bin"
    val_ds = PackedDataset(val_path, seq_len) if val_path.exists() else None
    print(f"[train] blocks: train={len(train_ds)} val={len(val_ds) if val_ds else 0} seq_len={seq_len}")

    attn = cfg.get("attn_implementation", "flash_attention_2")
    try:
        import flash_attn  # noqa: F401
    except ImportError:
        attn = "sdpa"
    model = AutoModelForCausalLM.from_pretrained(
        cfg["model"], dtype=torch.bfloat16, attn_implementation=attn, trust_remote_code=True)
    model.config.use_cache = False
    if cfg.get("gradient_checkpointing", True):
        model.gradient_checkpointing_enable()
    tok = AutoTokenizer.from_pretrained(cfg["model"], trust_remote_code=True)

    max_steps = 4 if args.smoke else cfg.get("max_steps", -1)
    targs = TrainingArguments(
        output_dir=cfg["output_dir"],
        per_device_train_batch_size=1 if args.smoke else cfg.get("per_device_batch_size", 2),
        gradient_accumulation_steps=1 if args.smoke else cfg.get("grad_accum", 8),
        num_train_epochs=cfg.get("epochs", 1),
        max_steps=max_steps,
        learning_rate=float(cfg.get("lr", 2e-5)),
        lr_scheduler_type=cfg.get("lr_scheduler", "cosine"),
        warmup_steps=cfg.get("warmup_steps", 50),
        weight_decay=cfg.get("weight_decay", 0.1),
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

    trainer = Trainer(model=model, args=targs, train_dataset=train_ds,
                      eval_dataset=val_ds, processing_class=tok)
    trainer.train(resume_from_checkpoint=cfg.get("resume", None))
    if not args.smoke:
        trainer.save_model(str(Path(cfg["output_dir"]) / "final"))
        tok.save_pretrained(str(Path(cfg["output_dir"]) / "final"))
    print("[train] done")


if __name__ == "__main__":
    main()
