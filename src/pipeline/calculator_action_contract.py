"""Strict canonical capability contract for deterministic calculation.

This adapter owns the JSON-safe calculator action shape and the one-way
conversion to the reviewed :mod:`basic_calculator` request contract.  It does
not inspect natural-language input or execute arithmetic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TypeVar

from src.agent.capabilities import CapabilityDefinition
from src.agent.permissions import EffectClass
from src.pipeline.basic_calculator import (
    CalculatorDurationUnit,
    CalculatorOperation,
    CalculatorRateUnit,
    CalculatorRequest,
)

CALCULATOR_CAPABILITY_ID = "compute.deterministic"
MAX_CALCULATOR_VALUES = 16


class CalculatorActionBindingError(ValueError):
    """Raised when validated JSON transport cannot form a calculator request."""


def calculator_arguments_schema() -> dict[str, object]:
    """Return the sole strict JSON transport schema for calculator actions."""

    number: dict[str, object] = {"type": "number"}
    unit = {"type": "string", "minLength": 1, "maxLength": 64}
    duration_unit = {
        "type": "string",
        "enum": [item.value for item in CalculatorDurationUnit],
    }
    rate_unit = {
        "type": "string",
        "enum": [item.value for item in CalculatorRateUnit],
    }

    def branch(
        operations: tuple[CalculatorOperation, ...],
        properties: dict[str, object],
        required: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [item.value for item in operations],
                },
                **properties,
            },
            "required": ["operation", *required],
        }

    return {
        "oneOf": [
            branch(
                (
                    CalculatorOperation.ADD,
                    CalculatorOperation.SUBTRACT,
                    CalculatorOperation.MULTIPLY,
                    CalculatorOperation.DIVIDE,
                ),
                {"left": number, "right": number, "unit": unit},
                ("left", "right"),
            ),
            branch(
                (CalculatorOperation.AVERAGE,),
                {
                    "values": {
                        "type": "array",
                        "items": number,
                        "minItems": 1,
                        "maxItems": MAX_CALCULATOR_VALUES,
                    },
                    "unit": unit,
                },
                ("values",),
            ),
            branch(
                (CalculatorOperation.PERCENT_OF,),
                {"base_value": number, "percent": number, "unit": unit},
                ("base_value", "percent"),
            ),
            branch(
                (CalculatorOperation.WORKER_TASK_RATE,),
                {
                    "total_tasks": number,
                    "workers": number,
                    "duration": number,
                    "duration_unit": duration_unit,
                },
                ("total_tasks", "workers", "duration", "duration_unit"),
            ),
            branch(
                (CalculatorOperation.RATE_CONVERT,),
                {
                    "rate_value": number,
                    "rate_unit": rate_unit,
                    "target_rate_unit": rate_unit,
                    "unit": unit,
                },
                ("rate_value", "rate_unit", "target_rate_unit"),
            ),
        ],
    }


def calculator_capability() -> CapabilityDefinition:
    """Return Calculator's reviewed local capability registration."""

    return CapabilityDefinition(
        capability_id=CALCULATOR_CAPABILITY_ID,
        purpose="Perform exact arithmetic with deterministic computation",
        tool_id="calculator",
        effect=EffectClass.READ,
        arguments_schema=calculator_arguments_schema(),
        runtime_binding="calculator.execute",
        discovery_group="calculator",
        available=True,
        safety_reviewed=True,
        budget_cost=1,
        result_kind="deterministic_result",
        activity_label="Calculating",
    )


def bind_calculator_action(arguments: Mapping[str, object]) -> CalculatorRequest:
    """Bind exactly the canonical transport fields to ``CalculatorRequest``.

    JSON numbers are converted through their decimal text representation to
    avoid binary-float expansion.  This function is deliberately incapable of
    accepting an expression or evaluating text.
    """

    if not isinstance(arguments, Mapping):
        raise CalculatorActionBindingError("arguments must be an object")
    try:
        operation = CalculatorOperation(_required_string(arguments["operation"]))
        return _request_for_operation(operation, arguments)
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise CalculatorActionBindingError("invalid_calculator_transport") from exc


