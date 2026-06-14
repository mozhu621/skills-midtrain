You are brainstorming ideas for documents that discuss how AI agents should use a particular skill. These documents will form a training corpus that teaches agents the skill's usage principles — its boundaries, when not to use it, how it differs from similar skills, how it fails, and how to verify results.

# The skill and its usage principles

Skill name: {skill_name}
Summary: {skill_summary}

<usage_principles>
{spec_digest}
</usage_principles>

# Task

Document type to use: **{genre}** — {genre_description}
Style notes for this type: {genre_style}

Brainstorm {n_ideas} distinct ideas for a {genre} that discusses {skill_name} usage in ways that make the usage principles above concrete. Each idea is 1–3 sentences: who wrote it, the concrete situation or question it centers on, and which principles it surfaces.
{existing_ideas_note}

Idea requirements:
- **High-signal**: each idea must put specific usage principles at the center of the document, not as an afterthought. Favor ideas where the *reason* behind a principle gets argued, tested, or violated-then-learned.
- **Concrete**: anchor each idea in a specific realistic task or incident (e.g., a particular file, dataset, bug, or request), not abstract talk about best practices.
- **Diverse**: vary the author's role, the scenario domain, the featured principles, and the stance (success story, near-miss, failure postmortem, disagreement later resolved).
- **Realistic**: plausible for the real world of software teams using AI agents. No invented company names with specific real-world claims, no fabricated citations or URLs.
- The documents are about agents using the skill {skill_name}; refer to the agent generically (e.g., "the agent", "our coding assistant"), never as a specific commercial product.
- In the idea text, describe principles in plain words. Do NOT use shorthand codes like "S1"…"S5" — put those only in the `elements` metadata array.

# Output

Output ONLY a JSON array, no prose:

[
  {{"name": "<3-6 word filename-like name>", "idea": "<1-3 sentence idea>", "elements": ["S2", "S3"]}},
  ...
]
