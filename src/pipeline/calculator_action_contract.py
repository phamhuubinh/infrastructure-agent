"""Canonical Agent v2 transport binding for deterministic calculation.

This adapter owns the JSON-safe calculator action shape and the one-way
conversion to the reviewed :mod:`basic_calculator` request contract.  It does
not inspect natural-language input or execute arithmetic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TypeVar

from src.pipeline.basic_calculator import (
    CalculatorDurationUnit,
    CalculatorOperation,
    CalculatorRateUnit,
    CalculatorRequest,
)

CALCULATOR_CAPABILITY_ID = "compute.deterministic"
MAX_CALCULATOR_VALUES = 16

_PROPERTY_NAMES = (
    "operation",
    "values",
    "left",
    "right",
    "base_value",
    "percent",
    "total_tasks",
    "workers",
    "duration",
    "duration_unit",
    "rate_value",
    "rate_unit",
    "target_rate_unit",
    "unit",
)


class CalculatorActionBindingError(ValueError):
    """Raised when validated JSON transport cannot form a calculator request."""


def calculator_arguments_schema() -> dict[str, object]:
    """Return the sole strict JSON transport schema for calculator actions."""

    nullable_number: dict[str, object] = {"type": ["number", "null"]}
    nullable_duration = {
        "type": ["string", "null"],
        "enum": [item.value for item in CalculatorDurationUnit] + [None],
    }
    nullable_rate = {
        "type": ["string", "null"],
        "enum": [item.value for item in CalculatorRateUnit] + [None],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "operation": {
                "type": "string",
                "enum": [item.value for item in CalculatorOperation],
            },
            "values": {
                "type": ["array", "null"],
                "items": {"type": "number"},
                "minItems": 1,
                "maxItems": MAX_CALCULATOR_VALUES,
            },
            "left": dict(nullable_number),
            "right": dict(nullable_number),
            "base_value": dict(nullable_number),
            "percent": dict(nullable_number),
            "total_tasks": dict(nullable_number),
            "workers": dict(nullable_number),
            "duration": dict(nullable_number),
            "duration_unit": nullable_duration,
            "rate_value": dict(nullable_number),
            "rate_unit": dict(nullable_rate),
            "target_rate_unit": dict(nullable_rate),
            "unit": {"type": ["string", "null"], "maxLength": 64},
        },
        "required": list(_PROPERTY_NAMES),
    }


def bind_calculator_action(arguments: Mapping[str, object]) -> CalculatorRequest:
    """Bind exactly the canonical transport fields to ``CalculatorRequest``.

    JSON numbers are converted through their decimal text representation to
    avoid binary-float expansion.  This function is deliberately incapable of
    accepting an expression or evaluating text.
    """

    if not isinstance(arguments, Mapping):
        raise CalculatorActionBindingError("arguments must be an object")
    names = set(arguments)
    expected = set(_PROPERTY_NAMES)
    if names != expected:
        missing = expected - names
        if missing:
            raise CalculatorActionBindingError("missing_transport_fields")
        raise CalculatorActionBindingError("undeclared_transport_fields")
    try:
        operation = CalculatorOperation(_required_string(arguments["operation"]))
        values = _decimal_values(arguments["values"])
        return CalculatorRequest(
            operation=operation,
            values=values,
            left=_optional_decimal(arguments["left"]),
            right=_optional_decimal(arguments["right"]),
            base_value=_optional_decimal(arguments["base_value"]),
            percent=_optional_decimal(arguments["percent"]),
            total_tasks=_optional_decimal(arguments["total_tasks"]),
            workers=_optional_decimal(arguments["workers"]),
            duration=_optional_decimal(arguments["duration"]),
            duration_unit=_optional_enum(
                CalculatorDurationUnit, arguments["duration_unit"]
            ),
            rate_value=_optional_decimal(arguments["rate_value"]),
            rate_unit=_optional_enum(CalculatorRateUnit, arguments["rate_unit"]),
            target_rate_unit=_optional_enum(
                CalculatorRateUnit, arguments["target_rate_unit"]
            ),
            unit=_optional_unit(arguments["unit"]),
        )
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise CalculatorActionBindingError("invalid_calculator_transport") from exc


def _required_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if type(value) not in {int, float}:
        raise TypeError("expected JSON number")
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError("expected finite number")
    return decimal


def _decimal_values(value: object) -> tuple[Decimal, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("values must be an array or null")
    if not 1 <= len(value) <= MAX_CALCULATOR_VALUES:
        raise ValueError("values array length is invalid")
    return tuple(_required_decimal(item) for item in value)


def _required_decimal(value: object) -> Decimal:
    decimal = _optional_decimal(value)
    if decimal is None:
        raise TypeError("values must contain JSON numbers")
    return decimal


_CalculatorEnum = TypeVar("_CalculatorEnum", CalculatorDurationUnit, CalculatorRateUnit)


def _optional_enum(
    enum_type: type[_CalculatorEnum], value: object
) -> _CalculatorEnum | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("expected enum string")
    return enum_type(value)


def _optional_unit(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError("invalid unit")
    return value


__all__ = [
    "CALCULATOR_CAPABILITY_ID",
    "MAX_CALCULATOR_VALUES",
    "CalculatorActionBindingError",
    "bind_calculator_action",
    "calculator_arguments_schema",
]
