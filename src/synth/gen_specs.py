"""Stage A: skill -> five-element Skill Spec (JSON), via OpenRouter."""
import argparse
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, load_prompt, parse_json_block, read_jsonl, write_jsonl
from src.synth.client import OpenRouterClient

ELEMENTS = ["S1_capability_scope", "S2_when_not_to_use", "S3_contrastive_disambiguation",
            "S4_failure_modes", "S5_post_call_verification"]

_tok_re = re.compile(r"[a-z0-9]{2,}")


def _tokens(s: str):
    return _tok_re.findall(s.lower())


class NeighborIndex:
    """TF-IDF cosine over name+description, within same kind."""

    def __init__(self, skills):
        self.skills = skills
        df: Counter = Counter()
        self.docs = []
        for s in skills:
            tf = Counter(_tokens(s["name"] + " " + s["description"]))
            self.docs.append(tf)
            df.update(tf.keys())
        n = max(len(skills), 1)
        self.idf = {t: math.log(n / (1 + c)) + 1 for t, c in df.items()}
        self.vecs, self.norms, self.inv = [], [], defaultdict(list)
        for i, tf in enumerate(self.docs):
            vec = {t: c * self.idf[t] for t, c in tf.items()}
            self.vecs.append(vec)
            self.norms.append(math.sqrt(sum(v * v for v in vec.values())) or 1.0)
            for t in vec:
                self.inv[t].append(i)

    def neighbors(self, i: int, k: int = 4):
        vec, kind = self.vecs[i], self.skills[i]["kind"]
        scores: dict[int, float] = defaultdict(float)
        for t, w in vec.items():
            postings = self.inv[t]
            if len(postings) > 2000:   # skip ultra-common terms
                continue
            for j in postings:
                scores[j] += w * self.vecs[j].get(t, 0.0)
        ranked = sorted(((s / (self.norms[i] * self.norms[j]), j) for j, s in scores.items()
                         if j != i and self.skills[j]["kind"] == kind
                         and self.skills[j]["name"].lower() != self.skills[i]["name"].lower()),
                        reverse=True)
        return [self.skills[j] for _, j in ranked[:k]]


def neighbor_block(neighbors):
    if not neighbors:
        return ("(No similar skills found in the library. For S3, contrast this skill with the agent "
                "doing the task directly with general-purpose means.)")
    return "\n".join(f"- {n['name']}: {n['description'][:240]}" for n in neighbors)


def validate_spec(obj) -> list[str]:
    errs = []
    if not isinstance(obj, dict) or "elements" not in obj:
        return ["missing elements"]
    for el in ELEMENTS:
        e = obj["elements"].get(el)
        if not isinstance(e, dict):
            errs.append(f"{el}: missing")
            continue
        if len(str(e.get("text", "")).split()) < 30:
            errs.append(f"{el}: text too short")
        pr = e.get("principles")
        if not isinstance(pr, list) or not (1 <= len(pr) <= 8):
            errs.append(f"{el}: bad principles")
    if not obj.get("skill_summary"):
        errs.append("missing skill_summary")
    return errs


TITLES = {"S1_capability_scope": "S1 capability & scope",
          "S2_when_not_to_use": "S2 when NOT to use",
          "S3_contrastive_disambiguation": "S3 vs similar skills",
          "S4_failure_modes": "S4 failure modes",
          "S5_post_call_verification": "S5 post-call verification"}
PLAIN_TITLES = {"S1_capability_scope": "What it does and its boundaries",
                "S2_when_not_to_use": "When not to use it",
                "S3_contrastive_disambiguation": "Choosing between it and similar skills",
                "S4_failure_modes": "How it typically fails",
                "S5_post_call_verification": "Verifying results after use"}


def spec_digest(spec_row: dict, labeled: bool = True) -> str:
    """labeled=True: S1..S5 headers (analysis use). labeled=False: plain headers,
    no S-codes anywhere (for doc-writing prompts, to avoid jargon echo)."""
    titles = TITLES if labeled else PLAIN_TITLES
    lines = []
    for el in ELEMENTS:
        e = spec_row["elements"][el]
        lines.append(f"## {titles[el]}\n{e['text']}")
        prefix = f"- [{el.split('_')[0]}] " if labeled else "- "
        lines += [prefix + p for p in e["principles"]]
        lines.append("")
    return "\n".join(lines).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills", default=str(DATA / "skills.jsonl"))
    ap.add_argument("--out", default=str(DATA / "specs/specs.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--kind", default="", help="filter: skill_md | api_tool")
    ap.add_argument("--ids", default="", help="comma-separated skill ids")
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--model", default="deepseek/deepseek-v4-pro")
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--reasoning-effort", default="low")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--prompt-version", default="v1")
    ap.add_argument("--render-md", action="store_true")
    args = ap.parse_args()

    skills = read_jsonl(args.skills)
    index = NeighborIndex(skills)
    sel = list(range(len(skills)))
    if args.kind:
        sel = [i for i in sel if skills[i]["kind"] == args.kind]
    if args.ids:
        want = set(args.ids.split(","))
        sel = [i for i in sel if skills[i]["id"] in want]
    if args.limit:
        sel = sel[: args.limit]

    template = load_prompt(f"skill2spec_{args.prompt_version}.md")
    client = OpenRouterClient(model=args.model, temperature=args.temperature,
                              max_tokens=args.max_tokens, cache_tag=f"spec_{args.prompt_version}",
                              reasoning_effort=args.reasoning_effort)

    jobs = []
    for i in sel:
        s = skills[i]
        prompt = template.format(
            skill_name=s["name"], skill_kind=s["kind"], skill_source=s["source"],
            skill_body=s["body"], neighbor_block=neighbor_block(index.neighbors(i, args.neighbors)))
        jobs.append({"id": s["id"], "messages": [{"role": "user", "content": prompt}]})

    results = client.chat_many(jobs, concurrency=args.concurrency, desc="spec")

    ok_rows, failed = [], []
    by_id = {skills[i]["id"]: skills[i] for i in sel}
    for sid, res in results.items():
        s = by_id[sid]
        if isinstance(res, Exception):
            failed.append({"id": sid, "name": s["name"], "error": str(res)})
            continue
        try:
            obj = parse_json_block(res["text"])
            errs = validate_spec(obj)
            if errs:
                raise ValueError("; ".join(errs))
            ok_rows.append({"skill_id": sid, "skill_name": s["name"], "kind": s["kind"],
                            "source": s["source"], "skill_summary": obj["skill_summary"],
                            "elements": {el: obj["elements"][el] for el in ELEMENTS},
                            "model": args.model, "prompt_version": args.prompt_version,
                            "cost": res.get("cost", 0)})
        except Exception as e:
            failed.append({"id": sid, "name": s["name"], "error": str(e),
                           "raw_head": res["text"][:300]})

    write_jsonl(args.out, ok_rows)
    if failed:
        write_jsonl(Path(args.out).with_name("specs_failed.jsonl"), failed)
    cost = sum(r.get("cost", 0) for r in ok_rows)
    print(f"[spec] ok={len(ok_rows)} failed={len(failed)} cost=${cost:.4f} -> {args.out}")

    if args.render_md:
        md_dir = Path(args.out).parent / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        for r in ok_rows:
            safe = re.sub(r"[^\w.-]", "_", r["skill_name"])[:60]
            (md_dir / f"{r['skill_id']}_{safe}.md").write_text(
                f"# Skill Spec: {r['skill_name']}\n\n_{r['skill_summary']}_\n\n{spec_digest(r)}\n")
        print(f"[spec] markdown renders -> {md_dir}")


if __name__ == "__main__":
    main()
