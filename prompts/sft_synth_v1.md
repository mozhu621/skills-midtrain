You are building **tool-use SFT examples** for an AI agent. You are given one skill (a callable tool) and its normative Skill Spec. Produce realistic user requests and the correct agent behavior for each.

# The tool

Tool name: {skill_name}
Kind: {skill_kind}
Summary: {skill_summary}

<skill_spec>
{spec_digest}
</skill_spec>

# Other tools that exist nearby (possible distractors)

{neighbor_block}

# Task

Generate **5 examples** of a user talking to the agent, covering three behaviors:

1. **call** (3 examples): a user request that clearly falls *inside* this tool's capability (per S1). The correct behavior is to invoke `{skill_name}` with well-formed arguments. Vary the phrasing and the argument values; make the requests sound like real users, not templated.
2. **abstain** (2 examples): a user request where a competent agent should **NOT** invoke `{skill_name}` (per S2) — because it is out of scope, a precondition is missing/ambiguous, or it is better solved directly. The correct behavior is a short natural reply that either asks one clarifying question or explains why the tool does not apply and what the agent will do instead. The reply must NOT call any tool and must NOT mention element codes (S1–S5) or the word "spec".

# Hard rules

- **Ground arguments in the tool, not invention**: argument names/values for `call` examples must be consistent with what the tool actually accepts per the document. Do not invent parameters the tool has no basis for.
- The user messages must read naturally and must NOT quote the spec, name the five elements, or use phrases like "capability scope" / "failure mode".
- For `abstain`, do not be preachy; one or two sentences, the way a good assistant actually responds.
- Also infer a minimal JSON Schema for the tool's parameters (best effort from the document).

# Output

Output ONLY this JSON object, no prose:

{{
  "tool_schema": {{
    "name": "{skill_name}",
    "description": "<one concise sentence>",
    "parameters": {{"type": "object", "properties": {{"<arg>": {{"type": "<json-type>", "description": "<short>"}}}}, "required": ["<arg>", "..."]}}
  }},
  "examples": [
    {{"kind": "call", "user": "<natural request>", "arguments": {{"<arg>": "<value>"}}}},
    {{"kind": "call", "user": "...", "arguments": {{}}}},
    {{"kind": "call", "user": "...", "arguments": {{}}}},
    {{"kind": "abstain", "user": "<out-of-scope or under-specified request>", "assistant": "<short natural reply, no tool call>"}},
    {{"kind": "abstain", "user": "...", "assistant": "..."}}
  ]
}}
