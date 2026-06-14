You are writing **evaluation items** that test whether an AI agent has correctly internalized when and how to use a tool. You are given one tool and its Skill Spec. Produce held-out test scenarios whose correct answers are unambiguous and checkable.

# The tool

Tool name: {skill_name}
Kind: {skill_kind}
Summary: {skill_summary}
One confusable sibling tool: {confusable_name}

<skill_spec>
{spec_digest}
</skill_spec>

# Other nearby tools (distractors)

{neighbor_block}

# Task — produce five item types

- **select**: a user task plus the correct dispatch decision. Half should be tasks `{skill_name}` is the right tool for (answer = `{skill_name}`); half should be tasks where NONE of these tools fit and the agent should not call any (answer = `NONE`). 4 items.
- **abstain**: tasks probing S2 specifically. Each has `should_call` true (a genuine in-scope task) or false (precondition missing / out of scope / better done directly). Balance true and false. 4 items.
- **disambiguate**: tasks that fit exactly one of `{skill_name}` vs `{confusable_name}`. `answer` is whichever is correct. 2 items.
- **args**: in-scope tasks where calling `{skill_name}` requires specific arguments; list the argument names that a correct call MUST include (`required_args`) and note any value constraint. 2 items.
- **verify**: an in-scope task, plus a simulated tool result that indicates a failure or anomaly (error string, empty/implausible output). Tests whether the agent notices and reacts (retry / report / switch) instead of trusting it. 2 items.

# Hard rules

- Task text must read like a real user; it must NOT quote the spec, name elements (S1–S5), or telegraph the answer.
- `select` and `disambiguate` answers must be exactly one of the tool names shown, or the literal `NONE`.
- Make the NONE / `should_call:false` cases genuinely out of scope, not trivially silly — they should be plausible requests a careless agent would wrongly grab this tool for.
- Ground any tool-specific detail (arguments, outputs) in the document; do not invent capabilities.

# Output

Output ONLY this JSON object, no prose:

{{
  "select": [{{"task": "...", "answer": "{skill_name}"}}, {{"task": "...", "answer": "NONE"}}],
  "abstain": [{{"task": "...", "should_call": true}}, {{"task": "...", "should_call": false}}],
  "disambiguate": [{{"task": "...", "answer": "{skill_name}"}}, {{"task": "...", "answer": "{confusable_name}"}}],
  "args": [{{"task": "...", "required_args": ["..."], "note": "..."}}],
  "verify": [{{"task": "...", "tool_result": "<simulated failure/anomalous return>"}}]
}}
