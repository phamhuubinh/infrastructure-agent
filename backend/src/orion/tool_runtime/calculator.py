"""A deterministic, scope-independent first real Orion tool."""

from __future__ import annotations

import ast
import math
from collections.abc import Callable

from orion.contracts import ToolCall, ToolDefinition, ToolResult

MAX_EXPRESSION_LENGTH = 4096
MAX_AST_NODES = 256
MAX_AST_DEPTH = 32
MAX_INTEGER_BITS = 4096

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[int | float, int | float], int | float]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[int | float], int | float]] = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


def calculator_definition() -> ToolDefinition:
    return ToolDefinition(
        name="calculator.evaluate",
        description="Evaluate a deterministic arithmetic expression.",
        input_schema={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_EXPRESSION_LENGTH,
                    "description": "Arithmetic expression.",
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        handler_key="calculator.evaluate",
    )


def _bounded(value: object) -> int | float:
    if type(value) is int:
        if value.bit_length() > MAX_INTEGER_BITS:
            raise ValueError("Integer result is too large")
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("Only finite real numbers are accepted")


def _check_tree(tree: ast.AST) -> None:
    pending = [(tree, 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            raise ValueError("Expression complexity exceeds the calculator limit")
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return _bounded(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent magnitude is too large")
        if (
            isinstance(node.op, ast.Pow)
            and type(left) is int
            and type(right) is int
            and right > 0
            and left not in {-1, 0, 1}
            and left.bit_length() * right > MAX_INTEGER_BITS
        ):
            raise ValueError("Integer result is too large")
        return _bounded(_BINARY_OPERATORS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _bounded(_UNARY_OPERATORS[type(node.op)](_evaluate(node.operand)))
    raise ValueError("Only arithmetic expressions are accepted")


def calculate(call: ToolCall) -> ToolResult:
    expression = call.arguments.get("expression")
    try:
        if not isinstance(expression, str) or not 1 <= len(expression) <= MAX_EXPRESSION_LENGTH:
            raise ValueError("Expression must be a bounded non-empty string")
        tree = ast.parse(expression, mode="eval")
        _check_tree(tree)
        value = _evaluate(tree)
    except (ArithmeticError, SyntaxError, TypeError, ValueError, RecursionError):
        return ToolResult.failure(
            call.call_id,
            call.tool_name,
            "invalid_input",
            "Use a finite real arithmetic expression within the calculator "
            "size and complexity limits.",
        )
    return ToolResult(
        call_id=call.call_id, tool_name=call.tool_name, status="success", data={"value": value}
    )
