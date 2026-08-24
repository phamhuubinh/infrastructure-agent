from __future__ import annotations

import re

from src.shared.execution.command_result import redact_sensitive
from src.shared.language import detect_language

_REASONING_BLOCK = re.compile(
    # A missing closing tag must fail closed too. Treating it as ordinary
    # prose was the path that allowed a partial scratchpad to reach users.
    r"<(?P<tag>think|analysis)\b[^>]*>.*?(?:</(?P=tag)\s*>|\Z)",
    flags=re.IGNORECASE | re.DOTALL,
)
_ORPHAN_REASONING_TAG = re.compile(r"</?(?:think|analysis)\b[^>]*>", re.IGNORECASE)
_LABELED_REASONING = re.compile(
    # A plaintext scratchpad is hidden reasoning only when its label begins
    # a line; ordinary prose that merely uses the word remains intact.
    r"(?ims)^(?:analysis|chain\s+of\s+thought|scratchpad)\s*:\s*.*?"
    r"(?=^\s*(?:final|answer|response)\s*:|\Z)",
)


def sanitize_model_output(content: str) -> str:
    """Remove model-internal reasoning from user-visible output.

    Prompt instructions are helpful but not a response-security boundary.
    This is deliberately reusable by providers and the final API serializer.
    """
    visible = content if isinstance(content, str) else str(content)
    while True:
        cleaned = _REASONING_BLOCK.sub("", visible)
        if cleaned == visible:
            break
        visible = cleaned
    visible = _ORPHAN_REASONING_TAG.sub("", visible)
    visible = _LABELED_REASONING.sub("", visible)
    return visible.strip()


# DR1-706: language quality validator.
#
# Detects unexpected script leakage (CJK/Cyrillic characters appearing in a
# Vietnamese answer) so a mixed-language response can be regenerated instead
# of shipped as-is. Code blocks and inline-code spans are excluded because
# technical identifiers legitimately vary.

_CODE_SPAN = re.compile(r"```.*?```|`[^`]*`", flags=re.DOTALL)

_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]"  # Han, Hiragana/Katakana, Hangul
)
_CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04FF]")


def detect_script_leakage(text: str) -> tuple[str, ...]:
    """Return the unexpected scripts (if any) found outside of code spans."""

    stripped = _CODE_SPAN.sub("", text)
    leaked: list[str] = []
    if _CJK_PATTERN.search(stripped):
        leaked.append("cjk")
    if _CYRILLIC_PATTERN.search(stripped):
        leaked.append("cyrillic")
    return tuple(leaked)


def sanitize_api_response(text: str, question: str) -> str:
    """Final defense-in-depth boundary for every user-visible response.

    Combines hidden-reasoning removal, script-leakage filtering, and an honest
    empty-response fallback.  This is the single function the API layer uses so
    a normal answer, a deterministic refusal, an external-verification answer,
    and any fallback/error path all converge on the same final boundary
    (GA2-B05).
    """
    visible = redact_sensitive(sanitize_model_output(text))
    visible = enforce_language_quality(visible, detect_language(question))
    return visible or (
        "Không thể trả về nội dung đó an toàn. Hãy gửi lại yêu cầu theo cách khác."
    )


def enforce_language_quality(text: str, expected_lang: str) -> str:
    """DR1-706: strip mixed-script leakage from a Latin-script answer.

    Vietnamese and English both use Latin scripts. On detection, drop CJK and
    Cyrillic leakage rather than rewriting the sentence, since Orion cannot
    safely regenerate a response inline here without another model round trip.
    """

    if expected_lang not in {"vi", "en"}:
        return text
    if not detect_script_leakage(text):
        return text

    def _strip_unexpected(segment: str) -> str:
        segment = _CJK_PATTERN.sub("", segment)
        return _CYRILLIC_PATTERN.sub("", segment)

    # Preserve code spans verbatim; clean everything else.
    parts = _CODE_SPAN.split(text)
    code_spans = _CODE_SPAN.findall(text)
    cleaned_parts = [_strip_unexpected(part) for part in parts]
    rebuilt: list[str] = []
    for index, part in enumerate(cleaned_parts):
        rebuilt.append(part)
        if index < len(code_spans):
            rebuilt.append(code_spans[index])
    return "".join(rebuilt)
