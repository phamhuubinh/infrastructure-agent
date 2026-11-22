"""Request-local, model-selected capability loading from the canonical registry."""

from __future__ import annotations

from collections.abc import Callable

from orion.contracts import RuntimeScope, ToolCall, ToolDefinition, ToolResult

ENABLE_NAME = "tools.enable"


def capability(name: str) -> str:
    return {
        "system": "commands",
        "endpoint": "remote_control",
        "skill": "skills",
    }.get(name.split(".")[0], name.split(".")[0])


class LazyToolExposure:
    def __init__(self, available: Callable[[RuntimeScope], tuple[ToolDefinition, ...]]) -> None:
        self.available = available
        self.enabled: dict[str, set[str]] = {}
        self.definition = ToolDefinition(
            name=ENABLE_NAME,
            handler_key=ENABLE_NAME,
            description="Enable tool capabilities needed for this request, then use their schemas.",
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "maxItems": 12,
                        "uniqueItems": True,
                    }
                },
                "required": ["capabilities"],
            },
        )

    def context(self, scope: RuntimeScope) -> str:
        groups = sorted(
            {capability(t.name) for t in self.available(scope) if t.name != ENABLE_NAME}
        )
        return (
            "For conversation and general explanations, answer directly. For facts requiring "
            "tools, "
            "enable the relevant capabilities using tools.enable, then call the exposed tools. "
            "Enable all capabilities needed for dependent steps together when known. "
            "commands runs PowerShell/cmd/sh; knowledge reads Orion documents/Projects; "
            "remote_control operates paired Workers; calculator does exact arithmetic; "
            "internet retrieves web evidence; skills loads operator guidance; scheduler "
            "manages jobs. "
            "Loading schemas grants no permission and produces no factual evidence. Available: "
            + ", ".join(groups)
        )

    def definitions(self, request_id: str, scope: RuntimeScope) -> tuple[ToolDefinition, ...]:
        enabled = self.enabled.get(request_id, set())
        return (
            self.definition,
            *(
                t
                for t in self.available(scope)
                if t.name != ENABLE_NAME and capability(t.name) in enabled
            ),
        )

    def enable(self, call: ToolCall) -> ToolResult:
        groups = {
            capability(t.name) for t in self.available(call.runtime_scope) if t.name != ENABLE_NAME
        }
        requested = set(call.arguments["capabilities"])
        if not call.request_id or not requested <= groups:
            return ToolResult.failure(
                call.call_id,
                call.tool_name,
                "invalid_input",
                "Choose available capability names from the system catalog.",
                model_recovery_required=True,
            )
        enabled = self.enabled.setdefault(call.request_id, set())
        if requested <= enabled:
            return ToolResult.failure(
                call.call_id,
                call.tool_name,
                "already_enabled",
                "These schemas are already visible. Use their tools directly.",
                model_recovery_required=True,
            )
        enabled.update(requested)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"enabled_capabilities": sorted(enabled)},
            model_continuation_required=True,
        )

    def end_request(self, request_id: str) -> None:
        self.enabled.pop(request_id, None)
