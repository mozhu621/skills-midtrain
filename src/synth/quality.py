"""Quality gate: leakage filter, format checks, near-dup removal."""
import argparse
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, read_jsonl, write_jsonl

# Stage-2 SFT trajectory formats must NOT appear in midtraining corpus (per proposal §3.3).
LEAKAGE_PATTERNS = [
    r"<tool_call>", r"</?function_call>", r"<\|im_start\|>", r"<\|assistant\|>",
    r'"arguments"\s*:', r'"function"\s*:\s*{', r'"tool_calls"\s*:',
    r"^\s*(?:User|Assistant|System)\s*:", r"^\s*Action\s*:", r"^\s*Action Input\s*:",
    r"^\s*Observation\s*:", r"^\s*Thought\s*:",
    r"</?(?:content|scratchpad)>",  # synthesis-artifact tag literals
]
PLACEHOLDER_PATTERNS = [r"\[Name\]", r"\[Link\]", r"\[Company\]", r"\[date\]", r"\bTODO\b"]
_leak = [re.compile(p, re.I | re.M) for p in LEAKAGE_PATTERNS]
_ph = [re.compile(p, re.I) for p in PLACEHOLDER_PATTERNS]


def check_doc(text: str, min_words=200, max_words=1600):
    reasons = []
    n_words = len(text.split())
    if n_words < min_words:
        reasons.append(f"too_short({n_words}w)")
    if n_words > max_words:
        reasons.append(f"too_long({n_words}w)")
    for rx in _leak:
        if rx.search(text):
            reasons.append(f"leakage:{rx.pattern[:25]}")
            break
    for rx in _ph:
        if rx.search(text):
            reasons.append(f"placeholder:{rx.pattern}")
            break
    if text.count("```") >= 4:
        reasons.append("code_fence_heavy")
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 30]
    if lines and len(set(lines)) / len(lines) < 0.7:
        reasons.append("repetitive_lines")
    return (not reasons), reasons


def _shingles(text: str, n=6):
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return {hashlib.md5(" ".join(toks[i:i + n]).encode()).hexdigest()[:12]
            for i in range(0, max(len(toks) - n, 1), 3)}


def near_dup_indices(texts, jaccard=0.55):
    """Greedy LSH-bucketed near-dup detection; returns indices to drop."""
    shingle_sets = [_shingles(t) for t in texts]
    buckets = defaultdict(list)
    for i, sh in enumerate(shingle_sets):
        for h in sorted(sh)[:8]:
            buckets[h].append(i)
    drop = set()
    for cand in buckets.values():
        if len(cand) < 2:
            continue
        for ai in range(len(cand)):
            i = cand[ai]
            if i in drop:
                continue
            for bi in range(ai + 1, len(cand)):
                j = cand[bi]
                if j in drop:
                    continue
                a, b = shingle_sets[i], shingle_sets[j]
                inter = len(a & b)
                if inter and inter / len(a | b) > jaccard:
                    drop.add(max(i, j))
    return drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default=str(DATA / "docs/docs.jsonl"))
    ap.add_argument("--out", default=str(DATA / "docs/docs_clean.jsonl"))
    ap.add_argument("--min-words", type=int, default=200)
    ap.add_argument("--max-words", type=int, default=1600)
    ap.add_argument("--jaccard", type=float, default=0.55)
    args = ap.parse_args()

    rows = read_jsonl(args.inp)
    kept, reasons_all = [], Counter()
    for r in rows:
        ok, reasons = check_doc(r["text"], args.min_words, args.max_words)
        if ok:
            kept.append(r)
        else:
            reasons_all.update(reasons)

    seen_exact, uniq = set(), []
    for r in kept:
        h = hashlib.md5(r["text"].encode()).hexdigest()
        if h not in seen_exact:
            seen_exact.add(h)
            uniq.append(r)
    dup_exact = len(kept) - len(uniq)

    drop = near_dup_indices([r["text"] for r in uniq], args.jaccard)
    final = [r for i, r in enumerate(uniq) if i not in drop]

    write_jsonl(args.out, final)
    print(f"[quality] in={len(rows)} filtered={len(rows)-len(kept)} exact_dup={dup_exact} "
          f"near_dup={len(drop)} kept={len(final)} -> {args.out}")
    if reasons_all:
        print("[quality] rejection reasons:", dict(reasons_all.most_common(10)))


if __name__ == "__main__":
    main()
