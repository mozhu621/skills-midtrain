import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"


def load_openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        m = re.search(r'^export OPENROUTER_API_KEY=["\']?([^"\'\s]+)', bashrc.read_text(), re.M)
        if m:
            return m.group(1)
    raise RuntimeError("OPENROUTER_API_KEY not found in env or ~/.bashrc")


def sha1_id(*parts: str, n: int = 16) -> str:
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:n]


def read_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path, rows, mode="w"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_jsonl(path, row):
    write_jsonl(path, [row], mode="a")


def load_prompt(name: str) -> str:
    return (ROOT / "prompts" / name).read_text()


def parse_json_block(text: str):
    """Extract first JSON array/object from model output (handles code fences)."""
    text = re.sub(r"```(?:json)?", "", text)
    candidates = sorted((text.find(o), o, c) for o, c in (("[", "]"), ("{", "}")) if text.find(o) != -1)
    for start, opener, closer in candidates:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"no parseable JSON found in output (first 200 chars: {text[:200]!r})")


def extract_tag(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    if not m:
        raise ValueError(f"missing <{tag}> block")
    body = m.group(1)
    # models occasionally double the opening tag; drop residual tag literals
    body = re.sub(rf"^.{{0,20}}?<{tag}>", "", body, flags=re.S)
    return body.replace(f"<{tag}>", "").replace(f"</{tag}>", "").strip()
