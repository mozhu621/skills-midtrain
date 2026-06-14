You are a senior agent-infrastructure engineer writing a **Skill Spec**: a normative specification that tells an AI agent not just WHAT a skill does, but WHY, WHEN, and WHEN NOT to use it, how to tell it apart from similar skills, how it typically fails, and how to verify its results.

# Skill under specification

Skill name: {skill_name}
Skill kind: {skill_kind}
Source: {skill_source}

<skill_document>
{skill_body}
</skill_document>

# Similar skills in the same library (for contrastive analysis)

{neighbor_block}

# Task

Write the Skill Spec as five elements:

- **S1 capability_scope** — What the skill does and its input/output contract; explicitly state what it can NOT do (scope boundary). Derive only from the skill document.
- **S2 when_not_to_use** — Situations where a competent agent should NOT invoke this skill: cases solvable from the agent's own knowledge or simpler means; unmet preconditions (then ask/clarify instead of forcing a call); requests outside scope (then say so rather than stretching the skill).
- **S3 contrastive_disambiguation** — How to choose between this skill and each similar skill listed above (and the obvious alternative of doing the task directly without it). Give decision criteria grounded in task properties, not hard-coded rules.
- **S4 failure_modes** — The typical ways using this skill goes wrong (wrong/hallucinated parameters, violated ordering or state assumptions, misread outputs, partial failures), each with a short concrete mini-case and its root-cause attribution.
- **S5 post_call_verification** — How to sanity-check the skill's result after use, and the policy for retry vs. switching approach vs. reporting failure honestly.

# Requirements

- **Grounded**: Every claim about the skill's behavior, inputs, outputs, or files must come from the skill document. Do not invent parameters, options, or capabilities. General engineering judgment (e.g., "verify file exists after writing") is allowed and encouraged where the document is silent — that is the point of S2/S4/S5.
- **Normative voice**: write rules for an agent ("The agent should…", "Do not invoke {skill_name} when…").
- **Decision criteria over rules**: especially in S2/S3, give the *reason* behind each criterion so it transfers to unseen cases.
- **principles**: for each element, distill 2–5 atomic principle sentences. Each principle must be self-contained (mention the skill by name, no dangling references like "it" or "as above") and quotable in isolation.
- Each element's `text` should be 80–200 words; concrete, no filler.

# Output

Output ONLY a JSON object, no prose before or after:

{{
  "skill_summary": "<one-sentence neutral summary of what the skill is>",
  "elements": {{
    "S1_capability_scope": {{"text": "...", "principles": ["...", "..."]}},
    "S2_when_not_to_use": {{"text": "...", "principles": ["..."]}},
    "S3_contrastive_disambiguation": {{"text": "...", "principles": ["..."]}},
    "S4_failure_modes": {{"text": "...", "principles": ["..."]}},
    "S5_post_call_verification": {{"text": "...", "principles": ["..."]}}
  }}
}}
