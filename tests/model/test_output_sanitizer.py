from __future__ import annotations

from src.model.output_sanitizer import (
    detect_script_leakage,
    enforce_language_quality,
    sanitize_model_output,
)


def test_sanitize_model_output_strips_reasoning_block() -> None:
    text = "<think>internal reasoning</think>Câu trả lời cuối cùng."
    assert sanitize_model_output(text) == "Câu trả lời cuối cùng."


def test_detect_script_leakage_flags_cjk() -> None:
    text = "CPU đang ở mức 高 bình thường."
    assert "cjk" in detect_script_leakage(text)


def test_detect_script_leakage_ignores_code_span() -> None:
    text = "Chạy lệnh `top -bn1 中文` để kiểm tra."
    assert detect_script_leakage(text) == ()


def test_enforce_language_quality_strips_leaked_script() -> None:
    text = "CPU đang ở mức 高 bình thường."
    cleaned = enforce_language_quality(text, "vi")
    assert "高" not in cleaned
    assert "bình thường" in cleaned


def test_enforce_language_quality_noop_for_english() -> None:
    text = "CPU is currently at 高 percent."
    assert enforce_language_quality(text, "en") == text
