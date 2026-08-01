from __future__ import annotations

import re

_REASONING_BLOCK = re.compile(
    r"<(?P<tag>think|analysis)\b[^>]*>.*?</(?P=tag)\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)


def sanitize_model_output(content: str) -> str:
    visible = content
    while True:
        cleaned = _REASONING_BLOCK.sub("", visible)
        if cleaned == visible:
            return cleaned.strip()
        visible = cleaned
