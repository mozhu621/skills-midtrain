"""Build tool-use SFT data from SEEN skills (shared by arms B0 and A).

For each seen skill we synthesize realistic user requests and the correct agent
behavior — either a tool call (in-scope, S1) or an abstention/clarification
(out-of-scope or under-specified, S2). Each example is rendered into a chat row
with a multi-tool catalog (the target tool + nearby distractors) so the model must
*select*, not just emit. The assistant target contains NO spec text or S1–S5 codes,
so B0 and A train on identical behavior and any generalization gap is attributable
to midtrain alone.

Output: data/sft/sft_{train,val}.jsonl  with rows {messages, skill_id, type, split}.

Run:  scripts/07_build_sft.sh --limit 200        (pilot)
      scripts/07_build_sft.sh                     (all seen skills with specs)
"""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, load_prompt, parse_json_block, read_jsonl, write_jsonl
from src.synth.client import OpenRouterClient
from src.synth.gen_specs import NeighborIndex, neighbor_block, spec_digest
from src.exp.tool_catalog import SYSTEM_TMPL, build_catalog, minimal_schema, render_tool_call


def render_assistant(ex: dict, tool_name: str) -> str:
    if ex["kind"] == "call":
        return render_tool_call(tool_name, ex.get("arguments", {}))
    return str(ex.get("assistant", "")).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default=str(DATA / "specs/specs.jsonl"))
    ap.add_argument("--skills", default=str(DATA / "skills.jsonl"))
    ap.add_argument("--seen", default=str(DATA / "splits/seen.txt"))
    ap.add_argument("--out-dir", default=str(DATA / "sft"))
    ap.add_argument("--prompt-version", default="v1")
    ap.add_argument("--n-distractors", type=int, default=2)
    ap.add_argument("--val-frac", type=float, default=0.02)
    ap.add_argument("--limit", type=int, default=0, help="cap #seen specs (0=all)")
    ap.add_argument("--model", default="deepseek/deepseek-v4-pro")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--reasoning-effort", default="low")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    skills = read_jsonl(args.skills)
    id2idx = {s["id"]: i for i, s in enumerate(skills)}
    index = NeighborIndex(skills)
    seen = set(Path(args.seen).read_text().split())
    specs = [r for r in read_jsonl(args.specs) if r["skill_id"] in seen]
    if args.limit:
        specs = specs[: args.limit]
    print(f"[sft] seen specs to synthesize: {len(specs)}")

    template = load_prompt(f"sft_synth_{args.prompt_version}.md")
    client = OpenRouterClient(model=args.model, temperature=args.temperature,
                              max_tokens=args.max_tokens, cache_tag=f"sft_{args.prompt_version}",
                              reasoning_effort=args.reasoning_effort)

    jobs, distractor_map = [], {}
    for sp in specs:
        i = id2idx.get(sp["skill_id"])
        if i is None:
            continue
        nbrs = index.neighbors(i, args.n_distractors)
        distractor_map[sp["skill_id"]] = nbrs
        prompt = template.format(
            skill_name=sp["skill_name"], skill_kind=sp["kind"],
            skill_summary=sp["skill_summary"], spec_digest=spec_digest(sp, labeled=True),
            neighbor_block=neighbor_block(nbrs))
        jobs.append({"id": sp["skill_id"], "messages": [{"role": "user", "content": prompt}]})

    results = client.chat_many(jobs, concurrency=args.concurrency, desc="sft-synth")

    rng = random.Random(args.seed)
    rows, failed, kind_counts = [], [], Counter()
    by_id = {sp["skill_id"]: sp for sp in specs}
    for sid, res in results.items():
        sp = by_id[sid]
        if isinstance(res, Exception):
            failed.append({"id": sid, "error": str(res)})
            continue
        try:
            obj = parse_json_block(res["text"])
            schema = obj["tool_schema"]
            schema["name"] = sp["skill_name"]  # force exact tool name
            for ex in obj["examples"]:
                if ex.get("kind") not in ("call", "abstain"):
                    continue
                assistant = render_assistant(ex, sp["skill_name"])
                if not assistant or not str(ex.get("user", "")).strip():
                    continue
                tools = [schema] + [minimal_schema(d["name"], d["description"])
                                    for d in distractor_map[sid]]
                catalog = build_catalog(tools, rng)
                rows.append({
                    "skill_id": sid, "skill_name": sp["skill_name"], "kind": sp["kind"],
                    "type": ex["kind"], "split": "seen",
                    "messages": [
                        {"role": "system", "content": SYSTEM_TMPL.format(tools=catalog)},
                        {"role": "user", "content": str(ex["user"]).strip()},
                        {"role": "assistant", "content": assistant},
                    ],
                })
                kind_counts[ex["kind"]] += 1
        except Exception as e:
            failed.append({"id": sid, "error": str(e), "raw_head": res["text"][:200]})

    rng.shuffle(rows)
    n_val = max(1, int(len(rows) * args.val_frac)) if len(rows) > 50 else 0
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "sft_val.jsonl", rows[:n_val])
    write_jsonl(out / "sft_train.jsonl", rows[n_val:])
    if failed:
        write_jsonl(out / "sft_failed.jsonl", failed)
    summary = {"n_specs": len(specs), "n_rows": len(rows), "n_train": len(rows) - n_val,
               "n_val": n_val, "by_type": dict(kind_counts), "n_failed": len(failed),
               "cost_usd": round(sum(r.get("cost", 0) for r in results.values()
                                     if isinstance(r, dict)), 4)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[sft] {json.dumps(summary, ensure_ascii=False)} -> {out}")


if __name__ == "__main__":
    main()
