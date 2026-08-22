from __future__ import annotations

import pytest

from src.model.output_sanitizer import (
    detect_script_leakage,
    enforce_language_quality,
    sanitize_api_response,
    sanitize_model_output,
)


def test_sanitize_model_output_strips_reasoning_block() -> None:
    text = "<think>internal reasoning</think>Câu trả lời cuối cùng."
    assert sanitize_model_output(text) == "Câu trả lời cuối cùng."


def test_sanitize_model_output_fails_closed_for_unterminated_reasoning() -> None:
    assert sanitize_model_output("<think>internal reasoning") == ""


def test_sanitize_model_output_strips_plaintext_scratchpad() -> None:
    text = "analysis: hidden reasoning\nfinal: Câu trả lời cuối cùng."

    assert sanitize_model_output(text) == "final: Câu trả lời cuối cùng."


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
    assert "高" not in enforce_language_quality(text, "en")


def test_sanitize_api_response_redacts_deterministic_secret_forms() -> None:
    text = (
        "password=super-secret-value; Authorization: Bearer abc123; "
        "https://user:pass@example.com/"
    )

    sanitized = sanitize_api_response(text, "Show diagnostics.")

    for secret in ("super-secret-value", "abc123", "user:pass@"):
        assert secret not in sanitized
    assert "<redacted>" in sanitized


@pytest.mark.parametrize("label", ("", "RSA ", "OPENSSH "))
def test_sanitize_api_response_redacts_pem_private_key_blocks(label: str) -> None:
    payload = "fixture-private-key-payload"
    text = (
        f"Before\n-----BEGIN {label}PRIVATE KEY-----\n{payload}\n"
        f"-----END {label}PRIVATE KEY-----\nAfter"
    )

    sanitized = sanitize_api_response(text, "Provide a safe final response.")

    assert payload not in sanitized
    assert "BEGIN" not in sanitized
    assert sanitized == "Before\n<redacted>\nAfter"


@pytest.mark.parametrize(
    ("text", "question"),
    (
        ("An API key is a credential used by an API.", "Explain API keys."),
        ("Use the environment variable API_KEY.", "How should I configure it?"),
        (
            "Use `systemctl restart sshd`.",
            "Show the command that would restart sshd, but do not run it.",
        ),
    ),
)
def test_sanitize_api_response_preserves_safe_educational_content(
    text: str, question: str
) -> None:
    assert sanitize_api_response(text, question) == text
