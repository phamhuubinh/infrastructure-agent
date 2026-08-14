from __future__ import annotations

from decimal import Decimal

from src.agent.final_response_guard import (
    FinalResponseConstraints,
    FinalResponseGuard,
    FinalResponseViolation,
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
