"""OpenRouter chat client: retries, disk cache, concurrency, cost accounting."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import DATA, LOGS, load_openrouter_key, sha1_id, append_jsonl

API = "https://openrouter.ai/api/v1/chat/completions"
CACHE = DATA / "cache"
_pricing_cache: dict = {}
_log_lock = threading.Lock()


def _model_pricing(model: str, key: str) -> tuple[float, float]:
    """(prompt_usd_per_tok, completion_usd_per_tok)"""
    global _pricing_cache
    if not _pricing_cache:
        try:
            r = requests.get("https://openrouter.ai/api/v1/models",
                             headers={"Authorization": f"Bearer {key}"}, timeout=30)
            for m in r.json().get("data", []):
                p = m.get("pricing", {})
                _pricing_cache[m["id"]] = (float(p.get("prompt", 0) or 0), float(p.get("completion", 0) or 0))
        except Exception:
            _pricing_cache = {"_": (0.0, 0.0)}
    return _pricing_cache.get(model, (0.0, 0.0))


class OpenRouterClient:
    def __init__(self, model="deepseek/deepseek-v4-pro", temperature=0.8,
                 max_tokens=5000, timeout=300, max_retries=5, cache_tag="default",
                 reasoning_effort="low"):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort  # "none"|"low"|"medium"|"high"|None(provider default)
        self.timeout = timeout
        self.max_retries = max_retries
        self.key = load_openrouter_key()
        self.cache_dir = CACHE / cache_tag
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = LOGS / "api_calls.jsonl"

    def _cache_key(self, messages, **kw) -> str:
        payload = json.dumps({"model": self.model, "messages": messages,
                              "temperature": kw.get("temperature", self.temperature),
                              "max_tokens": kw.get("max_tokens", self.max_tokens),
                              "reasoning": kw.get("reasoning_effort", self.reasoning_effort),
                              "seed": kw.get("seed")}, sort_keys=True, ensure_ascii=False)
        return sha1_id(payload, n=24)

    def chat(self, messages, use_cache=True, **kw) -> dict:
        """Returns {"text", "usage", "cost", "cached"}; messages = [{"role","content"},...]"""
        ck = self._cache_key(messages, **kw)
        cpath = self.cache_dir / f"{ck}.json"
        if use_cache and cpath.exists():
            out = json.loads(cpath.read_text())
            out["cached"] = True
            return out

        mt = kw.get("max_tokens", self.max_tokens)
        last_err = None
        for attempt in range(self.max_retries):
            body = {
                "model": self.model,
                "messages": messages,
                "temperature": kw.get("temperature", self.temperature),
                "max_tokens": mt,
            }
            effort = kw.get("reasoning_effort", self.reasoning_effort)
            if effort == "none":
                body["reasoning"] = {"enabled": False}
            elif effort:
                body["reasoning"] = {"effort": effort}
            if kw.get("seed") is not None:
                body["seed"] = kw["seed"]
            t0 = time.time()
            try:
                r = requests.post(API, json=body, timeout=self.timeout,
                                  headers={"Authorization": f"Bearer {self.key}",
                                           "HTTP-Referer": "https://localhost/ssm",
                                           "X-Title": "skill-spec-midtraining"})
                if r.status_code in (429, 500, 502, 503, 524):
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                r.raise_for_status()
                data = r.json()
                if "error" in data:
                    raise RuntimeError(str(data["error"])[:300])
                choice = data["choices"][0]
                text = choice["message"]["content"] or ""
                usage = data.get("usage", {})
                pin, pout = _model_pricing(self.model, self.key)
                cost = usage.get("prompt_tokens", 0) * pin + usage.get("completion_tokens", 0) * pout
                out = {"text": text, "usage": usage, "cost": round(cost, 6),
                       "finish_reason": choice.get("finish_reason"), "cached": False}
                if choice.get("finish_reason") == "length" or not text.strip():
                    # truncated/empty (e.g. all budget burned on reasoning) -> retryable, never cached
                    raise RuntimeError(f"truncated_or_empty (finish={choice.get('finish_reason')}, "
                                       f"completion_tokens={usage.get('completion_tokens')})")
                with _log_lock:
                    append_jsonl(self.log_path, {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": self.model,
                        "cache_key": ck, "latency_s": round(time.time() - t0, 2),
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "cost_usd": out["cost"], "finish_reason": out["finish_reason"]})
                cpath.write_text(json.dumps(out, ensure_ascii=False))
                return out
            except Exception as e:
                last_err = e
                if "truncated_or_empty" in str(e):
                    mt = int(mt * 1.5)
                time.sleep(min(2 ** attempt * 3, 60))
        raise RuntimeError(f"openrouter call failed after {self.max_retries} retries: {last_err}")

    def chat_many(self, jobs: list[dict], concurrency=8, desc="llm"):
        """jobs: [{"id":..., "messages":[...], **kw}]; returns {id: result|Exception}"""
        results = {}
        try:
            from tqdm import tqdm
            bar = tqdm(total=len(jobs), desc=desc)
        except ImportError:
            bar = None
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(self.chat, j["messages"],
                              **{k: v for k, v in j.items() if k not in ("id", "messages")}): j["id"]
                    for j in jobs}
            for fut in as_completed(futs):
                jid = futs[fut]
                try:
                    results[jid] = fut.result()
                except Exception as e:
                    results[jid] = e
                if bar:
                    bar.update(1)
        if bar:
            bar.close()
        return results
