"""Stage B: Skill Spec -> multi-genre discussion documents (MSM doc_idea + doc stages)."""
import argparse
import random
import re
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import ROOT, DATA, load_prompt, parse_json_block, extract_tag, read_jsonl, write_jsonl, sha1_id
from src.synth.gen_specs import spec_digest
from src.synth.client import OpenRouterClient

PLAIN_FOCUS = {"S1": "capability boundaries", "S2": "when not to use it",
               "S3": "choosing between similar skills", "S4": "failure modes",
               "S5": "verifying results"}

SCODE_TO_KEY = {"S1": "S1_capability_scope", "S2": "S2_when_not_to_use",
                "S3": "S3_contrastive_disambiguation", "S4": "S4_failure_modes",
                "S5": "S5_post_call_verification"}

LANG_RULES = {
    "en": "",
    "zh": ("- Language: write the entire document in natural, fluent Simplified Chinese (简体中文). "
           "Keep the skill's own name and any API parameter/field identifiers in their original form, "
           "but all explanatory prose, headings, and reasoning must be in Chinese.\n"),
}


def build_focus_principles(spec_row, scodes):
    """Gather the actual principle sentences for the chosen elements (MSM-style assertion targeting)."""
    lines = []
    for sc in scodes:
        key = SCODE_TO_KEY.get(sc)
        if not key or key not in spec_row.get("elements", {}):
            continue
        for p in spec_row["elements"][key]["principles"]:
            lines.append(f"- {p}")
    return "\n".join(lines)


