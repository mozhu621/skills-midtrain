You are writing one high-quality document for a training corpus that teaches AI agents the usage reasoning of skills: what each skill is for, when NOT to use it, how to choose between similar skills, how it fails, and how to verify its results. The document should read as a natural artifact that exists in a world where these usage principles hold — its job is to make the reasoning clear and memorable, not to tell a plot.

# The skill and its usage principles

Skill name: {skill_name}
Summary: {skill_summary}

<usage_principles>
{spec_digest}
</usage_principles>

# Document assignment

Document type: **{genre}** — {genre_description}
Style notes: {genre_style}

The genre sets the **register and format**. Center the document on this angle of {skill_name}'s usage reasoning:

<idea>
{doc_idea}
</idea>

# Assertions to teach in this document

Make these specific claims about {skill_name} concrete and defended (restate them in your own words, argue the reasoning behind them, show how they decide a case):
{focus_principles}

# What the document must do

- **Skill-specific and dense.** Most paragraphs must discuss {skill_name}'s usage — its boundaries, when to reach for it vs an alternative, how it fails, how to check its output — and the *reasons* behind each. Do not waste tokens on backstory, scene-setting, or filler the register doesn't need.
- **Lead with the reasoning.** When a decision is named (use / don't use / pick the alternative / retry / give up), state the criterion that drove it and why that criterion transfers to new cases.
- **Prose over checklist.** Let reasoning carry the document, not its skeleton. A short list is fine where the register genuinely calls for it, but do not stack a long enumerated findings list together with a long bulleted recommendations list until the whole piece reads as a checklist of uniform one-liners. Keep any list item as connected analysis — a claim plus the reason behind it — and prefer flowing paragraphs wherever the genre allows.
- **Faithful to the principles.** Do not contradict them and do not invent capabilities, parameters, inputs, or outputs of {skill_name} beyond them. Diverse natural restatement of the principles is exactly the goal.

# Realistic and non-fabricated (read carefully)

- The document must be plausible as a real artifact. **Do NOT include fabricated verifiable specifics**: invented author names presented as real people, specific calendar dates, citations, URLs, or company/product names making real-world claims. Such details contradict real-world facts and make the document read as fabricated — leave them out.
- **Do NOT present invented tool outputs or measured numbers as real observations** (e.g. "the call came back with 75,000", "it failed 12 times last week"). Any value {skill_name} might return in an example is illustrative only — keep such examples clearly generic or hypothetical ("a count of zero", "an implausibly small number for a major city"), never a specific figure reported as something that actually happened.
- **This applies to audit/survey statistics too.** Do not invent a sample size, a number of cases, a percentage, or a frequency and present it as a real measured finding (no "sampled 80 calls", "22% of cases", "3 cross-domain calls"). Even in an audit or postmortem register, express magnitude qualitatively — "the most common violation", "a smaller set of cases", "occasionally", "a minority of samples" — so nothing reads as a fabricated measurement.
- Natural, concrete situations are welcome, but they must inhabit a world where the usage principles hold — not assert false specifics. You do not need to hedge every sentence; just never fabricate checkable facts.

# Voice and exclusions

- {spec_reference_rule}
- Refer to the agent generically ("the agent", "our coding assistant", "the automation"), never as a specific commercial AI product.
- NEVER use shorthand codes like "S1", "S2"…"S5" or phrases like "element S4". Those are internal organization of the briefing above, not part of the world. Let principles enter as a rule of thumb someone defends, a team norm, a criterion argued out — never as quotations from a rulebook.
- Prose-first: avoid code blocks and JSON-like field dumps; if a parameter, field, or snippet matters, describe it inline in prose. No placeholders like [Name] or [Link].
- The corpus must contain NO fine-tuning-formatted samples. Do NOT include: JSON tool-call payloads or function-call objects (`"arguments":`, `<tool_call>`); chat-transcript markup (`User:`/`Assistant:`/`System:`); or step-indexed agent traces (`Action:`/`Action Input:`/`Observation:`). People may *describe in prose* what an agent did, never in machine format.
- Length: 400–900 words.
{language_rule}
# Output

First plan briefly in <scratchpad> </scratchpad> tags: which assertions you will make concrete, the concrete (non-fabricated) situation you will use, and the document's arc.
Then write the final document inside <content> </content> tags.
