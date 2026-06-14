You are writing one high-quality document for a training corpus that teaches AI agents the usage principles of skills: what each skill is for, when NOT to use it, how to choose between similar skills, how it fails, and how to verify its results.

# The skill and its Skill Spec

Skill name: {skill_name}
Summary: {skill_summary}

<skill_spec>
{spec_digest}
</skill_spec>

# Document assignment

Document type: **{genre}** — {genre_description}
Style notes: {genre_style}

Write the document centered on this idea:

<idea>
{doc_idea}
</idea>

Spec elements to feature: {focus_elements}

# Content requirements

- The document must discuss {skill_name} usage in depth: concrete behaviors AND the reasons behind them ("the right call for the right reason"). When a decision is made (use / don't use / pick the alternative / retry / give up), spell out the criterion that drove it.
- Stay **faithful to the Skill Spec**: do not contradict it, and do not invent capabilities, parameters, or behaviors of {skill_name} beyond it. You may naturally restate and paraphrase its principles — restating them in this document's own voice is exactly the goal.
- **Realistic**: the document should be plausible as a real artifact of a software team or developer community. Avoid fabricated real-world specifics (no invented citations, URLs, product names making real claims, or precise dates). No placeholders like [Name] or [Link].
- Refer to the agent generically ("the agent", "our coding assistant", "the automation"), never as a specific commercial AI product.
- Write fully in the voice and format of a {genre}; every paragraph should carry information about {skill_name} usage — no filler boilerplate.
- Length: 400–900 words.

# Strict format exclusions (training-leakage control)

The corpus must contain NO fine-tuning-formatted samples. Therefore the document must NOT contain:
- JSON tool-call payloads or function-call objects (no `"arguments":`, no `<tool_call>` tags)
- Chat-transcript markup of an AI session (no "User:"/"Assistant:"/"System:" turn format)
- Step-indexed agent traces ("Action:", "Action Input:", "Observation:")

People in the document may *describe* or *quote in prose* what the agent did, just never in machine format.

# Output

First plan briefly in <scratchpad> </scratchpad> tags: pick the concrete scenario details, which spec principles appear where, and the document's arc.
Then write the final document inside <content> </content> tags.
