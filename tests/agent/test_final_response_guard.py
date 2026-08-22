from __future__ import annotations

from decimal import Decimal

from src.agent.final_response_guard import (
    FinalResponseConstraints,
    FinalResponseGuard,
    FinalResponseViolation,
    response_is_honestly_unavailable_or_unverified,
    response_reports_unavailable_or_unverified,
)
from src.pipeline.basic_calculator import (
    CalculatorContractResult,
    CalculatorOperation,
    CalculatorResultStatus,
)


def test_localhost_claim_cannot_pass_for_validated_monitor_target() -> None:
    result = FinalResponseGuard().validate(
        "CPU on localhost is 20%.",
        FinalResponseConstraints(validated_target="monitor"),
    )

    assert not result.passed
    assert FinalResponseViolation.TARGET_MISMATCH in result.violations
    assert "localhost" not in result.text


def test_conflicting_calculator_result_is_replaced_with_exact_value() -> None:
    calculation = CalculatorContractResult(
        CalculatorResultStatus.SUCCESS,
        CalculatorOperation.AVERAGE,
        value=Decimal("40"),
    )

    result = FinalResponseGuard().validate(
        "Result: 41.",
        FinalResponseConstraints(calculator_result=calculation),
    )

    assert result.violations == (FinalResponseViolation.CALCULATOR_MISMATCH,)
    assert result.text == "Result: 40."


def test_unverified_current_fact_cannot_be_presented_as_current_value() -> None:
    result = FinalResponseGuard().validate(
        "The current price is 100 USD.",
        FinalResponseConstraints(current_required=True, current_verified=False),
    )

    assert FinalResponseViolation.CURRENT_UNVERIFIED in result.violations
    assert "could not be verified" in result.text


def test_completion_unavailable_helper_rejects_mixed_confident_response() -> None:
    response = "Evidence is unavailable, but the result is definitely 42."

    assert response_reports_unavailable_or_unverified(response)
    assert not response_is_honestly_unavailable_or_unverified(response)


def test_only_used_provenance_may_be_cited() -> None:
    result = FinalResponseGuard().validate(
        "Verified from https://unrelated.example/data",
        FinalResponseConstraints(
            current_required=True,
            current_verified=True,
            used_provenance=("https://used.example/data",),
        ),
    )

    assert FinalResponseViolation.PROVENANCE_NOT_USED in result.violations
    assert "unrelated.example" not in result.text


def test_verified_read_only_response_with_used_source_passes() -> None:
    result = FinalResponseGuard().validate(
        "Current information is verified: https://used.example/data",
        FinalResponseConstraints(
            current_required=True,
            current_verified=True,
            used_provenance=("https://used.example/data",),
        ),
    )

    assert result.passed


def test_exact_sentence_count_passes_for_matching_response() -> None:
    result = FinalResponseGuard().validate(
        "Tôi là Orion. Tôi có thể hỗ trợ phân tích. "
        "Tôi hoạt động theo các giới hạn an toàn.",
        FinalResponseConstraints(requested_sentence_count=3),
    )

    assert result.passed


def test_exact_sentence_count_rejects_a_shorter_response() -> None:
    result = FinalResponseGuard().validate(
        "Câu trả lời ngắn đúng ba câu.",
        FinalResponseConstraints(requested_sentence_count=3),
    )

    assert not result.passed
    assert FinalResponseViolation.SHAPE_MISMATCH in result.violations


def test_exact_sentence_count_rejects_a_longer_response() -> None:
    result = FinalResponseGuard().validate(
        "One. Two. Three. Four.",
        FinalResponseConstraints(requested_sentence_count=3),
    )

    assert not result.passed
    assert FinalResponseViolation.SHAPE_MISMATCH in result.violations


def test_sentence_count_ignores_decimals_and_supports_unicode_terminators() -> None:
    result = FinalResponseGuard().validate(
        "Giá trị là 3.14. Tiếp theo。Kết thúc!",
        FinalResponseConstraints(requested_sentence_count=3),
    )

    assert result.passed


def test_without_sentence_count_constraint_no_shape_check_applies() -> None:
    result = FinalResponseGuard().validate(
        "Câu trả lời ngắn đúng ba câu.",
        FinalResponseConstraints(),
    )

    assert result.passed
