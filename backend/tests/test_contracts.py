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
    citation_source_ref_ids_from_content,
    strip_source_citation_markers,
)


@pytest.mark.parametrize(
    "marker",
    (
        "[[source:abc]]",
        "[[source: abc]]",
        "[[source:abc ]]",
        "[[source: abc ]]",
    ),
)
def test_citation_marker_parser_and_stripper_share_the_same_syntax(marker: str) -> None:
    content = f"Evidence {marker} remains prose."

    assert citation_source_ref_ids_from_content(content) == ("abc",)
    assert strip_source_citation_markers(content) == "Evidence  remains prose."


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
    scope = RuntimeScope(session_id="session-1", principal_id="local", workspace_id="local")
    assert scope.project_id is None


def test_provider_schema_projection_is_deterministic_and_does_not_alias_canonical_schema() -> None:
    definition = ToolDefinition(
        name="document.edit",
        description="Apply a structured document edit.",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"const": "replace"},
                                "text": {"type": "string", "minLength": 1},
                            },
                            "required": ["kind", "text"],
                            "additionalProperties": False,
                        }
                    ]
                },
                "at": {"type": "string", "format": "date-time", "pattern": "secret"},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
        handler_key="internal.document.edit",
        operation_kind="mutation",
    )

    first = definition.provider_schema()
    second = definition.provider_schema()

    assert first == second
    parameters = first["function"]["parameters"]
    assert parameters == {
        "type": "object",
        "properties": {
            "operation": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {
                            "kind": {"const": "replace"},
                            "text": {"type": "string"},
                        },
                        "required": ["kind", "text"],
                        "additionalProperties": False,
                    }
                ]
            },
            "at": {"type": "string", "format": "date-time"},
        },
        "required": ["operation"],
        "additionalProperties": False,
    }
    parameters["properties"]["operation"]["oneOf"][0]["properties"]["kind"]["const"] = "bad"
    assert (
        definition.input_schema["properties"]["operation"]["oneOf"][0]["properties"]["kind"][
            "const"
        ]
        == "replace"
    )
    assert definition.input_schema["additionalProperties"] is False
    assert definition.operation_kind == "mutation"


def test_provider_schema_projection_keeps_bounds_and_closed_objects() -> None:
    definition = ToolDefinition(
        name="test.generic",
        description="Exercise the generic provider schema projection.",
        input_schema={
            "type": "object",
            "properties": {
                "range": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 5,
                },
                "groups": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {
                                "type": "integer",
                                "minimum": 2,
                                "maximum": 4,
                                "default": 3,
                            }
                        ]
                    },
                },
            },
            "required": ["range"],
            "additionalProperties": False,
        },
        handler_key="test.generic",
    )

    parameters = definition.provider_schema()["function"]["parameters"]

    assert parameters == {
        "type": "object",
        "properties": {
            "range": {"type": "integer", "minimum": 1, "maximum": 8},
            "groups": {
                "type": "array",
                "items": {"oneOf": [{"type": "integer", "minimum": 2, "maximum": 4}]},
            },
        },
        "required": ["range"],
        "additionalProperties": False,
    }
    assert definition.input_schema["properties"]["range"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 8,
        "default": 5,
    }


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
