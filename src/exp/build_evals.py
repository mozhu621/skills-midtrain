"""Generate the E1-E6 eval battery from Skill Specs.

  E1 select (ID, seen)        — task + tool menu; answer = right tool or NONE
  E2 select (OOD, held-out)   — same form, skills never seen in training  [main metric]
  E3 abstain (OOD)            — should_call true/false; tests when NOT to call (S2)
  E4 disambiguate (OOD)       — pick between a tool and its confusable sibling (S3)
  E5 args (OOD)               — required arguments must appear, none hallucinated (S1/S4)
  E6 verify (OOD)             — a failed tool result is injected; does the agent react? (S5)

Seen specs yield E1 only; held-out specs yield E2-E6. Each item carries everything the
runner/judge needs (prompt messages, gradeable answer, spec digest).

Run:  scripts/09_build_evals.sh --specs data/debug/specs_pilot_v1.jsonl   (pilot)
      scripts/09_build_evals.sh                                            (all specs)
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
from src.exp.split import top_neighbor_scored
from src.exp.tool_catalog import minimal_schema, system_message, render_tool_call


def dedup_tools(tools: list[dict]) -> list[dict]:
    """Drop tools whose name already appeared (same skill name across repos), keep order."""
    seen, out = set(), []
    for t in tools:
        if t["name"] in seen:
            continue
        seen.add(t["name"])
        out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default=str(DATA / "specs/specs.jsonl"))
    ap.add_argument("--skills", default=str(DATA / "skills.jsonl"))
    ap.add_argument("--seen", default=str(DATA / "splits/seen.txt"))
    ap.add_argument("--heldout", default=str(DATA / "splits/heldout.txt"))
    ap.add_argument("--out", default=str(DATA / "evals/evals.jsonl"))
    ap.add_argument("--prompt-version", default="v1")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="deepseek/deepseek-v4-pro")
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--max-tokens", type=int, default=5000)
    ap.add_argument("--reasoning-effort", default="low")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    skills = read_jsonl(args.skills)
    id2idx = {s["id"]: i for i, s in enumerate(skills)}
    index = NeighborIndex(skills)
    seen = set(Path(args.seen).read_text().split())
    heldout = set(Path(args.heldout).read_text().split()) if Path(args.heldout).exists() else set()
    specs = [r for r in read_jsonl(args.specs) if r["skill_id"] in seen or r["skill_id"] in heldout]
    if args.limit:
        specs = specs[: args.limit]
    print(f"[evals] specs in split: {len(specs)} (seen menu=E1, heldout menu=E2-E6)")

    template = load_prompt(f"eval_gen_{args.prompt_version}.md")
    client = OpenRouterClient(model=args.model, temperature=args.temperature,
                              max_tokens=args.max_tokens, cache_tag=f"evalgen_{args.prompt_version}",
                              reasoning_effort=args.reasoning_effort)

    jobs, meta = [], {}
    for sp in specs:
        i = id2idx.get(sp["skill_id"])
        if i is None:
            continue
        nbrs = index.neighbors(i, 3)
        j, _ = top_neighbor_scored(index, i)
        sib = skills[j]["name"] if j is not None else "(no close sibling)"
        meta[sp["skill_id"]] = {"nbrs": nbrs, "sib": sib}
        prompt = template.format(
            skill_name=sp["skill_name"], skill_kind=sp["kind"], skill_summary=sp["skill_summary"],
            confusable_name=sib, spec_digest=spec_digest(sp, labeled=True),
            neighbor_block=neighbor_block(nbrs))
        jobs.append({"id": sp["skill_id"], "messages": [{"role": "user", "content": prompt}]})

    results = client.chat_many(jobs, concurrency=args.concurrency, desc="eval-gen")

    rng = random.Random(args.seed)
    items, failed, counts = [], [], Counter()
    by_id = {sp["skill_id"]: sp for sp in specs}

    def base(sp, etype, k):
        return {"id": f"{sp['skill_id']}_{etype}_{k}", "etype": etype,
                "split": "seen" if sp["skill_id"] in seen else "heldout",
                "skill_id": sp["skill_id"], "skill_name": sp["skill_name"], "kind": sp["kind"],
                "skill_summary": sp["skill_summary"], "spec_digest": spec_digest(sp, labeled=True)}

    for sid, res in results.items():
        sp = by_id[sid]
        if isinstance(res, Exception):
            failed.append({"id": sid, "error": str(res)})
            continue
        try:
            obj = parse_json_block(res["text"])
        except Exception as e:
            failed.append({"id": sid, "error": str(e), "raw_head": res["text"][:200]})
            continue
        nbrs, sib = meta[sid]["nbrs"], meta[sid]["sib"]
        target = minimal_schema(sp["skill_name"], sp["skill_summary"])
        std_tools = dedup_tools([target] + [minimal_schema(n["name"], n["description"])
                                            for n in nbrs])[:3]
        std_names = [t["name"] for t in std_tools]
        is_seen = sid in seen

        def select_item(it, k):
            etype = "E1" if is_seen else "E2"
            row = base(sp, etype, k)
            row.update({"messages": [system_message(std_tools, rng),
                                     {"role": "user", "content": str(it["task"]).strip()}],
                        "candidates": std_names, "answer": str(it.get("answer", "NONE")).strip()})
            return row

        for k, it in enumerate(obj.get("select", [])):
            items.append(select_item(it, k)); counts["E1" if is_seen else "E2"] += 1

        if is_seen:
            continue  # seen skills contribute ID selection only

        for k, it in enumerate(obj.get("abstain", [])):
            row = base(sp, "E3", k)
            row.update({"messages": [system_message(std_tools, rng),
                                     {"role": "user", "content": str(it["task"]).strip()}],
                        "candidates": std_names, "should_call": bool(it.get("should_call"))})
            items.append(row); counts["E3"] += 1

        dis_tools = dedup_tools([target, minimal_schema(sib, "")]
                                + [minimal_schema(n["name"], n["description"]) for n in nbrs])[:3]
        dis_names = [t["name"] for t in dis_tools]
        for k, it in enumerate(obj.get("disambiguate", [])):
            row = base(sp, "E4", k)
            row.update({"messages": [system_message(dis_tools, rng),
                                     {"role": "user", "content": str(it["task"]).strip()}],
                        "candidates": dis_names, "answer": str(it.get("answer", "")).strip()})
            items.append(row); counts["E4"] += 1

        for k, it in enumerate(obj.get("args", [])):
            row = base(sp, "E5", k)
            row.update({"messages": [system_message(std_tools, rng),
                                     {"role": "user", "content": str(it["task"]).strip()}],
                        "candidates": std_names,
                        "required_args": it.get("required_args", []), "note": it.get("note", "")})
            items.append(row); counts["E5"] += 1

        for k, it in enumerate(obj.get("verify", [])):
            row = base(sp, "E6", k)
            tool_result = str(it.get("tool_result", "")).strip()
            row.update({"messages": [
                system_message(std_tools, rng),
                {"role": "user", "content": str(it["task"]).strip()},
                {"role": "assistant", "content": render_tool_call(sp["skill_name"], {})},
                {"role": "user", "content": f"<tool_result>\n{tool_result}\n</tool_result>\n"
                                            "The tool call above returned this. Continue handling "
                                            "the user's request."},
            ], "tool_result": tool_result})
            items.append(row); counts["E6"] += 1

    rng.shuffle(items)
    write_jsonl(args.out, items)
    if failed:
        write_jsonl(Path(args.out).with_name("evals_failed.jsonl"), failed)
    summary = {"n_specs": len(specs), "n_items": len(items), "by_etype": dict(counts),
               "n_failed": len(failed),
               "cost_usd": round(sum(r.get("cost", 0) for r in results.values()
                                     if isinstance(r, dict)), 4)}
    Path(args.out).with_name("evals_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[evals] {json.dumps(summary, ensure_ascii=False)} -> {args.out}")


if __name__ == "__main__":
    main()
