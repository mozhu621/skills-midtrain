"""Run a model over the E1-E6 battery and score it (mean ± stderr per E-type).

Scoring:
  E1/E2/E4  exact-match on the dispatched tool name (or NONE)            — no judge
  E3        over-trigger / under-trigger / accuracy from call-vs-abstain — no judge
  E5/E6     LLM-judge (PASS/FAIL) via OpenRouterClient                   — judge model

Arms:
  B0  --model checkpoints/sft_b0/final
  A   --model checkpoints/sft_a/final
  B1  --model Qwen/Qwen3.5-4B-Base --in-context     (spec injected into the prompt, no FT)

Multiple --epochs resample at temperature>0 so stderr reflects sampling noise (per MSM).

Run:  scripts/10_eval.sh --model checkpoints/sft_b0/final
      scripts/10_eval.sh --model Qwen/Qwen3.5-4B-Base --in-context
"""
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import torch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, parse_json_block, read_jsonl, load_prompt
from src.synth.client import OpenRouterClient
from src.exp.chat_format import build_prompt

CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def parse_call(text: str):
    """Return (called_tool_name | None, arguments | None)."""
    m = CALL_RE.search(text)
    if not m:
        return None, None
    try:
        obj = parse_json_block(m.group(1))
        return str(obj.get("name", "")).strip() or None, obj.get("arguments")
    except Exception:
        return None, None


def match_name(pred: str | None, candidates: list[str]) -> str:
    """Normalize a predicted tool name to a candidate (case-insensitive) or 'NONE'."""
    if not pred:
        return "NONE"
    low = pred.lower()
    for c in candidates:
        if c.lower() == low:
            return c
    return pred  # unknown name -> counts as wrong (not in menu)


def inject_spec(messages, spec_digest):
    out = [dict(m) for m in messages]
    for m in out:
        if m["role"] == "system":
            m["content"] = (m["content"] + "\n\n# Guidance for the tools above\n" + spec_digest)
            return out
    out.insert(0, {"role": "system", "content": spec_digest})
    return out


class HFRunner:
    def __init__(self, model_id, max_new_tokens=256, temperature=0.7, batch_size=16):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        self.tok.padding_side = "left"
        attn = "flash_attention_2"
        try:
            import flash_attn  # noqa: F401
        except ImportError:
            attn = "sdpa"
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=torch.bfloat16, attn_implementation=attn,
            trust_remote_code=True, device_map="auto")
        self.model.eval()
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.batch_size = batch_size

    @torch.no_grad()
    def generate(self, list_of_messages) -> list[str]:
        prompts = [build_prompt(self.tok, m, add_generation_prompt=True) for m in list_of_messages]
        outs = []
        for s in range(0, len(prompts), self.batch_size):
            chunk = prompts[s:s + self.batch_size]
            enc = self.tok(chunk, return_tensors="pt", padding=True,
                           add_special_tokens=False).to(self.model.device)
            gen = self.model.generate(
                **enc, max_new_tokens=self.max_new_tokens,
                do_sample=self.temperature > 0, temperature=max(self.temperature, 1e-5),
                top_p=0.95, pad_token_id=self.tok.pad_token_id)
            for i in range(len(chunk)):
                new = gen[i, enc["input_ids"].shape[1]:]
                outs.append(self.tok.decode(new, skip_special_tokens=True).strip())
        return outs


