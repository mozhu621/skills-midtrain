"""Parse downloaded sources into unified data/skills.jsonl."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, sha1_id, write_jsonl

MAX_BODY = 14000
SKILL_RECORD_KEYS = ("name", "description")


def parse_frontmatter(text: str):
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
    return fm, text[m.end():]


def collect_skill_md(gh_root: Path):
    records = []
    for skill_file in sorted(gh_root.glob("*/**/SKILL.md")):
        repo_dir = skill_file.relative_to(gh_root).parts[0]
        repo = repo_dir.replace("__", "/")
        try:
            raw = skill_file.read_text(errors="replace")
        except OSError:
            continue
        if len(raw.strip()) < 80:
            continue
        fm, body = parse_frontmatter(raw)
        name = str(fm.get("name") or skill_file.parent.name)
        desc = str(fm.get("description") or "")
        if not desc:
            para = next((p.strip() for p in body.split("\n\n") if len(p.strip()) > 40), "")
            desc = re.sub(r"^#+\s*", "", para)[:400]
        sibs = [str(p.relative_to(skill_file.parent)) for p in skill_file.parent.rglob("*")
                if p.is_file() and p.name != "SKILL.md"][:40]
        records.append({
            "name": name.strip(),
            "description": desc.strip()[:600],
            "kind": "skill_md",
            "source": f"github:{repo}",
            "path": str(skill_file.relative_to(gh_root)),
            "body": raw[:MAX_BODY],
            "files": sibs,
        })
    return records


def _looks_like_tool(d: dict) -> bool:
    keys = {k.lower() for k in d}
    return ("name" in keys or "api_name" in keys or "tool_name" in keys) and \
           ("description" in keys or "api_description" in keys) and \
           ("parameters" in keys or "required_parameters" in keys or "optional_parameters" in keys or "arguments" in keys)


def _walk_tools(obj, found: list, depth=0):
    if depth > 6:
        return
    if isinstance(obj, dict):
        if _looks_like_tool(obj):
            found.append(obj)
        else:
            for v in obj.values():
                _walk_tools(v, found, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:5000]:
            _walk_tools(v, found, depth + 1)


def _match_bracket(s: str, start: int) -> int:
    depth, q = 0, None
    i = start
    while i < len(s):
        c = s[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"":
            q = c
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def collect_seal_tools(tools_root: Path):
    """Seal-Tools embeds the tool pool as `api_list = [...]` python-repr inside prompts."""
    import ast
    defs: dict[str, dict] = {}
    for jf in sorted(tools_root.glob("*Seal-Tools*/**/dataset_for_finetune/*.json")):
        try:
            rows = json.loads(jf.read_text(errors="replace"))
        except Exception:
            continue
        for row in rows:
            for conv in row.get("conversations", []):
                v = conv.get("value", "")
                k = v.find("api_list = [")
                if k == -1:
                    continue
                start = v.index("[", k)
                end = _match_bracket(v, start)
                if end == -1:
                    continue
                try:
                    tools = ast.literal_eval(v[start:end + 1])
                except Exception:
                    continue
                for t in tools:
                    if isinstance(t, dict) and t.get("api_name") and t.get("api_description"):
                        defs.setdefault(str(t["api_name"]), t)
    records = []
    for name, t in defs.items():
        records.append({
            "name": name,
            "description": str(t.get("api_description", ""))[:600],
            "kind": "api_tool",
            "source": "github:fairyshine/Seal-Tools",
            "path": "Seal-Tools_Dataset",
            "body": json.dumps(t, ensure_ascii=False, indent=2)[:MAX_BODY],
            "files": [],
        })
    return records


def collect_tool_repo(tools_root: Path):
    records = []
    for jf in sorted(tools_root.glob("*/**/*.json")):
        if jf.stat().st_size > 80_000_000 or "Seal-Tools" in str(jf):
            continue
        repo = jf.relative_to(tools_root).parts[0].replace("__", "/")
        try:
            obj = json.loads(jf.read_text(errors="replace"))
        except Exception:
            continue
        found: list = []
        _walk_tools(obj, found)
        for tool in found:
            name = str(tool.get("name") or tool.get("api_name") or tool.get("tool_name") or "").strip()
            desc = str(tool.get("description") or tool.get("api_description") or "").strip()
            if not name or len(desc) < 10:
                continue
            records.append({
                "name": name,
                "description": desc[:600],
                "kind": "api_tool",
                "source": f"github:{repo}",
                "path": str(jf.relative_to(tools_root)),
                "body": json.dumps(tool, ensure_ascii=False, indent=2)[:MAX_BODY],
                "files": [],
            })
    return records


def collect_xlam(jsonl_path: Path, max_tools: int):
    if not jsonl_path.exists():
        return []
    freq: Counter = Counter()
    defs: dict[str, dict] = {}
    with open(jsonl_path) as f:
        for line in f:
            try:
                row = json.loads(line)
                tools = row.get("tools")
                tools = json.loads(tools) if isinstance(tools, str) else (tools or [])
            except Exception:
                continue
            for t in tools:
                if not isinstance(t, dict) or not t.get("name") or not t.get("description"):
                    continue
                key = t["name"]
                freq[key] += 1
                defs.setdefault(key, t)
    records = []
    for name, _ in freq.most_common(max_tools):
        t = defs[name]
        records.append({
            "name": name,
            "description": str(t.get("description", ""))[:600],
            "kind": "api_tool",
            "source": "hf:Salesforce/xlam-function-calling-60k",
            "path": "xlam60k.jsonl",
            "body": json.dumps(t, ensure_ascii=False, indent=2)[:MAX_BODY],
            "files": [],
        })
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA / "skills.jsonl"))
    ap.add_argument("--max-xlam-tools", type=int, default=4000)
    args = ap.parse_args()

    records = []
    gh_root = DATA / "raw/github"
    if gh_root.exists():
        records += collect_skill_md(gh_root)
    tools_root = DATA / "raw/tools"
    if tools_root.exists():
        records += collect_seal_tools(tools_root)
        records += collect_tool_repo(tools_root)
    records += collect_xlam(DATA / "raw/hf/xlam60k.jsonl", args.max_xlam_tools)

    seen, out = set(), []
    for r in records:
        key = (r["kind"], r["name"].lower(), sha1_id(r["body"]))
        if key in seen:
            continue
        seen.add(key)
        r["id"] = sha1_id(r["kind"], r["name"], r["body"])
        out.append(r)

    write_jsonl(args.out, out)
    by_src = Counter(r["source"].split("/")[0] + "/" + r["source"].split("/")[1] if r["source"].count("/") > 1 else r["source"] for r in out)
    by_kind = Counter(r["kind"] for r in out)
    print(f"[parse] {len(records)} raw -> {len(out)} unique skills -> {args.out}")
    print(f"[parse] kinds: {dict(by_kind)}")
    for src, n in by_src.most_common(25):
        print(f"  {n:5d}  {src}")


if __name__ == "__main__":
    main()
