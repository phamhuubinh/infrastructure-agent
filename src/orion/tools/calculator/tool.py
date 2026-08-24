"""A deterministic, scope-independent first real Orion tool."""

from __future__ import annotations

import ast
from collections.abc import Callable

from orion.contracts import ToolCall, ToolDefinition, ToolResult

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
                "expression": {"type": "string", "description": "Arithmetic expression."}
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        handler_key="calculator.evaluate",
    )


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent magnitude is too large")
        return _BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("Only arithmetic expressions are accepted")


def calculate(call: ToolCall) -> ToolResult:
    expression = call.arguments["expression"]
    assert isinstance(expression, str)
    try:
        value = _evaluate(ast.parse(expression, mode="eval"))
    except (ArithmeticError, SyntaxError, TypeError, ValueError) as error:
        return ToolResult.failure(call.call_id, call.tool_name, "invalid_input", str(error))
    return ToolResult(
        call_id=call.call_id, tool_name=call.tool_name, status="success", data={"value": value}
    )
