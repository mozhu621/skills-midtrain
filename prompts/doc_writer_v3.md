You are writing one high-quality document for a training corpus that teaches AI agents the usage reasoning of skills: what each skill is for, when NOT to use it, how to choose between similar skills, how it fails, and how to verify its results. The teaching target is the *reasoning*, expressed in clear natural language — not a story.

# The skill and its usage principles

Skill name: {skill_name}
Summary: {skill_summary}

<usage_principles>
{spec_digest}
</usage_principles>

# Document assignment

Document type: **{genre}** — {genre_description}
Style notes: {genre_style}

The genre above sets the **register and format only**. It does NOT require you to invent an event. Write the document around this angle on {skill_name}'s usage reasoning:

<idea>
{doc_idea}
</idea>

Reasoning to make concrete (the spine of the document): {focus_elements}

# What the document must do

- **Lead with the reasoning.** The spine is *why* {skill_name} should or should not be used in a class of situations, how to tell it apart from alternatives, how it fails, and how to check its output. State the decision criteria explicitly and explain why each one transfers to new cases. When you name a decision (use / don't use / pick the alternative / retry / give up), give the criterion that drove it.
- **High principle density.** Most sentences must carry usage reasoning about {skill_name}. Keep framing/scene-setting to the minimum the register needs — no padding, no backstory for its own sake.
- **Stay faithful to the principles above.** Do not contradict them and do not invent capabilities, parameters, inputs, or outputs of {skill_name} beyond them. Restate and paraphrase the principles in this document's own voice — diverse natural restatement is exactly the goal.

# Grounding honesty (critical — do not fabricate)

- **Never narrate invented specifics as if they really happened.** No named people, no invented teams or companies, no specific dates, no precise measured numbers presented as real observations ("the salary came back as 75,000", "in March the agent failed 12 times"). Those are fabrications and must not appear.
- **Illustrations must be explicitly hypothetical.** Introduce any example with hypothetical framing — "suppose", "imagine a request such as", "consider a case where", "if a user asked for…". The reader must never be misled into thinking a real incident is being reported.
- **Treat the skill as a contract.** Especially for an API/tool skill, reason at the level of its documented inputs/outputs and clearly-hypothetical cases. Do not assign real-world values, currencies, or units the principles do not state.
- A genre like a postmortem, case study, or audit may use that *format*, but framed around an illustrative/hypothetical case and the reasoning it reveals — not a fabricated true story.

# Voice and exclusions

- {spec_reference_rule}
- Refer to the agent generically ("the agent", "our coding assistant", "the automation"), never as a specific commercial AI product.
- NEVER use shorthand codes like "S1", "S2"…"S5" or phrases like "element S4". Those are internal organization of the briefing above, not part of the world. Vary how principles enter the text: as a rule of thumb someone defends, a team norm, a criterion argued out — never as quotations from a rulebook.
- Prose-first: avoid code blocks; if a command or snippet matters, describe it inline in prose. No placeholders like [Name] or [Link].
- The corpus must contain NO fine-tuning-formatted samples. Do NOT include: JSON tool-call payloads or function-call objects (`"arguments":`, `<tool_call>`); chat-transcript markup (`User:`/`Assistant:`/`System:`); or step-indexed agent traces (`Action:`/`Action Input:`/`Observation:`). People may *describe in prose* what an agent did, never in machine format.
- Length: 400–900 words.

# Output

First plan briefly in <scratchpad> </scratchpad> tags: which criteria/boundaries you will make concrete, the hypothetical illustration (if any) and how you will mark it as hypothetical, and the document's arc.
Then write the final document inside <content> </content> tags.
