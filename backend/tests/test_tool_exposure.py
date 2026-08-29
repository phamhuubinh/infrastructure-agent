from __future__ import annotations

import json

import pytest
from conftest import ScriptedBackend, runtime

from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    RuntimeScope,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistry, ToolRegistryBuilder


def _definition(name: str, handler_key: str | None = None) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Use {name} for its registered operation.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string", "minLength": 1}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler_key=handler_key or f"internal.{name}",
    )


def _registry(
    names: tuple[str, ...] = ("fake.alpha", "fake.beta"),
    calls: list[ToolCall] | None = None,
) -> ToolRegistry:
    builder = ToolRegistryBuilder()

    def handler(call: ToolCall) -> ToolResult:
        if calls is not None:
            calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"value": call.arguments["value"]},
        )

    for name in names:
        builder.register(_definition(name), handler)
    return builder.freeze()


def _expand(*names: str, call_id: str = "expand") -> ModelTurn:
    return ModelTurn(
        tool_calls=(
            ModelToolCall(
                call_id=call_id,
                tool_name=EXPAND_TOOL_NAME,
                arguments={"tool_names": list(names)},
            ),
        )
    )


def test_catalog_is_deterministic_sanitized_and_derived_from_the_registry() -> None:
    registry = _registry(("fake.beta", "fake.alpha", "fake.newly_registered"))

    first, second = registry.new_tool_exposure(), registry.new_tool_exposure()

    assert first.catalog == second.catalog
    assert first.catalog.splitlines() == [
        (
            "Tools (expand exact ordinary names with orion.tools.expand before execution; "
            "expansion is additive and repeatable):"
        ),
        "fake.alpha",
        "fake.beta",
        "fake.newly_registered",
    ]
    assert "Use fake.alpha for its registered operation." not in first.catalog
    assert "Use fake.beta for its registered operation." not in first.catalog
    assert [definition.name for definition in first.model_tools] == [EXPAND_TOOL_NAME]
    with pytest.raises(TypeError, match="frozen JSON snapshot"):
        first.model_tools[0].input_schema["properties"]["corruption"] = {"type": "string"}
    model_visible = json.dumps(
        {"catalog": first.catalog, "tools": [item.provider_schema() for item in first.model_tools]}
    )
    for internal_field in ("handler_key", "credential_ref", "api_key", "runtime_scope"):
        assert internal_field not in model_visible


def test_expanded_tool_keeps_its_provider_description_and_schema() -> None:
    exposure = _registry().new_tool_exposure()

    assert exposure.model_tools[0].description == (
        "Expand exact ordinary catalog names before execution. "
        "Expansion is additive and may be repeated."
    )

    exposure.expand(
        ModelToolCall(
            call_id="expand",
            tool_name=EXPAND_TOOL_NAME,
            arguments={"tool_names": ["fake.alpha"]},
        )
    )

    expanded = exposure.model_tools[1].provider_schema()["function"]
    assert expanded["name"] == "fake.alpha"
    assert expanded["description"] == "Use fake.alpha for its registered operation."
    assert expanded["parameters"] == {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }


def test_expansion_is_generic_additive_and_accepts_multiple_exact_names() -> None:
    exposure = _registry().new_tool_exposure()

    first = exposure.expand(
        ModelToolCall(
            call_id="one",
            tool_name=EXPAND_TOOL_NAME,
            arguments={"tool_names": ["fake.alpha"]},
        )
    )
    second = exposure.expand(
        ModelToolCall(
            call_id="two",
            tool_name=EXPAND_TOOL_NAME,
            arguments={"tool_names": ["fake.beta", "fake.alpha"]},
        )
    )

    assert first.data == {"exposed_tools": ["fake.alpha"]}
    assert second.data == {"exposed_tools": ["fake.alpha", "fake.beta"]}
    assert exposure.exposed_names == frozenset({"fake.alpha", "fake.beta"})
    assert [definition.name for definition in exposure.model_tools] == [
        EXPAND_TOOL_NAME,
        "fake.alpha",
        "fake.beta",
    ]


def test_invalid_expansion_names_or_arguments_do_not_expose_anything() -> None:
    exposure = _registry().new_tool_exposure()

    invalid_name = exposure.expand(
        ModelToolCall(
            call_id="unknown",
            tool_name=EXPAND_TOOL_NAME,
            arguments={"tool_names": ["fake.alpha", "missing.tool"]},
        )
    )
    invalid_arguments = exposure.expand(
        ModelToolCall(
            call_id="extra",
            tool_name=EXPAND_TOOL_NAME,
            arguments={"tool_names": ["fake.alpha"], "extra": True},
        )
    )

    assert invalid_name.error is not None and invalid_name.error.code == "invalid_input"
    assert invalid_arguments.error is not None and invalid_arguments.error.code == "invalid_input"
    assert exposure.exposed_names == frozenset()
    assert [definition.name for definition in exposure.model_tools] == [EXPAND_TOOL_NAME]


