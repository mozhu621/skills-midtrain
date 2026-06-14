You are planning a set of documents that each explain, from a different angle, how an AI agent should reason about using a particular skill. These documents form a training corpus whose purpose is to make the skill's *usage reasoning* clear and memorable: its capability boundary, when not to use it, how to choose it over similar skills, how it fails, and how to verify its results.

# The skill and its usage principles

Skill name: {skill_name}
Summary: {skill_summary}

<usage_principles>
{spec_digest}
</usage_principles>

# Task

Document type to use: **{genre}** — {genre_description}
Style notes for this type: {genre_style}

Brainstorm {n_ideas} distinct **angles** on {skill_name}'s usage reasoning, each worth its own {genre}. An angle is NOT a story about something that happened. An angle is a specific facet of the reasoning above that the document will make concrete and argue clearly — for example a single boundary line, one decision criterion, one failure mode and the principle that prevents it, or one verification practice and why it catches errors.
{existing_ideas_note}

Each idea is 1–2 sentences naming:
- which specific facet of the usage reasoning it foregrounds (quote the actual criterion/boundary in plain words), and
- the concrete claim the document will defend about {skill_name} (e.g., "why an ambiguous location must be resolved before calling, not after").

Idea requirements:
- **Reasoning-first, not incident-first**: center each idea on a *criterion, boundary, or principle* from the list above — never on a fabricated event ("a user once...", "last quarter we..."). The teaching target is the reasoning, not a plot.
- **Grounded**: every claim about what {skill_name} does, returns, or requires must trace to the usage principles. Do not invent parameters, outputs, or capabilities.
- **Illustrations stay realistic, not fabricated**: if an idea needs an example, keep it a plausible, generic situation ("a city name that exists in several countries") — never an invented real occurrence with named people, specific dates, or measured numbers reported as fact.
- **Distinct**: the {n_ideas} angles must foreground *different* facets (different boundaries / criteria / failure modes / checks), so the resulting documents do not overlap.
- **No fabricated specifics**: no invented company names, product names, people, exact figures, or citations presented as real.
- The documents are about agents using the skill {skill_name}; refer to the agent generically ("the agent", "our coding assistant"), never as a specific commercial product.
- In the idea text, describe principles in plain words. Do NOT use shorthand codes like "S1"…"S5" — put those only in the `elements` metadata array.

# Output

Output ONLY a JSON array, no prose:

[
  {{"name": "<3-6 word filename-like name>", "idea": "<1-2 sentence angle on the reasoning>", "elements": ["S2", "S3"]}},
  ...
]
