from __future__ import annotations

from src.model.protocol.prompt_builder_v2 import _detect_language


def test_explicit_english_instruction_overrides_vietnamese_input() -> None:
    assert _detect_language("Answer in English: Docker là gì?") == "en"


def test_explicit_vietnamese_instruction_overrides_english_input() -> None:
    assert _detect_language("Answer in Vietnamese: What is an API?") == "vi"
