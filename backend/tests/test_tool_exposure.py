from __future__ import annotations

import asyncio
import json

import pytest
from conftest import ScriptedBackend, runtime

from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.registry import ToolRegistryBuilder


@pytest.mark.anyio
async def test_current_request_requires_fresh_results_not_previous_assistant_prose(store) -> None:  # type: ignore[no-untyped-def]
    reading = 0

    def read(call: ToolCall) -> ToolResult:
        nonlocal reading
        reading += 1
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"value": reading},
        )

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="test.current",
            handler_key="test.current",
            description="Current reading.",
            input_schema={"type": "object", "properties": {}},
        ),
        read,
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="old",
                        tool_name="test.current",
                        arguments={},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Previous assistant claimed 999.")),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="current",
                        tool_name="test.current",
                        arguments={},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="The current reading is 2.")),
        ]
    )
    session = store.create_session()
    chat = runtime(store, backend, builder.freeze())
    await chat.submit(session, "Read the value")
    await chat.submit(session, "What is the current value now?")

    initial, _ = backend.calls[2]
    synthesis, _ = backend.calls[3]
    assert not any(message.role == "tool" for message in initial)
    assert any(message.role == "assistant" and "999" in message.content for message in initial)
    assert "Prior assistant prose is not evidence" in initial[0].content
    assert "If no relevant evidence was refreshed" in initial[0].content
    evidence = [json.loads(message.content) for message in synthesis if message.role == "tool"]
    assert len(evidence) == 1
    assert evidence[0]["call_id"] == "current"
    assert evidence[0]["data"] == {"value": 2}
    assert evidence[0]["_orion_provenance"]["current_request"] is True
    assert len(backend.calls) == 4
    for messages, definitions in backend.calls:
        assert messages[0].role == "system"
        assert sum(message.role == "system" for message in messages) == 1
        assert definitions == builder.freeze().model_definitions()


def _registry():  # type: ignore[no-untyped-def]
    builder = ToolRegistryBuilder()
    for name in ("fake.cpu", "fake.ram", "fake.disk", "fake.load"):
        builder.register(
            ToolDefinition(
                name=name,
                description=f"Read {name}.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler_key=name,
            ),
            lambda call, name=name: ToolResult(
                call_id=call.call_id,
                tool_name=name,
                status="success",
                data={"target_ref": "host", "value": name},
            ),
        )
    return builder.freeze()


@pytest.mark.anyio
async def test_all_registered_tools_are_available_on_the_first_model_turn(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Done."))])
    session_id = store.create_session()

    await runtime(store, backend, _registry()).submit(session_id, "Explain TCP vs UDP")

    assert len(backend.calls) == 1
    assert [tool.name for tool in backend.calls[0][1]] == [
        "fake.cpu",
        "fake.disk",
        "fake.load",
        "fake.ram",
    ]


@pytest.mark.anyio
async def test_independent_reads_share_one_tool_round_trip(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=tuple(
                    ModelToolCall(call_id=name, tool_name=f"fake.{name}", arguments={})
                    for name in ("cpu", "ram", "disk", "load")
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="All readings collected.")),
        ]
    )
    session_id = store.create_session()

    await runtime(store, backend, _registry()).submit(session_id, "CPU RAM disk and load")

    assert len(backend.calls) == 2
    tool_names = [
        item.tool_name for item in store.timeline(session_id) if item.kind == "tool_result"
    ]
    assert tool_names == ["fake.cpu", "fake.ram", "fake.disk", "fake.load"]


@pytest.mark.anyio
async def test_read_only_handlers_are_dispatched_concurrently(store) -> None:  # type: ignore[no-untyped-def]
    started = asyncio.Event()
    release = asyncio.Event()
    active = 0
    peak = 0

    async def handler(call: ToolCall) -> ToolResult:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started.set()
        await release.wait()
        active -= 1
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success", data={})

    builder = ToolRegistryBuilder()
    for name in ("fake.one", "fake.two"):
        builder.register(
            ToolDefinition(
                name=name,
                description=name,
                input_schema={"type": "object"},
                handler_key=name,
            ),
            handler,
        )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="one", tool_name="fake.one", arguments={}),
                    ModelToolCall(call_id="two", tool_name="fake.two", arguments={}),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="done")),
        ]
    )
    session_id = store.create_session()
    task = asyncio.create_task(runtime(store, backend, builder.freeze()).submit(session_id, "read"))
    await started.wait()
    await asyncio.sleep(0)
    release.set()
    await task

    assert peak == 2
