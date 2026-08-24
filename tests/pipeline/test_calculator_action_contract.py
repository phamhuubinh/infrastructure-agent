from __future__ import annotations

from decimal import Decimal

import pytest

from src.pipeline.basic_calculator import CalculatorResultStatus, calculate_request
from src.pipeline.calculator_action_contract import (
    CalculatorActionBindingError,
    bind_calculator_action,
    calculator_arguments_schema,
)


def test_calculator_schema_is_closed_operation_discriminated_union() -> None:
    schema = calculator_arguments_schema()

    assert set(schema) == {"oneOf"}
    branches = schema["oneOf"]
    assert isinstance(branches, list)
    assert all(branch["additionalProperties"] is False for branch in branches)
    assert all("null" not in str(branch) for branch in branches)

    multiply = next(
        branch
        for branch in branches
        if "multiply" in branch["properties"]["operation"]["enum"]
    )
    assert multiply["required"] == ["operation", "left", "right"]
    assert set(multiply["properties"]) == {"operation", "left", "right", "unit"}


@pytest.mark.parametrize(
    "arguments",
    (
        {"operation": "multiply"},
        {"operation": "multiply", "left": None, "right": None},
        {"operation": "multiply", "left": 2, "right": 3, "values": [2, 3]},
    ),
)
def test_calculator_binding_rejects_missing_null_or_irrelevant_fields(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(CalculatorActionBindingError):
        bind_calculator_action(arguments)


def test_minimal_multiply_binding_preserves_decimal_result() -> None:
    request = bind_calculator_action(
        {"operation": "multiply", "left": 287, "right": 419}
    )

    result = calculate_request(request)

    assert result.status is CalculatorResultStatus.SUCCESS
    assert result.value == Decimal("120253")