@pytest.mark.anyio
async def test_expanded_tool_uses_existing_runner_scope_and_result_loop(store) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    backend = ScriptedBackend(
        [
            _expand("fake.alpha"),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="actual", tool_name="fake.alpha", arguments={"value": "ok"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Done.")),
        ]
    )
    session_id = store.create_session()

    await runtime(store, backend, _registry(calls=calls)).submit(session_id, "Use the fake tool")

    assert len(calls) == 1
    assert calls[0].runtime_scope == RuntimeScope(
        session_id=session_id, principal_id="local", workspace_id="local"
    )
    assert len(backend.calls) == 3
    assert [definition.name for definition in backend.calls[0][1]] == [EXPAND_TOOL_NAME]
    assert [definition.name for definition in backend.calls[1][1]] == [
        EXPAND_TOOL_NAME,
        "fake.alpha",
    ]
    assert [definition.name for definition in backend.calls[2][1]] == [
        EXPAND_TOOL_NAME,
        "fake.alpha",
    ]
    result = next(
        item.payload["result"]
        for item in store.timeline(session_id)
        if item.kind == "tool_result" and item.tool_name == "fake.alpha"
    )
    assert result["data"] == {"value": "ok"}


@pytest.mark.anyio
async def test_one_expansion_can_expose_multiple_plausible_tools_without_routing(store) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    backend = ScriptedBackend(
        [
            _expand("fake.alpha", "fake.beta"),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="alpha", tool_name="fake.alpha", arguments={"value": "cpu"}
                    ),
                    ModelToolCall(
                        call_id="beta", tool_name="fake.beta", arguments={"value": "monitor"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Compared both sources.")),
        ]
    )
    session_id = store.create_session()

    await runtime(store, backend, _registry(calls=calls)).submit(
        session_id, "check CPU server monitor"
    )

    assert [definition.name for definition in backend.calls[1][1]] == [
        EXPAND_TOOL_NAME,
        "fake.alpha",
        "fake.beta",
    ]
    assert [call.tool_name for call in calls] == ["fake.alpha", "fake.beta"]
    assert len(backend.calls) == 3


@pytest.mark.anyio
async def test_hidden_or_invalid_ordinary_tool_never_dispatches(store) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="hidden", tool_name="fake.alpha", arguments={"value": "ok"}
                    ),
                )
            ),
            _expand("fake.alpha"),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="invalid",
                        tool_name="fake.alpha",
                        arguments={"value": "ok", "extra": True},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Recovered.")),
        ]
    )
    session_id = store.create_session()

    await runtime(store, backend, _registry(calls=calls)).submit(session_id, "Try the tool")

    assert calls == []
    results = [
        item.payload["result"]
        for item in store.timeline(session_id)
        if item.kind == "tool_result" and item.tool_name == "fake.alpha"
    ]
    assert [result["error"]["code"] for result in results] == ["not_exposed", "invalid_input"]
    assert results[0]["error"]["message"] == (
        "Tool is not exposed. Call orion.tools.expand with this exact catalog name, then retry."
    )


@pytest.mark.anyio
async def test_exposure_is_additive_within_a_request_and_resets_for_the_next_one(store) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    backend = ScriptedBackend(
        [
            _expand("fake.alpha"),
            _expand("fake.beta"),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="beta", tool_name="fake.beta", arguments={"value": "monitor"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="First done.")),
            ModelTurn(assistant=AssistantMessage(content="Second direct answer.")),
        ]
    )
    chat = runtime(store, backend, _registry(calls=calls))
    session_id = store.create_session()

    await chat.submit(session_id, "check CPU server monitor")
    await chat.submit(session_id, "unrelated question")

    assert [definition.name for definition in backend.calls[1][1]] == [
        EXPAND_TOOL_NAME,
        "fake.alpha",
    ]
    assert [definition.name for definition in backend.calls[2][1]] == [
        EXPAND_TOOL_NAME,
        "fake.alpha",
        "fake.beta",
    ]
    assert [definition.name for definition in backend.calls[3][1]] == [
        EXPAND_TOOL_NAME,
        "fake.alpha",
        "fake.beta",
    ]
    assert [definition.name for definition in backend.calls[4][1]] == [EXPAND_TOOL_NAME]
    assert [call.tool_name for call in calls] == ["fake.beta"]
