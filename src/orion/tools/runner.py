"""Validation, application-owned scope attachment, and canonical dispatch."""

from __future__ import annotations

from pydantic import ValidationError

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
        if not self._registry.arguments_are_valid(model_call.tool_name, model_call.arguments):
            return ToolResult.failure(
                model_call.call_id,
                model_call.tool_name,
                "invalid_input",
                "Tool arguments do not match the registered input schema.",
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
            raw_result = handler(call)
        except Exception:
            return ToolResult.failure(
                model_call.call_id, model_call.tool_name, "upstream_error", "Tool execution failed."
            )
        try:
            result = ToolResult.model_validate(raw_result)
        except ValidationError:
            return ToolResult.failure(
                model_call.call_id,
                model_call.tool_name,
                "upstream_error",
                "Tool returned an invalid result.",
            )
        if result.call_id != call.call_id or result.tool_name != call.tool_name:
            return ToolResult.failure(
                model_call.call_id,
                model_call.tool_name,
                "upstream_error",
                "Tool returned mismatched correlation metadata.",
            )
        return result
