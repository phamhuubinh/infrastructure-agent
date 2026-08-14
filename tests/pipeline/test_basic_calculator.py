"""GA2-H04: deterministic basic calculator regression coverage."""

from __future__ import annotations

from decimal import Decimal

from src.pipeline.basic_calculator import (
    CalculatorDurationUnit,
    CalculatorOperation,
    CalculatorRateUnit,
    CalculatorRequest,
    CalculatorResultStatus,
    calculate,
    calculate_request,
    calculate_supplied_text,
    format_value,
    looks_like_arithmetic,
)


def test_structured_average_uses_exact_operands() -> None:
    result = calculate_request(
        CalculatorRequest(
            CalculatorOperation.AVERAGE,
            values=(Decimal("20"), Decimal("40"), Decimal("60")),
        )
    )

    assert result.status is CalculatorResultStatus.SUCCESS
    assert result.value == Decimal("40")


def test_structured_worker_task_rate_has_explicit_formula_fields() -> None:
    result = calculate_request(
        CalculatorRequest(
            CalculatorOperation.WORKER_TASK_RATE,
            total_tasks=Decimal("800"),
            workers=Decimal("8"),
            duration=Decimal("10"),
            duration_unit=CalculatorDurationUnit.MINUTES,
        )
    )

    assert result.value == Decimal("10")
    assert result.unit == "tasks/worker/minute"


def test_structured_rate_conversion_preserves_unit_semantics() -> None:
    result = calculate_request(
        CalculatorRequest(
            CalculatorOperation.RATE_CONVERT,
            rate_value=Decimal("120"),
            rate_unit=CalculatorRateUnit.PER_MINUTE,
            target_rate_unit=CalculatorRateUnit.PER_SECOND,
            unit="requests",
        )
    )

    assert result.value == Decimal("2")
    assert result.unit == "requests/second"


def test_structured_percent_and_ambiguous_requests_fail_explicitly() -> None:
    invalid_percent = calculate_request(
        CalculatorRequest(
            CalculatorOperation.PERCENT_OF,
            base_value=Decimal("200"),
            percent=Decimal("120"),
        )
    )
    ambiguous = calculate_request(
        CalculatorRequest(CalculatorOperation.DIVIDE, left=Decimal("10"))
    )

    assert invalid_percent.status is CalculatorResultStatus.INVALID
    assert invalid_percent.reason == "percent_out_of_range"
    assert ambiguous.status is CalculatorResultStatus.AMBIGUOUS


def test_natural_language_supplied_forms() -> None:
    assert calculate_supplied_text("average of 20, 40, 60").result.value == Decimal("40")
    remaining = calculate_supplied_text("64 GB total, 18 GB used")
    assert remaining.result.value == Decimal("46")
    assert remaining.unit == "GB"
    assert calculate_supplied_text("64 GB tổng, 18 GB đã dùng").result.value == Decimal("46")
    assert calculate_supplied_text("20 + 40 + 60 then divide by 3").result.value == Decimal("40")
    assert calculate_supplied_text("20 + 40 + 60 rồi chia 3").result.value == Decimal("40")
    downtime = calculate_supplied_text("99.9% availability over 30 days")
    assert downtime.result.value == Decimal("43.2")
    assert downtime.unit == "minutes"


def test_natural_language_availability_requires_period() -> None:
    result = calculate_supplied_text("99.9% availability")
    assert result.recognized is True
    assert result.result.ok is False


def test_basic_subtraction() -> None:
    result = calculate("64 - 18")
    assert result.ok is True
    assert result.value == Decimal("46")


def test_average_function() -> None:
    result = calculate("average(20, 40, 60)")
    assert result.ok is True
    assert result.value == Decimal("40")


def test_parentheses_and_multiplication() -> None:
    result = calculate("(8 + 2) * 3")
    assert result.ok is True
    assert result.value == Decimal("30")


def test_division() -> None:
    result = calculate("10 / 4")
    assert result.ok is True
    assert result.value == Decimal("2.5")


def test_division_by_zero_fails_closed() -> None:
    result = calculate("1 / 0")
    assert result.ok is False
    assert "division by zero" in (result.error or "")


def test_min_max_functions() -> None:
    assert calculate("min(3, 1, 2)").value == Decimal("1")
    assert calculate("max(3, 1, 2)").value == Decimal("3")


def test_unsafe_expression_rejected() -> None:
    result = calculate("__import__('os').system('id')")
    assert result.ok is False
    assert result.value is None


def test_nested_function_call_is_allowed_safe() -> None:
    """Nested calls still use only the safe grammar (no variables, imports,
    attributes); they are intentionally allowed."""
    result = calculate("average(1, min(2, 3))")
    assert result.ok is True
    assert result.value == Decimal("1.5")


def test_variables_rejected() -> None:
    result = calculate("x + 1")
    assert result.ok is False


def test_looks_like_arithmetic_guard() -> None:
    assert looks_like_arithmetic("64 - 18") is True
    assert looks_like_arithmetic("average(20, 40, 60)") is True
    assert looks_like_arithmetic("viết script") is False


def test_format_value_integer_and_fraction() -> None:
    assert format_value(Decimal("46")) == "46"
    assert format_value(Decimal("2.50")) == "2.5"
