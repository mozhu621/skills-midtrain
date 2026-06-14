"""Audit corpus for fabrication (编故事): invented specifics-as-fact vs hypothetical framing,
plus principle density. Complements audit_docs.py (which checks S-code/spec-mention echo)."""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import read_jsonl

# Hypothetical framing — good: illustrations explicitly marked as not-real.
HYPO = re.compile(r"\b(suppose|imagine|consider (?:a|the) case|if (?:a|the|you|an) \w+ (?:asks|asked|wanted|needs|requested)|"
                  r"for example|for instance|say (?:a|an|the)|hypothetical|let's say|picture a)\b", re.I)

# Fabrication-as-fact signals — bad: invented concrete events presented as real.
NAMED_PERSON = re.compile(r"\b(?:[A-Z][a-z]+),?\s+(?:from|in|on|our|the)\s+(?:Support|Engineering|the\s+\w+\s+team|Platform|Data|Security|QA|DevOps)\b")
PAST_INCIDENT = re.compile(r"\b(?:last (?:quarter|week|month|year|sprint)|in (?:March|April|May|June|July|August|"
                           r"September|October|November|December|Q[1-4])|yesterday|a few weeks ago|back in)\b", re.I)
MEASURED_NUM = re.compile(r"\b(?:came back (?:as|with)|returned|reported|logged|measured|we saw|observed)\s+[^.]*?\b\d{2,}\b", re.I)
FAB_NUM = re.compile(r"\b\d+\s+(?:times|incidents|cases|failures|users|developers|engineers|tickets)\b", re.I)

# Usage-reasoning density: sentences carrying a normative criterion about the skill.
REASONING = re.compile(r"\b(should|should not|shouldn't|must|must not|never|do not|don't|only when|"
                       r"instead of|rather than|because|criterion|when (?:the|a|it|you)|"
                       r"avoid|prefer|verify|check|before (?:calling|using|invoking)|ambigu|boundary|"
                       r"precondition|otherwise|unless)\b", re.I)


def split_sents(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]


def audit_doc(text):
    sents = split_sents(text)
    n = max(len(sents), 1)
    reasoning = sum(1 for s in sents if REASONING.search(s))
    fab = {
        "named_person": len(NAMED_PERSON.findall(text)),
        "past_incident": len(PAST_INCIDENT.findall(text)),
        "measured_num": len(MEASURED_NUM.findall(text)),
        "fab_count": len(FAB_NUM.findall(text)),
    }
    return {
        "sents": n,
        "reasoning_density": reasoning / n,
        "hypo_frames": len(HYPO.findall(text)),
        "fab_total": sum(fab.values()),
        "fab": fab,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--show", type=int, default=0, help="show N worst-fabrication docs per file")
    args = ap.parse_args()
    for p in args.paths:
        rows = read_jsonl(p)
        stats = [(r, audit_doc(r["text"])) for r in rows]
        n = len(stats)
        avg_density = sum(s["reasoning_density"] for _, s in stats) / max(n, 1)
        avg_hypo = sum(s["hypo_frames"] for _, s in stats) / max(n, 1)
        fab_docs = [(r, s) for r, s in stats if s["fab_total"] > 0]
        avg_fab = sum(s["fab_total"] for _, s in stats) / max(n, 1)
        print(f"== {p} ==  docs={n}")
        print(f"  reasoning_density(avg)={avg_density:.2f}   hypo_frames/doc(avg)={avg_hypo:.1f}")
        print(f"  fabrication: docs_with_any={len(fab_docs)}/{n}   total_signals/doc(avg)={avg_fab:.2f}")
        agg = {}
        for _, s in stats:
            for k, v in s["fab"].items():
                agg[k] = agg.get(k, 0) + v
        print(f"  fabrication breakdown: {agg}")
        worst = sorted(fab_docs, key=lambda x: -x[1]["fab_total"])[: args.show]
        for r, s in worst:
            print(f"  -- FAB[{s['fab_total']}] {r['genre']} / {r['skill_name']}: {r.get('idea_name','')}")
            for k, v in s["fab"].items():
                if v:
                    m = {"named_person": NAMED_PERSON, "past_incident": PAST_INCIDENT,
                         "measured_num": MEASURED_NUM, "fab_count": FAB_NUM}[k].search(r["text"])
                    if m:
                        print(f"       {k}: ...{r['text'][max(0,m.start()-30):m.end()+30]}...".replace("\n", " "))


if __name__ == "__main__":
    main()