def _required_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _decimal(value: object) -> Decimal:
    if type(value) not in {int, float}:
        raise TypeError("expected JSON number")
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError("expected finite number")
    return decimal


def _decimal_values(value: object) -> tuple[Decimal, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("values must be an array")
    if not 1 <= len(value) <= MAX_CALCULATOR_VALUES:
        raise ValueError("values array length is invalid")
    return tuple(_decimal(item) for item in value)


_CalculatorEnum = TypeVar("_CalculatorEnum", CalculatorDurationUnit, CalculatorRateUnit)


def _enum(enum_type: type[_CalculatorEnum], value: object) -> _CalculatorEnum:
    if not isinstance(value, str):
        raise TypeError("expected enum string")
    return enum_type(value)


def _optional_unit(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError("invalid unit")
    return value


def _request_for_operation(
    operation: CalculatorOperation,
    arguments: Mapping[str, object],
) -> CalculatorRequest:
    binary = {
        CalculatorOperation.ADD,
        CalculatorOperation.SUBTRACT,
        CalculatorOperation.MULTIPLY,
        CalculatorOperation.DIVIDE,
    }
    if operation in binary:
        _exact_keys(
            arguments,
            {"operation", "left", "right", "unit"},
            {"operation", "left", "right"},
        )
        return CalculatorRequest(
            operation,
            left=_decimal(arguments["left"]),
            right=_decimal(arguments["right"]),
            unit=_optional_unit(arguments.get("unit")),
        )
    if operation is CalculatorOperation.AVERAGE:
        _exact_keys(
            arguments,
            {"operation", "values", "unit"},
            {"operation", "values"},
        )
        return CalculatorRequest(
            operation,
            values=_decimal_values(arguments["values"]),
            unit=_optional_unit(arguments.get("unit")),
        )
    if operation is CalculatorOperation.PERCENT_OF:
        _exact_keys(
            arguments,
            {"operation", "base_value", "percent", "unit"},
            {"operation", "base_value", "percent"},
        )
        return CalculatorRequest(
            operation,
            base_value=_decimal(arguments["base_value"]),
            percent=_decimal(arguments["percent"]),
            unit=_optional_unit(arguments.get("unit")),
        )
    if operation is CalculatorOperation.WORKER_TASK_RATE:
        _exact_keys(
            arguments,
            {"operation", "total_tasks", "workers", "duration", "duration_unit"},
            {"operation", "total_tasks", "workers", "duration", "duration_unit"},
        )
        return CalculatorRequest(
            operation,
            total_tasks=_decimal(arguments["total_tasks"]),
            workers=_decimal(arguments["workers"]),
            duration=_decimal(arguments["duration"]),
            duration_unit=_enum(CalculatorDurationUnit, arguments["duration_unit"]),
        )
    _exact_keys(
        arguments,
        {"operation", "rate_value", "rate_unit", "target_rate_unit", "unit"},
        {"operation", "rate_value", "rate_unit", "target_rate_unit"},
    )
    return CalculatorRequest(
        operation,
        rate_value=_decimal(arguments["rate_value"]),
        rate_unit=_enum(CalculatorRateUnit, arguments["rate_unit"]),
        target_rate_unit=_enum(CalculatorRateUnit, arguments["target_rate_unit"]),
        unit=_optional_unit(arguments.get("unit")),
    )


def _exact_keys(
    arguments: Mapping[str, object], allowed: set[str], required: set[str]
) -> None:
    if set(arguments) - allowed:
        raise ValueError("undeclared_transport_fields")
    if required - set(arguments):
        raise ValueError("missing_transport_fields")


__all__ = [
    "CALCULATOR_CAPABILITY_ID",
    "MAX_CALCULATOR_VALUES",
    "CalculatorActionBindingError",
    "bind_calculator_action",
    "calculator_capability",
    "calculator_arguments_schema",
]