def sample_genres(genres, n, rng):
    pool, weights = list(genres), [g.get("weight", 1.0) for g in genres]
    picked = []
    for _ in range(min(n, len(pool))):
        total = sum(weights)
        r, acc = rng.uniform(0, total), 0.0
        for i, w in enumerate(weights):
            acc += w
            if r <= acc:
                picked.append(pool.pop(i))
                weights.pop(i)
                break
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default=str(DATA / "specs/specs.jsonl"))
    ap.add_argument("--out", default=str(DATA / "docs/docs.jsonl"))
    ap.add_argument("--genres", default=str(ROOT / "prompts/doc_genres.yaml"))
    ap.add_argument("--n-genres", type=int, default=4)
    ap.add_argument("--n-ideas", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="deepseek/deepseek-v4-pro")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--max-doc-tokens", type=int, default=2600)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--prompt-version", default="v1")
    ap.add_argument("--lang", default="en", choices=["en", "zh"])
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()

    specs = read_jsonl(args.specs)
    if args.limit:
        specs = specs[: args.limit]
    genres = yaml.safe_load(open(args.genres))["genres"]
    idea_tpl = load_prompt(f"doc_ideas_{args.prompt_version}.md")
    doc_tpl = load_prompt(f"doc_writer_{args.prompt_version}.md")
    client = OpenRouterClient(model=args.model, temperature=args.temperature,
                              cache_tag=f"docs_{args.prompt_version}")

    FORMAL_RULE = ("This team keeps a written usage guideline for {name}, so a single light nod to 'the guidelines' "
                   "is acceptable if it reads naturally — but do NOT pin every point on it. Reference the guideline "
                   "at most once or twice in the whole document, vary the wording, and otherwise state each principle "
                   "in your own analytical voice as a finding or judgment, never as repeated quotations from a rulebook.")
    INFORMAL_RULE = ("Do not mention any 'spec', 'guideline document', or 'usage principles document' — "
                     "the principles must appear as the author's own experience, team norms, or community "
                     "lore, with no hint that a briefing document exists.")

    # ---- stage 1: ideas per (skill, genre)
    idea_jobs, meta = [], {}
    for sp in specs:
        digest = spec_digest(sp, labeled=False)
        rng = random.Random(f"{args.seed}:{sp['skill_id']}")
        for g in sample_genres(genres, args.n_genres, rng):
            jid = f"{sp['skill_id']}::{g['name']}"
            prompt = idea_tpl.format(
                skill_name=sp["skill_name"], skill_summary=sp["skill_summary"],
                spec_digest=digest, genre=g["name"], genre_description=g["description"],
                genre_style=g["style"], n_ideas=args.n_ideas, existing_ideas_note="")
            idea_jobs.append({"id": jid, "messages": [{"role": "user", "content": prompt}],
                              "max_tokens": 1600, "seed": rng.randint(0, 10**6)})
            meta[jid] = (sp, g, digest)

    idea_results = client.chat_many(idea_jobs, concurrency=args.concurrency, desc="ideas")

    # ---- stage 2: one doc per idea
    doc_jobs, doc_meta, idea_failures = [], {}, []
    for jid, res in idea_results.items():
        sp, g, digest = meta[jid]
        if isinstance(res, Exception):
            idea_failures.append({"job": jid, "error": str(res)})
            continue
        try:
            ideas = parse_json_block(res["text"])
            assert isinstance(ideas, list) and ideas
        except Exception as e:
            idea_failures.append({"job": jid, "error": f"parse: {e}", "raw_head": res["text"][:200]})
            continue
        for k, idea in enumerate(ideas[: args.n_ideas]):
            if not isinstance(idea, dict) or not idea.get("idea"):
                continue
            elements = [e for e in idea.get("elements", []) if re.match(r"^S[1-5]$", str(e))] or ["S2", "S3"]
            focus = ", ".join(sorted({PLAIN_FOCUS[e] for e in elements}))
            focus_principles = build_focus_principles(sp, elements)
            did = sha1_id(jid, str(k), str(idea.get("name", "")))
            rule = FORMAL_RULE.format(name=sp["skill_name"]) if g.get("formal_spec_reference") else INFORMAL_RULE
            prompt = doc_tpl.format(
                skill_name=sp["skill_name"], skill_summary=sp["skill_summary"], spec_digest=digest,
                genre=g["name"], genre_description=g["description"], genre_style=g["style"],
                doc_idea=idea["idea"], focus_elements=focus, focus_principles=focus_principles,
                spec_reference_rule=rule, language_rule=LANG_RULES[args.lang])
            doc_jobs.append({"id": did, "messages": [{"role": "user", "content": prompt}],
                             "max_tokens": args.max_doc_tokens})
            doc_meta[did] = (sp, g, idea, elements)

    doc_results = client.chat_many(doc_jobs, concurrency=args.concurrency, desc="docs")

    rows, doc_failures = [], []
    for did, res in doc_results.items():
        sp, g, idea, elements = doc_meta[did]
        if isinstance(res, Exception):
            doc_failures.append({"doc": did, "skill": sp["skill_name"], "error": str(res)})
            continue
        try:
            content = extract_tag(res["text"], "content")
        except ValueError as e:
            doc_failures.append({"doc": did, "skill": sp["skill_name"], "error": str(e),
                                 "raw_head": res["text"][:200]})
            continue
        rows.append({"doc_id": did, "text": content, "skill_id": sp["skill_id"],
                     "skill_name": sp["skill_name"], "kind": sp["kind"], "genre": g["name"],
                     "idea_name": idea.get("name", ""), "idea": idea["idea"],
                     "elements": elements, "model": args.model,
                     "prompt_version": args.prompt_version, "cost": res.get("cost", 0),
                     "n_words": len(content.split())})

    write_jsonl(args.out, rows)
    fails = idea_failures + doc_failures
    if fails:
        write_jsonl(Path(args.out).with_name("docs_failed.jsonl"), fails)
    cost = sum(r["cost"] for r in rows)
    words = sum(r["n_words"] for r in rows)
    print(f"[docs] docs={len(rows)} idea_fail={len(idea_failures)} doc_fail={len(doc_failures)} "
          f"words={words} (~{int(words*1.35)} toks) cost=${cost:.4f} -> {args.out}")


if __name__ == "__main__":
    main()
