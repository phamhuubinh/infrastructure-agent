from __future__ import annotations

import pytest
from pydantic import ValidationError

from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    RuntimeScope,
    ToolDefinition,
    ToolError,
    ToolResult,
)


def test_contracts_serialize_and_hide_handler_binding_from_provider() -> None:
    definition = ToolDefinition(
        name="calculator.evaluate",
        description="Calculate arithmetic.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler_key="internal.calculator",
    )
    provider_schema = definition.provider_schema()

    assert "handler_key" not in provider_schema
    assert provider_schema["function"]["name"] == "calculator.evaluate"
    turn = ModelTurn(
        assistant=AssistantMessage(content="Calculating."),
        tool_calls=(ModelToolCall(call_id="call-1", tool_name=definition.name, arguments={}),),
    )
    assert ModelTurn.model_validate_json(turn.model_dump_json()) == turn
    assert RuntimeScope(session_id="session-1").project_id is None


def test_contract_validation_rejects_invalid_runtime_data() -> None:
    with pytest.raises(ValidationError, match="ModelTurn requires"):
        ModelTurn()
    assert ModelTurn(assistant=AssistantMessage(content="Answer.")).tool_calls == ()
    assert (
        ModelTurn(
            tool_calls=(
                ModelToolCall(call_id="call-1", tool_name="calculator.evaluate", arguments={}),
            )
        ).assistant
        is None
    )
    combined = ModelTurn(
        assistant=AssistantMessage(content="Calculating."),
        tool_calls=(
            ModelToolCall(call_id="call-2", tool_name="calculator.evaluate", arguments={}),
        ),
    )
    assert combined.assistant is not None
    assert len(combined.tool_calls) == 1
    with pytest.raises(ValidationError):
        ToolDefinition(
            name="Calculator!",
            description="bad",
            input_schema={"type": "object"},
            handler_key="handler",
        )
    with pytest.raises(ValidationError):
        ToolResult(call_id="c", tool_name="t", status="error", data=None, error=None, sources=())
    with pytest.raises(ValidationError):
        ToolResult(
            call_id="c",
            tool_name="t",
            status="success",
            data=None,
            error=ToolError(code="bad", message="bad"),
            sources=(),
        )
