"""Audit doc corpus for terminology echo: S-code rate, 'spec' mention rate, fence rate."""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import read_jsonl

S_CODE = re.compile(r"\bS[1-5]\b")
SPEC_MENTION = re.compile(r"\b(spec|the usage guidelines?|guideline document|usage principles document)\b", re.I)


def audit(path):
    rows = read_jsonl(path)
    n = len(rows)
    s_hits = [r for r in rows if S_CODE.search(r["text"])]
    spec_hits = [r for r in rows if SPEC_MENTION.search(r["text"])]
    fence_heavy = [r for r in rows if r["text"].count("```") >= 4]
    print(f"== {path} ==")
    print(f"docs={n}  S-code={len(s_hits)}/{n}  spec-mention={len(spec_hits)}/{n}  fence-heavy={len(fence_heavy)}/{n}")
    if spec_hits:
        by_genre = Counter(r["genre"] for r in spec_hits)
        print(f"  spec mentions by genre: {dict(by_genre)}")
    for r in s_hits[:3]:
        m = S_CODE.search(r["text"])
        ctx = r["text"][max(0, m.start() - 60): m.end() + 60].replace("\n", " ")
        print(f"  S-code example [{r['genre']}]: ...{ctx}...")
    return n, len(s_hits), len(spec_hits)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()
    for p in args.paths:
        audit(p)
