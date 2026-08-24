"""Validation, application-owned scope attachment, and canonical dispatch."""

from __future__ import annotations

from typing import Any

from orion.contracts import ModelToolCall, RuntimeScope, ToolCall, ToolResult
from orion.tools.registry import ToolRegistry


class ToolRunner:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def run(self, model_call: ModelToolCall, scope: RuntimeScope) -> ToolResult:
        definition = self._registry.definition(model_call.tool_name)
        if definition is None:
            return ToolResult.failure(
                model_call.call_id, model_call.tool_name, "not_found", "Unknown registered tool."
            )
        error = self._validate(model_call.arguments, definition.input_schema)
        if error is not None:
            return ToolResult.failure(
                model_call.call_id, model_call.tool_name, "invalid_input", error
            )
        handler = self._registry.handler(definition.handler_key)
        if handler is None:
            return ToolResult.failure(
                model_call.call_id,
                model_call.tool_name,
                "unavailable",
                "Tool handler is unavailable.",
            )
        call = ToolCall(
            call_id=model_call.call_id,
            tool_name=model_call.tool_name,
            arguments=model_call.arguments,
            runtime_scope=scope,
        )
        try:
            result = handler(call)
        except Exception:
            return ToolResult.failure(
                model_call.call_id, model_call.tool_name, "upstream_error", "Tool execution failed."
            )
        if result.call_id != call.call_id or result.tool_name != call.tool_name:
            return ToolResult.failure(
                model_call.call_id,
                model_call.tool_name,
                "upstream_error",
                "Tool returned mismatched correlation metadata.",
            )
        return result

    def _validate(self, arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not isinstance(arguments, dict):
            return "Tool arguments must be an object."
        for key in required:
            if key not in arguments:
                return f"Missing required argument: {key}."
        if schema.get("additionalProperties") is False:
            unexpected = set(arguments) - set(properties)
            if unexpected:
                return f"Unexpected argument: {sorted(unexpected)[0]}."
        for key, value in arguments.items():
            declaration = properties.get(key)
            if not isinstance(declaration, dict):
                continue
            expected = declaration.get("type")
            if expected == "string" and not isinstance(value, str):
                return f"Argument {key} must be a string."
            if expected == "number" and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
            ):
                return f"Argument {key} must be a number."
            if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                return f"Argument {key} must be an integer."
        return None
