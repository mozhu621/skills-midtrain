"""Single source of truth for chat rendering, shared by SFT training and eval.

Prefers the tokenizer's own chat template; falls back to ChatML (Qwen-style) when a
base model ships without one. Training and inference MUST go through here so the
prompt format the model is fine-tuned on is exactly the format it is evaluated on.
"""
IM_START, IM_END = "<|im_start|>", "<|im_end|>"


def render_chatml(messages, add_generation_prompt: bool = False) -> str:
    s = "".join(f"{IM_START}{m['role']}\n{m['content']}{IM_END}\n" for m in messages)
    if add_generation_prompt:
        s += f"{IM_START}assistant\n"
    return s


def build_prompt(tok, messages, add_generation_prompt: bool = False) -> str:
    if getattr(tok, "chat_template", None):
        return tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=add_generation_prompt)
    return render_chatml(messages, add_generation_prompt)


def encode_completion_only(tok, messages, max_len: int):
    """Return (input_ids, labels) with everything before the final assistant turn masked
    to -100. Returns None if the example is degenerate (empty completion)."""
    prompt_str = build_prompt(tok, messages[:-1], add_generation_prompt=True)
    full_str = build_prompt(tok, messages, add_generation_prompt=False)
    prompt_ids = tok(prompt_str, add_special_tokens=False)["input_ids"]
    full_ids = tok(full_str, add_special_tokens=False)["input_ids"]
    if len(full_ids) <= len(prompt_ids):
        return None
    labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]
    full_ids, labels = full_ids[:max_len], labels[:max_len]
    if all(l == -100 for l in labels):
        return None
    return full_ids, labels
