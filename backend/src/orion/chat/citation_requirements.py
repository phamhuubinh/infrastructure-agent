"""Recognize explicit citation output instructions during terminal validation.

This is deliberately conservative: mentioning sources or discussing how to cite
is not an instruction to cite. It does not classify tasks or select/expose tools.
Unrecognized wording remains governed by the model's general citation policy.
"""

from __future__ import annotations

import re
import unicodedata

# Quoted examples, code and Markdown blockquotes are not output instructions.
_QUOTED_DATA = re.compile(
    r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`|"
    r'"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’|(?<!\w)\'[^\'\n]*\'(?!\w)|(?m:^[ \t]*>[^\n]*)'
)
_SOURCE_OBJECT = (
    r"(?:(?:the|your|supporting|exact)\s+)?(?:sources?|citations?|source attribution)\b"
)
_DIRECT_INSTRUCTION = re.compile(
    r"(?:^|[.!?;,\n]\s*|\b(?:and|then|but|và|nhưng)\s+)\s*"
    r"(?:(?:please|can you|could you|would you|hãy|vui lòng)\s+)?"
    r"(?P<negated>(?:do not|don't|don’t|no need to|không|không cần|đừng)\s+)?"
    r"(?:cite\b|(?:include|provide|show|list|give|add)\s+"
    + _SOURCE_OBJECT
    + r"|(?:trích dẫn|dẫn|ghi rõ|nêu rõ)\s+nguồn\b)"
)
_CITATION_MODIFIER = re.compile(r"\b(?:(?P<negated>without|không kèm)|with|kèm)\b")
_MODIFIER_OBJECT = re.compile(r"\s+(?:" + _SOURCE_OBJECT + r"|(?:trích dẫn\s+)?nguồn\b)")


def explicitly_requests_citation(content: str) -> bool:
    """Read direct English/Vietnamese output instructions from the original user text.

    The last explicit instruction wins, including a later opt-out. Call only at
    terminal validation, never as a pre-model routing or tool-exposure decision.
    """
    text = _QUOTED_DATA.sub(" ", unicodedata.normalize("NFC", content)).casefold()
    instructions = [
        (match.start(), match.group("negated") is None)
        for match in _DIRECT_INSTRUCTION.finditer(text)
    ]
    instructions.extend(
        (match.start(), match.group("negated") is None)
        for match in _CITATION_MODIFIER.finditer(text)
        if _MODIFIER_OBJECT.match(text, match.end())
    )
    return max(instructions)[1] if instructions else False
