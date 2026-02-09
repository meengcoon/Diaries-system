from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

# Default replacement for any explicitly-marked sensitive segment.
# Must NOT contain '[' or ']' so it won't trigger the bracket leak check.
DEFAULT_PLACEHOLDER = "__"

# Non-greedy match for: [ ... ] (allowing newlines inside).
_BRACKET_RE = re.compile(r"\[[\s\S]*?\]")

def redact_text(text: str, placeholder: str = DEFAULT_PLACEHOLDER) -> str:
    """
    Replace any `[ ... ]` segments in `text` with `placeholder`.
    The brackets are removed as part of the replacement.

    Example:
      "晚饭：[米饭、青菜]" -> "晚饭：__"
    """
    if not text:
        return text
    return _BRACKET_RE.sub(placeholder, text)

# Backwards-compatible alias (older code might call this).
def redact_square_brackets(text: str, repl: str = DEFAULT_PLACEHOLDER) -> str:
    return redact_text(text, placeholder=repl)

def redact_messages(
    messages: Iterable[Dict[str, Any]],
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> List[Dict[str, Any]]:
    """
    Redact bracket-marked segments for chat-style payloads.

    Supports keys:
      - {"role": "...", "content": "..."}
      - {"idx": 1, "text": "..."}
    """
    out: List[Dict[str, Any]] = []
    for m in messages:
        m2 = dict(m)

        if isinstance(m2.get("content"), str):
            m2["content"] = redact_text(m2["content"], placeholder=placeholder)

        if isinstance(m2.get("text"), str):
            m2["text"] = redact_text(m2["text"], placeholder=placeholder)

        out.append(m2)

    return out

__all__ = [
    "DEFAULT_PLACEHOLDER",
    "redact_text",
    "redact_square_brackets",
    "redact_messages",
]
