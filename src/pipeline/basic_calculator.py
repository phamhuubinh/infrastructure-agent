"""GA2-H04: narrow deterministic arithmetic for safe, self-contained math.

This is intentionally *not* a general expression evaluator.  It accepts only
a small, safe grammar (numbers, + - * /, parentheses, commas for lists,
``average(...)``, ``min``, ``max``) and returns a typed result.  It is used
only for self-contained supplied data — never to evaluate user code or shell
content.

Examples:
    ``64 - 18``             -> 46
    ``average(20, 40, 60)`` -> 40
    ``(8 + 2) * 3``         -> 30
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum


class CalculatorOperation(str, Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    AVERAGE = "average"
    PERCENT_OF = "percent_of"
    WORKER_TASK_RATE = "worker_task_rate"
    RATE_CONVERT = "rate_convert"


class CalculatorRateUnit(str, Enum):
    PER_SECOND = "per_second"
    PER_MINUTE = "per_minute"
    PER_HOUR = "per_hour"


class CalculatorDurationUnit(str, Enum):
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"


class CalculatorResultStatus(str, Enum):
    SUCCESS = "success"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class CalculatorRequest:
    """Structured arithmetic selected by semantic planning.

    Fields are operation-specific.  The calculator never discovers operands
    by scraping arbitrary prose on this path.
    """

    operation: CalculatorOperation
    values: tuple[Decimal, ...] = ()
    left: Decimal | None = None
    right: Decimal | None = None
    base_value: Decimal | None = None
    percent: Decimal | None = None
    total_tasks: Decimal | None = None
    workers: Decimal | None = None
    duration: Decimal | None = None
    duration_unit: CalculatorDurationUnit | None = None
    rate_value: Decimal | None = None
    rate_unit: CalculatorRateUnit | None = None
    target_rate_unit: CalculatorRateUnit | None = None
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class CalculatorContractResult:
    status: CalculatorResultStatus
    operation: CalculatorOperation | None
    value: Decimal | None = None
    unit: str | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is CalculatorResultStatus.SUCCESS

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "operation": self.operation.value if self.operation is not None else None,
            "value": str(self.value) if self.value is not None else None,
            "unit": self.unit,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CalculationResult:
    """Typed result of a safe arithmetic evaluation."""

    ok: bool
    value: Decimal | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "value": str(self.value) if self.value is not None else None,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class SuppliedCalculation:
    """A recognized natural-language calculation with an optional unit."""

    result: CalculationResult
    unit: str | None = None
    recognized: bool = False


def _safe_div(left: Decimal, right: Decimal) -> Decimal:
    """Division that rejects a zero divisor explicitly."""
    if right == 0:
        raise ZeroDivisionError("division by zero")
    return left / right


_BINOPS: dict[type, Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: _safe_div,
}
_UNARYOPS: dict[type, Callable[[Decimal], Decimal]] = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}
_ALLOWED_FUNCTIONS = frozenset({"average", "avg", "min", "max", "round"})


class _SafeEvaluator:
    """AST evaluator restricted to the safe arithmetic grammar."""

    def evaluate(self, expression: str) -> Decimal:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid arithmetic expression: {exc}") from exc
        if not isinstance(tree, ast.Expression):
            raise ValueError("Expected a single arithmetic expression.")
        value = self._visit(tree.body)
        if not isinstance(value, Decimal):
            raise ValueError("Expression must evaluate to a number.")
        return value

    def _visit(self, node: ast.AST) -> object:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                raise ValueError("Boolean constants are not allowed.")
            if isinstance(node.value, (int, float)):
                try:
                    return Decimal(str(node.value))
                except InvalidOperation as exc:
                    raise ValueError("Invalid numeric constant.") from exc
            raise ValueError("Only numeric constants are allowed.")
        if isinstance(node, ast.BinOp):
            bin_op = _BINOPS.get(type(node.op))
            if bin_op is None:
                raise ValueError("Unsupported binary operator.")
            left = self._visit(node.left)
            right = self._visit(node.right)
            if not isinstance(left, Decimal) or not isinstance(right, Decimal):
                raise ValueError("Operands must be numeric.")
            try:
                return bin_op(left, right)
            except ZeroDivisionError as exc:
                raise ValueError(str(exc)) from exc
        if isinstance(node, ast.UnaryOp):
            unary_op = _UNARYOPS.get(type(node.op))
            if unary_op is None:
                raise ValueError("Unsupported unary operator.")
            value = self._visit(node.operand)
            if not isinstance(value, Decimal):
                raise ValueError("Operand must be numeric.")
            return unary_op(value)
        if isinstance(node, ast.Call):
            func_name = self._safe_name(node.func)
            if func_name not in _ALLOWED_FUNCTIONS:
                raise ValueError(f"Unsupported function '{func_name}'.")
            if node.keywords:
                raise ValueError("Function keyword arguments are not allowed.")
            args: list[Decimal] = []
            for arg in node.args:
                value = self._visit(arg)
                if not isinstance(value, Decimal):
                    raise ValueError("Function arguments must be numeric.")
                args.append(value)
            return self._apply_function(func_name, args)
        if isinstance(node, ast.Name):
            raise ValueError("Variables are not allowed; supply concrete values.")
        raise ValueError("Expression contains an unsupported construct.")

    @staticmethod
    def _safe_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        raise ValueError("Only simple function names are allowed.")

    @staticmethod
    def _apply_function(name: str, args: list[Decimal]) -> Decimal:
        if name in {"average", "avg"}:
            if not args:
                raise ValueError("average() requires at least one value.")
            return sum(args, Decimal(0)) / Decimal(len(args))
        if name == "min":
            if not args:
                raise ValueError("min() requires at least one value.")
            return min(args)
        if name == "max":
            if not args:
                raise ValueError("max() requires at least one value.")
            return max(args)
        if name == "round":
            if len(args) != 2:
                raise ValueError("round(value, ndigits) requires two arguments.")
            return args[0].quantize(Decimal(1).scaleb(-int(args[1])))
        raise ValueError(f"Unsupported function '{name}'.")


_ARITHMETIC_RE = re.compile(
    r"^\s*(?:[-+()\d.,\s*/]|average|avg|min|max|round)+\s*$",
    re.IGNORECASE,
)


def looks_like_arithmetic(text: str) -> bool:
    """Return True when the whole text is a safe arithmetic expression."""
    return bool(_ARITHMETIC_RE.match(text.strip()))


def calculate(expression: str) -> CalculationResult:
    """Evaluate one narrow arithmetic expression deterministically."""
    clean = expression.strip()
    if not clean:
        return CalculationResult(False, error="Empty expression.")
    if not looks_like_arithmetic(clean):
        return CalculationResult(
            False, error="Expression contains characters outside the safe grammar."
        )
    try:
        value = _SafeEvaluator().evaluate(clean)
    except (ValueError, InvalidOperation) as exc:
        return CalculationResult(False, error=str(exc))
    return CalculationResult(True, value=value)


def calculate_request(request: CalculatorRequest) -> CalculatorContractResult:
    """Execute one validated structured request without reading user prose."""

    if not isinstance(request, CalculatorRequest):
        raise TypeError("request must be a CalculatorRequest.")
    operation = request.operation
    if not isinstance(operation, CalculatorOperation):
        return CalculatorContractResult(
            CalculatorResultStatus.UNSUPPORTED,
            None,
            reason="unsupported_operation",
        )

    invalid_field = _invalid_decimal_field(request)
    if invalid_field is not None:
        return CalculatorContractResult(
            CalculatorResultStatus.INVALID,
            operation,
            reason=f"invalid_{invalid_field}",
        )

    if operation is CalculatorOperation.AVERAGE:
        if not request.values or _has_values_outside(request, {"values", "unit"}):
            return _ambiguous(operation, "average_requires_values_only")
        value = sum(request.values, Decimal(0)) / Decimal(len(request.values))
        return _success(request, value, request.unit)

    binary = {
        CalculatorOperation.ADD: lambda left, right: left + right,
        CalculatorOperation.SUBTRACT: lambda left, right: left - right,
        CalculatorOperation.MULTIPLY: lambda left, right: left * right,
        CalculatorOperation.DIVIDE: _safe_div,
    }.get(operation)
    if binary is not None:
        if (
            request.left is None
            or request.right is None
            or _has_values_outside(request, {"left", "right", "unit"})
        ):
            return _ambiguous(operation, "binary_operation_requires_left_and_right")
        try:
            value = binary(request.left, request.right)
        except ZeroDivisionError:
            return CalculatorContractResult(
                CalculatorResultStatus.INVALID,
                operation,
                reason="division_by_zero",
            )
        return _success(request, value, request.unit)

    if operation is CalculatorOperation.PERCENT_OF:
        if (
            request.base_value is None
            or request.percent is None
            or _has_values_outside(request, {"base_value", "percent", "unit"})
        ):
            return _ambiguous(operation, "percent_of_requires_base_and_percent")
        if request.percent < 0 or request.percent > 100:
            return CalculatorContractResult(
                CalculatorResultStatus.INVALID,
                operation,
                reason="percent_out_of_range",
            )
        return _success(
            request,
            request.base_value * request.percent / Decimal(100),
            request.unit,
        )

    if operation is CalculatorOperation.WORKER_TASK_RATE:
        if (
            request.total_tasks is None
            or request.workers is None
            or request.duration is None
            or request.duration_unit is None
            or _has_values_outside(
                request,
                {"total_tasks", "workers", "duration", "duration_unit"},
            )
        ):
            return _ambiguous(
                operation,
                "worker_task_rate_requires_tasks_workers_duration",
            )
        if request.total_tasks < 0 or request.workers <= 0 or request.duration <= 0:
            return CalculatorContractResult(
                CalculatorResultStatus.INVALID,
                operation,
                reason="worker_task_rate_requires_positive_denominators",
            )
        minutes = _duration_in_minutes(request.duration, request.duration_unit)
        return _success(
            request,
            request.total_tasks / request.workers / minutes,
            "tasks/worker/minute",
        )

    if operation is CalculatorOperation.RATE_CONVERT:
        if (
            request.rate_value is None
            or request.rate_unit is None
            or request.target_rate_unit is None
            or _has_values_outside(
                request,
                {"rate_value", "rate_unit", "target_rate_unit", "unit"},
            )
        ):
            return _ambiguous(operation, "rate_convert_requires_rate_and_units")
        if request.rate_value < 0:
            return CalculatorContractResult(
                CalculatorResultStatus.INVALID,
                operation,
                reason="rate_must_be_non_negative",
            )
        per_second = request.rate_value / _seconds_per_rate_unit(request.rate_unit)
        value = per_second * _seconds_per_rate_unit(request.target_rate_unit)
        base = request.unit or "items"
        unit = f"{base}/{_rate_unit_label(request.target_rate_unit)}"
        return _success(request, value, unit)

    return CalculatorContractResult(
        CalculatorResultStatus.UNSUPPORTED,
        operation,
        reason="unsupported_operation",
    )


def _success(
    request: CalculatorRequest,
    value: Decimal,
    unit: str | None,
) -> CalculatorContractResult:
    return CalculatorContractResult(
        CalculatorResultStatus.SUCCESS,
        request.operation,
        value=value,
        unit=unit,
    )


def _ambiguous(
    operation: CalculatorOperation,
    reason: str,
) -> CalculatorContractResult:
    return CalculatorContractResult(
        CalculatorResultStatus.AMBIGUOUS,
        operation,
        reason=reason,
    )


def _invalid_decimal_field(request: CalculatorRequest) -> str | None:
    names = (
        "left",
        "right",
        "base_value",
        "percent",
        "total_tasks",
        "workers",
        "duration",
        "rate_value",
    )
    for name in names:
        value = getattr(request, name)
        if value is not None and not isinstance(value, Decimal):
            return name
    if not isinstance(request.values, tuple) or any(
        not isinstance(value, Decimal) for value in request.values
    ):
        return "values"
    if request.unit is not None and (
        not isinstance(request.unit, str)
        or not request.unit.strip()
        or len(request.unit) > 64
    ):
        return "unit"
    if request.duration_unit is not None and not isinstance(
        request.duration_unit, CalculatorDurationUnit
    ):
        return "duration_unit"
    if request.rate_unit is not None and not isinstance(
        request.rate_unit, CalculatorRateUnit
    ):
        return "rate_unit"
    if request.target_rate_unit is not None and not isinstance(
        request.target_rate_unit, CalculatorRateUnit
    ):
        return "target_rate_unit"
    return None


def _has_values_outside(
    request: CalculatorRequest,
    allowed: set[str],
) -> bool:
    values: dict[str, object] = {
        "values": request.values,
        "left": request.left,
        "right": request.right,
        "base_value": request.base_value,
        "percent": request.percent,
        "total_tasks": request.total_tasks,
        "workers": request.workers,
        "duration": request.duration,
        "duration_unit": request.duration_unit,
        "rate_value": request.rate_value,
        "rate_unit": request.rate_unit,
        "target_rate_unit": request.target_rate_unit,
        "unit": request.unit,
    }
    return any(
        name not in allowed and value not in (None, (), "")
        for name, value in values.items()
    )


def _duration_in_minutes(
    value: Decimal,
    unit: CalculatorDurationUnit,
) -> Decimal:
    return {
        CalculatorDurationUnit.SECONDS: value / Decimal(60),
        CalculatorDurationUnit.MINUTES: value,
        CalculatorDurationUnit.HOURS: value * Decimal(60),
    }[unit]


def _seconds_per_rate_unit(unit: CalculatorRateUnit) -> Decimal:
    return {
        CalculatorRateUnit.PER_SECOND: Decimal(1),
        CalculatorRateUnit.PER_MINUTE: Decimal(60),
        CalculatorRateUnit.PER_HOUR: Decimal(3600),
    }[unit]


def _rate_unit_label(unit: CalculatorRateUnit) -> str:
    return {
        CalculatorRateUnit.PER_SECOND: "second",
        CalculatorRateUnit.PER_MINUTE: "minute",
        CalculatorRateUnit.PER_HOUR: "hour",
    }[unit]


_COUNT_NOUN_PATTERN = (
    r"\b\d+(?:[.,]\d+)?\s+"
    r"(?:máy|may|máy chủ|may chu|machines?|workers?|servers?|nodes?|hosts?|vms?|"
    r"containers?|instances?|processes?)\b"
)


def calculate_supplied_text(text: str) -> SuppliedCalculation:
    """Parse only reviewed VI/EN supplied-data arithmetic forms."""
    lower = " ".join(text.casefold().split())
    numbers = [Decimal(value.replace(",", ".")) for value in re.findall(r"\d+(?:[.,]\d+)?", lower)]

    if any(marker in lower for marker in ("average", "trung bình", "trung binh")):
        # A count of machines/workers (e.g. "3 máy") is context, not an
        # operand; averaging it in silently corrupts the result.
        filtered = re.sub(_COUNT_NOUN_PATTERN, " ", lower)
        operands = [
            Decimal(value.replace(",", "."))
            for value in re.findall(r"\d+(?:[.,]\d+)?", filtered)
        ]
        if len(operands) < 2:
            return SuppliedCalculation(CalculationResult(False, error="Missing values."), recognized=True)
        return SuppliedCalculation(
            CalculationResult(
                True,
                sum(operands, Decimal(0)) / Decimal(len(operands)),
            ),
            recognized=True,
        )
    remaining = re.search(
        r"(\d+(?:[.,]\d+)?)\s*gb\s*(?:total|tổng|tong).*?(\d+(?:[.,]\d+)?)\s*gb\s*(?:used|đã dùng|da dung)",
        lower,
    )
    if remaining:
        total, used = (Decimal(item.replace(",", ".")) for item in remaining.groups())
        return SuppliedCalculation(CalculationResult(True, total - used), unit="GB", recognized=True)
    if ("then divide by" in lower or "rồi chia" in lower or "roi chia" in lower) and len(numbers) >= 2:
        divisor = numbers[-1]
        if divisor == 0:
            return SuppliedCalculation(CalculationResult(False, error="division by zero"), recognized=True)
        return SuppliedCalculation(CalculationResult(True, sum(numbers[:-1], Decimal(0)) / divisor), recognized=True)
    if "availability" in lower or "sẵn sàng" in lower or "san sang" in lower:
        availability = re.search(r"(\d+(?:[.,]\d+)?)\s*%", lower)
        days = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:days?|ngày|ngay)", lower)
        if availability is None or days is None:
            return SuppliedCalculation(CalculationResult(False, error="Missing availability period."), recognized=True)
        percent = Decimal(availability.group(1).replace(",", "."))
        period_days = Decimal(days.group(1).replace(",", "."))
        if not Decimal(0) <= percent <= Decimal(100) or period_days <= 0:
            return SuppliedCalculation(CalculationResult(False, error="Invalid availability input."), recognized=True)
        downtime_minutes = period_days * Decimal(24 * 60) * (Decimal(100) - percent) / Decimal(100)
        return SuppliedCalculation(CalculationResult(True, downtime_minutes), unit="minutes", recognized=True)
    return SuppliedCalculation(CalculationResult(False), recognized=False)


def format_value(value: Decimal) -> str:
    """Render a Decimal as a compact human-readable number."""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


__all__ = [
    "CalculatorContractResult",
    "CalculatorDurationUnit",
    "CalculatorOperation",
    "CalculatorRateUnit",
    "CalculatorRequest",
    "CalculatorResultStatus",
    "CalculationResult",
    "calculate",
    "calculate_request",
    "format_value",
    "calculate_supplied_text",
    "SuppliedCalculation",
    "looks_like_arithmetic",
]
