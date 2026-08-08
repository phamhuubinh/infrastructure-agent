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
            op = _BINOPS.get(type(node.op))
            if op is None:
                raise ValueError("Unsupported binary operator.")
            left = self._visit(node.left)
            right = self._visit(node.right)
            if not isinstance(left, Decimal) or not isinstance(right, Decimal):
                raise ValueError("Operands must be numeric.")
            try:
                return op(left, right)
            except ZeroDivisionError as exc:
                raise ValueError(str(exc)) from exc
        if isinstance(node, ast.UnaryOp):
            op = _UNARYOPS.get(type(node.op))
            if op is None:
                raise ValueError("Unsupported unary operator.")
            value = self._visit(node.operand)
            if not isinstance(value, Decimal):
                raise ValueError("Operand must be numeric.")
            return op(value)
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


def format_value(value: Decimal) -> str:
    """Render a Decimal as a compact human-readable number."""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


__all__ = [
    "CalculationResult",
    "calculate",
    "format_value",
    "looks_like_arithmetic",
]
