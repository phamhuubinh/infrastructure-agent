from __future__ import annotations

import pytest

from orion.contracts import ModelToolCall, RuntimeScope, ToolCall, ToolDefinition
from orion.tool_runtime.registry import ToolRegistryBuilder
from orion.tool_runtime.runner import ToolRunner


def _definition(schema: dict[str, object]) -> ToolDefinition:
    return ToolDefinition(
        name="fake.structured",
        description="Validate a structured payload.",
        input_schema=schema,
        handler_key="fake.structured",
    )


def test_registry_rejects_malformed_json_schema() -> None:
    registry = ToolRegistryBuilder()
    malformed = {
        "type": "object",
        "properties": {"value": {"type": 42}},
    }

    with pytest.raises(ValueError, match="invalid JSON Schema"):
        registry.register(_definition(malformed), lambda _call: {})


def test_runner_uses_complete_json_schema_before_dispatch() -> None:
    executions = 0

    def handler(call: ToolCall) -> dict[str, object]:
        nonlocal executions
        executions += 1
        return {
            "call_id": call.call_id,
            "tool_name": call.tool_name,
            "status": "success",
            "data": {"accepted": True},
            "error": None,
            "sources": [],
        }

    registry = ToolRegistryBuilder()
    registry.register(
        _definition(
            {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "object",
                        "properties": {"mode": {"type": "string", "enum": ["safe"]}},
                        "required": ["mode"],
                        "additionalProperties": False,
                    }
                },
                "required": ["payload"],
                "additionalProperties": False,
            }
        ),
        handler,
    )
    runner = ToolRunner(registry.freeze())
    scope = RuntimeScope(session_id="session-1", principal_id="local", workspace_id="local")

    invalid = runner.run(
        ModelToolCall(
            call_id="invalid",
            tool_name="fake.structured",
            arguments={"payload": {"mode": "unsafe", "extra": True}},
        ),
        scope,
    )
    valid = runner.run(
        ModelToolCall(
            call_id="valid",
            tool_name="fake.structured",
            arguments={"payload": {"mode": "safe"}},
        ),
        scope,
    )

    assert invalid.status == "error"
    assert invalid.error is not None
    assert invalid.error.code == "invalid_input"
    assert executions == 1
    assert valid.status == "success"
    assert valid.data == {"accepted": True}


def test_runner_normalizes_invalid_handler_results() -> None:
    registry = ToolRegistryBuilder()
    registry.register(
        _definition({"type": "object", "properties": {}, "additionalProperties": False}),
        lambda _call: {"status": "success"},
    )

    result = ToolRunner(registry.freeze()).run(
        ModelToolCall(call_id="call-1", tool_name="fake.structured", arguments={}),
        RuntimeScope(session_id="session-1", principal_id="local", workspace_id="local"),
    )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "upstream_error"
