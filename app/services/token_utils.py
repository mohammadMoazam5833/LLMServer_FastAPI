from __future__ import annotations

import re


def estimate_text_tokens(text: str) -> int:
    """Approximate token count for a text string.

    This is a heuristic suitable for mixed Persian/English text and OpenAI-like
    chat prompts. It counts word-like units and breaks long tokens into smaller
    subtoken segments, then applies a minimum of 1.
    """
    text = (text or "").strip()
    if not text:
        return 1

    parts = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    tokens = 0
    for part in parts:
        if len(part) <= 4:
            tokens += 1
        else:
            tokens += (len(part) + 3) // 4
    return max(1, tokens)


def estimate_message_tokens(message: dict) -> int:
    return estimate_text_tokens(message.get("content", "")) + 4