def mean_stderr(vals: list[float]):
    n = len(vals)
    if n == 0:
        return 0.0, 0.0, 0
    mean = sum(vals) / n
    if n == 1:
        return mean, 0.0, 1
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    return mean, math.sqrt(var / n), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="HF path/id of the model under test")
    ap.add_argument("--evals", default=str(DATA / "evals/evals.jsonl"))
    ap.add_argument("--out-dir", default=str(DATA / "evals/results"))
    ap.add_argument("--tag", default="", help="run label (default: model dir name)")
    ap.add_argument("--etypes", default="", help="comma list filter, e.g. E2,E3")
    ap.add_argument("--in-context", action="store_true", help="arm B1: inject spec into prompt")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--judge-model", default="deepseek/deepseek-v4-pro")
    ap.add_argument("--judge-concurrency", type=int, default=8)
    args = ap.parse_args()

    items = read_jsonl(args.evals)
    if args.etypes:
        want = set(args.etypes.split(","))
        items = [it for it in items if it["etype"] in want]
    if args.limit:
        items = items[: args.limit]
    print(f"[eval] items: {len(items)} | epochs: {args.epochs} | in_context: {args.in_context}")

    runner = HFRunner(args.model, max_new_tokens=args.max_new_tokens,
                      temperature=args.temperature, batch_size=args.batch_size)

    records = []
    for ep in range(args.epochs):
        msgs = [inject_spec(it["messages"], it["spec_digest"]) if args.in_context else it["messages"]
                for it in items]
        completions = runner.generate(msgs)
        for it, comp in zip(items, completions):
            records.append({"epoch": ep, "item": it, "response": comp})

    # ---- deterministic scoring (E1/E2/E3/E4) + collect judge jobs (E5/E6) ----
    judge_template = load_prompt("eval_judge_v1.md")
    judge_jobs, judge_index = [], {}
    per_etype: dict[str, list[float]] = defaultdict(list)
    over_trigger, under_trigger = [], []

    for ridx, rec in enumerate(records):
        it, etype, comp = rec["item"], rec["item"]["etype"], rec["response"]
        name, call_args = parse_call(comp)
        called = name is not None

        if etype in ("E1", "E2", "E4"):
            pred = match_name(name, it["candidates"])
            ans = it["answer"]
            correct = 1.0 if pred.lower() == ans.lower() else 0.0
            per_etype[etype].append(correct)
            rec["pred"], rec["correct"] = pred, correct
        elif etype == "E3":
            should = it["should_call"]
            correct = 1.0 if called == should else 0.0
            per_etype["E3"].append(correct)
            if not should:
                over_trigger.append(1.0 if called else 0.0)
            else:
                under_trigger.append(0.0 if called else 1.0)
            rec["called"], rec["correct"] = called, correct
        elif etype in ("E5", "E6"):
            if etype == "E5":
                ctx = (f"Task: {it['messages'][-1]['content']}\n"
                       f"Required arguments: {it.get('required_args')}\n"
                       f"Note: {it.get('note', '')}")
            else:
                ctx = (f"Task: {it['messages'][1]['content']}\n"
                       f"Injected tool result: {it.get('tool_result', '')}")
            prompt = judge_template.format(
                item_type="args" if etype == "E5" else "verify",
                skill_name=it["skill_name"], skill_summary=it["skill_summary"],
                spec_digest=it["spec_digest"], item_context=ctx, model_response=comp)
            jid = f"j{ridx}"
            judge_jobs.append({"id": jid, "messages": [{"role": "user", "content": prompt}]})
            judge_index[jid] = ridx

    if judge_jobs:
        judge = OpenRouterClient(model=args.judge_model, temperature=0.0, max_tokens=600,
                                 cache_tag="eval_judge", reasoning_effort="low")
        jres = judge.chat_many(judge_jobs, concurrency=args.judge_concurrency, desc="judge")
        for jid, res in jres.items():
            rec = records[judge_index[jid]]
            etype = rec["item"]["etype"]
            verdict = 0.0
            if isinstance(res, dict):
                try:
                    verdict = 1.0 if parse_json_block(res["text"]).get("verdict", "").upper() == "PASS" else 0.0
                except Exception:
                    verdict = 0.0
            per_etype[etype].append(verdict)
            rec["correct"] = verdict

    # ---- aggregate ----
    report = {}
    for etype, vals in sorted(per_etype.items()):
        mean, se, n = mean_stderr(vals)
        report[etype] = {"metric": "accuracy" if etype in ("E1", "E2", "E3", "E4") else "pass_rate",
                         "mean": round(mean, 4), "stderr": round(se, 4), "n": n}
    if over_trigger:
        m, se, n = mean_stderr(over_trigger)
        report["E3_over_trigger"] = {"metric": "rate", "mean": round(m, 4), "stderr": round(se, 4), "n": n}
    if under_trigger:
        m, se, n = mean_stderr(under_trigger)
        report["E3_under_trigger"] = {"metric": "rate", "mean": round(m, 4), "stderr": round(se, 4), "n": n}

    tag = args.tag or Path(args.model.rstrip("/")).name
    if args.in_context:
        tag += "_incontext"
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{tag}_records.jsonl", "w") as f:
        for rec in records:
            f.write(json.dumps({"epoch": rec["epoch"], "etype": rec["item"]["etype"],
                                "skill_id": rec["item"]["skill_id"],
                                "correct": rec.get("correct"), "response": rec["response"][:500]},
                               ensure_ascii=False) + "\n")
    summary = {"model": args.model, "tag": tag, "in_context": args.in_context,
               "epochs": args.epochs, "n_items": len(items), "report": report}
    (out / f"{tag}_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[eval] {json.dumps(report, ensure_ascii=False)}")
    print(f"[eval] -> {out}/{tag}_summary.json")


if __name__ == "__main__":
    main()
