"""Validation, application-owned scope attachment, and canonical dispatch."""

from __future__ import annotations

import inspect
from collections.abc import Callable

from pydantic import ValidationError

from orion.contracts import ModelToolCall, RuntimeScope, ToolCall, ToolResult
from orion.security import redact_public
from orion.tool_runtime.registry import ToolHandler, ToolRegistry


class ToolRunner:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def run(
        self,
        model_call: ModelToolCall,
        scope: RuntimeScope,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> ToolResult:
        prepared = self._prepare(model_call, scope, cancellation_requested)
        if isinstance(prepared, ToolResult):
            return prepared
        handler, call = prepared
        try:
            raw_result = handler(call)
        except Exception:
            return ToolResult.failure(
                call.call_id, call.tool_name, "upstream_error", "Tool execution failed."
            )
        if inspect.isawaitable(raw_result):
            if inspect.iscoroutine(raw_result):
                raw_result.close()
            return ToolResult.failure(
                call.call_id, call.tool_name, "unavailable", "Tool requires async dispatch."
            )
        return self._normalise(call, raw_result)

    async def run_async(
        self,
        model_call: ModelToolCall,
        scope: RuntimeScope,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> ToolResult:
        prepared = self._prepare(model_call, scope, cancellation_requested)
        if isinstance(prepared, ToolResult):
            return prepared
        handler, call = prepared
        try:
            raw_result = handler(call)
            if inspect.isawaitable(raw_result):
                raw_result = await raw_result
        except Exception:
            return ToolResult.failure(
                call.call_id, call.tool_name, "upstream_error", "Tool execution failed."
            )
        return self._normalise(call, raw_result)

    def _prepare(
        self,
        model_call: ModelToolCall,
        scope: RuntimeScope,
        cancellation_requested: Callable[[], bool] | None,
    ) -> ToolResult | tuple[ToolHandler, ToolCall]:
        definition = self._registry.definition(model_call.tool_name)
        if definition is None:
            return ToolResult.failure(
                model_call.call_id, model_call.tool_name, "not_found", "Unknown registered tool."
            )
        validation_issue = self._registry.argument_validation_issue(
            model_call.tool_name, model_call.arguments
        )
        if validation_issue is not None:
            return ToolResult.failure(
                model_call.call_id,
                model_call.tool_name,
                "invalid_input",
                "Tool arguments do not match the registered input schema. "
                f"Validation issue: {validation_issue}. "
                "Retry using only values allowed by the currently exposed schema.",
                model_recovery_required=True,
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
            cancellation_requested=cancellation_requested,
        )
        return handler, call

    def _normalise(self, call: ToolCall, raw_result: object) -> ToolResult:
        try:
            result = ToolResult.model_validate(raw_result)
        except ValidationError:
            return ToolResult.failure(
                call.call_id,
                call.tool_name,
                "upstream_error",
                "Tool returned an invalid result.",
            )
        if result.call_id != call.call_id or result.tool_name != call.tool_name:
            return ToolResult.failure(
                call.call_id,
                call.tool_name,
                "upstream_error",
                "Tool returned mismatched correlation metadata.",
            )
        return ToolResult.model_validate(redact_public(result.model_dump(mode="json")))
