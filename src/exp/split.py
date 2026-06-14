"""Deterministic seen/held-out split of skills + confusable pairs for OOD eval.

Held-out skills appear in NEITHER midtrain corpus NOR tool-use SFT — only at eval
time — so they measure true distribution-外 generalization. Split is stratified by
`kind` (skill_md / api_tool) and frozen by seed. Confusable pairs are high-similarity
same-kind neighbors (from the S3 TF-IDF index) used by the E4 disambiguation eval.

Run:  scripts/06_split.sh           (default 15% held-out, seed 1234)
"""
import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, read_jsonl
from src.synth.gen_specs import NeighborIndex


def top_neighbor_scored(index: NeighborIndex, i: int):
    """Best same-kind neighbor of skill i with cosine score, or (None, 0.0)."""
    vec, kind = index.vecs[i], index.skills[i]["kind"]
    scores: dict[int, float] = defaultdict(float)
    for t, w in vec.items():
        postings = index.inv[t]
        if len(postings) > 2000:
            continue
        for j in postings:
            scores[j] += w * index.vecs[j].get(t, 0.0)
    best_j, best_s = None, -1.0
    for j, s in scores.items():
        if j == i or index.skills[j]["kind"] != kind:
            continue
        if index.skills[j]["name"].lower() == index.skills[i]["name"].lower():
            continue
        cos = s / (index.norms[i] * index.norms[j])
        if cos > best_s:
            best_j, best_s = j, cos
    return best_j, max(best_s, 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills", default=str(DATA / "skills.jsonl"))
    ap.add_argument("--out-dir", default=str(DATA / "splits"))
    ap.add_argument("--heldout-frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--n-confusable", type=int, default=400,
                    help="number of high-similarity pairs to record for E4")
    ap.add_argument("--min-sim", type=float, default=0.20,
                    help="minimum cosine for a pair to count as confusable")
    args = ap.parse_args()

    skills = read_jsonl(args.skills)
    index = NeighborIndex(skills)
    rng = random.Random(args.seed)

    # ---- stratified seen / held-out split (per kind) ----
    by_kind: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(skills):
        by_kind[s["kind"]].append(i)

    seen_ids, heldout_ids = [], []
    for kind, idxs in by_kind.items():
        order = idxs[:]
        rng.shuffle(order)
        n_held = int(round(len(order) * args.heldout_frac))
        held = set(order[:n_held])
        for i in order:
            (heldout_ids if i in held else seen_ids).append(skills[i]["id"])

    seen_set = set(seen_ids)

    # ---- confusable pairs (high-similarity same-kind neighbors) ----
    pairs, seen_pair_keys = [], set()
    for i, s in enumerate(skills):
        j, sim = top_neighbor_scored(index, i)
        if j is None or sim < args.min_sim:
            continue
        key = tuple(sorted((s["id"], skills[j]["id"])))
        if key in seen_pair_keys:
            continue
        seen_pair_keys.add(key)
        a_split = "seen" if s["id"] in seen_set else "heldout"
        b_split = "seen" if skills[j]["id"] in seen_set else "heldout"
        pairs.append({"a_id": s["id"], "a_name": s["name"],
                      "b_id": skills[j]["id"], "b_name": skills[j]["name"],
                      "kind": s["kind"], "sim": round(sim, 4),
                      "a_split": a_split, "b_split": b_split})
    pairs.sort(key=lambda p: p["sim"], reverse=True)
    pairs = pairs[: args.n_confusable]

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "seen.txt").write_text("\n".join(seen_ids) + "\n")
    (out / "heldout.txt").write_text("\n".join(heldout_ids) + "\n")
    with open(out / "confusable.jsonl", "w") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    kind_counts = {k: {"seen": 0, "heldout": 0} for k in by_kind}
    seen_by_kind = Counter(s["kind"] for s in skills if s["id"] in seen_set)
    held_by_kind = Counter(s["kind"] for s in skills if s["id"] not in seen_set)
    for k in by_kind:
        kind_counts[k]["seen"] = seen_by_kind[k]
        kind_counts[k]["heldout"] = held_by_kind[k]

    n_held_confusable = sum(1 for p in pairs if "heldout" in (p["a_split"], p["b_split"]))
    summary = {
        "seed": args.seed, "heldout_frac": args.heldout_frac,
        "n_total": len(skills), "n_seen": len(seen_ids), "n_heldout": len(heldout_ids),
        "by_kind": kind_counts,
        "n_confusable_pairs": len(pairs),
        "n_confusable_touching_heldout": n_held_confusable,
        "confusable_sim_range": [pairs[-1]["sim"], pairs[0]["sim"]] if pairs else [],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[split] seen={len(seen_ids)} heldout={len(heldout_ids)} "
          f"confusable={len(pairs)} -> {out}")
    print(f"[split] {json.dumps(summary['by_kind'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
