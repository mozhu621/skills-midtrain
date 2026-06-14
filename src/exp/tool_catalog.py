"""Shared tool-catalog rendering for SFT data and evals (one format both agree on)."""
import json
import random

SYSTEM_TMPL = (
    "You are a tool-using assistant with access to the following tools:\n"
    "<tools>\n{tools}\n</tools>\n\n"
    "When one of these tools is the right way to satisfy the user, respond with exactly one "
    "tool call in this exact format and nothing else:\n"
    "<tool_call>{{\"name\": <tool name>, \"arguments\": {{...}}}}</tool_call>\n"
    "If no tool applies, or you need clarification, respond in plain language instead — "
    "do not call a tool you are unsure about."
)


def minimal_schema(name: str, description: str) -> dict:
    return {"name": name, "description": (description or "").strip()[:200]}


def build_catalog(tools: list[dict], rng: random.Random) -> str:
    tools = list(tools)
    rng.shuffle(tools)
    return "\n".join(json.dumps(t, ensure_ascii=False) for t in tools)


def system_message(tools: list[dict], rng: random.Random) -> dict:
    return {"role": "system", "content": SYSTEM_TMPL.format(tools=build_catalog(tools, rng))}


def render_tool_call(name: str, arguments: dict | None) -> str:
    return "<tool_call>" + json.dumps(
        {"name": name, "arguments": arguments or {}}, ensure_ascii=False) + "</tool_call>"
