from __future__ import annotations

import asyncio

import pytest
from conftest import ScriptedBackend

from orion.access import LocalAccessAdapter
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime, RequestCancelled
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.mutation_authorization import MutationAuthorizationPolicy
from orion.tool_runtime.registry import ToolRegistry, ToolRegistryBuilder


def _definition(name: str, mutation: bool = False) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        handler_key=name,
        description=name,
        operation_kind="mutation" if mutation else "read",
        input_schema={
            "type": "object",
            "properties": {"target_ref": {"type": "string"}},
            "required": ["target_ref"],
            "additionalProperties": False,
        },
    )


def _backend() -> ScriptedBackend:
    return ScriptedBackend(
        [
            ModelTurn(
                tool_calls=tuple(
                    ModelToolCall(
                        call_id=name,
                        tool_name=name,
                        arguments={"target_ref": "local"},
                    )
                    for name in ("test.first", "test.second")
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Done.")),
        ]
    )


def _success(call: ToolCall) -> ToolResult:
    return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success")


@pytest.mark.anyio
async def test_all_arguments_are_validated_before_any_handler(store, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    order: list[str] = []
    original = ToolRegistry.argument_validation_issue

    def validate(self, name, arguments):  # type: ignore[no-untyped-def]
        order.append("validate:" + name)
        return original(self, name, arguments)

    def handler(call: ToolCall) -> ToolResult:
        order.append("execute:" + call.tool_name)
        return _success(call)

    monkeypatch.setattr(ToolRegistry, "argument_validation_issue", validate)
    builder = ToolRegistryBuilder()
    for name in ("test.first", "test.second"):
        builder.register(_definition(name), handler)
    backend = _backend()
    await ChatRuntime(store, backend, builder.freeze(), LocalAccessAdapter()).submit(
        store.create_session(), "Read both"
    )
    assert order == [
        "validate:test.first",
        "validate:test.second",
        "execute:test.first",
        "execute:test.second",
    ]
    assert len(backend.calls) == 2


@pytest.mark.anyio
async def test_batch_records_individual_execution_time_and_keeps_call_ids(store) -> None:  # type: ignore[no-untyped-def]
    clock = [0.0]
    second_started = asyncio.Event()
    first_finished = asyncio.Event()

    async def handler(call: ToolCall) -> ToolResult:
        if call.tool_name == "test.first":
            await second_started.wait()
            clock[0] = 0.01
            first_finished.set()
        else:
            second_started.set()
            await first_finished.wait()
            # Let the first completion pass through the budget wrapper and persist.
            for _ in range(20):
                await asyncio.sleep(0)
            clock[0] = 0.08
        return _success(call)

    builder = ToolRegistryBuilder()
    for name in ("test.first", "test.second"):
        builder.register(_definition(name), handler)
    session = store.create_session()
    backend = _backend()
    await ChatRuntime(
        store, backend, builder.freeze(), LocalAccessAdapter(), monotonic_clock=lambda: clock[0]
    ).submit(session, "Read both")
    results = {
        item.call_id: item.payload for item in store.timeline(session) if item.kind == "tool_result"
    }
    assert results["test.first"]["elapsed_ms"] == 10
    assert results["test.second"]["elapsed_ms"] == 80
    assert {
        message.tool_call_id for message in backend.calls[1][0] if message.role == "tool"
    } == set(results)


@pytest.mark.anyio
@pytest.mark.parametrize("cancel", [False, True])
async def test_completed_mutation_survives_a_later_interrupted_read(store, cancel) -> None:  # type: ignore[no-untyped-def]
    clock = [0.0]
    cancellation = asyncio.Event()
    executed: list[str] = []

    async def handler(call: ToolCall) -> ToolResult:
        executed.append(call.tool_name)
        if call.tool_name == "test.second":
            if cancel:
                cancellation.set()
            else:
                clock[0] = 121
        return _success(call)

    builder = ToolRegistryBuilder()
    builder.register(_definition("test.first", mutation=True), handler)
    builder.register(_definition("test.second"), handler)
    session = store.create_session()
    sink = BoundedModelInputDiagnostics()
    chat = ChatRuntime(
        store,
        _backend(),
        builder.freeze(),
        LocalAccessAdapter(),
        monotonic_clock=lambda: clock[0],
        diagnostic_sink=sink,
        mutation_authorization=MutationAuthorizationPolicy(frozenset({("test.first", "local")})),
    )
    if cancel:
        with pytest.raises(RequestCancelled):
            await chat.submit(session, "Mutate then read", cancellation)
    else:
        outcome = await chat.submit(session, "Mutate then read", cancellation)
        assert outcome.status == "incomplete"
    results = {
        item.tool_name: item.payload["result"]
        for item in store.timeline(session)
        if item.kind == "tool_result"
    }
    assert executed == ["test.first", "test.second"]
    assert results["test.first"]["status"] == "success"
    assert results["test.second"]["error"]["code"] == ("cancelled" if cancel else "timeout")


@pytest.mark.anyio
async def test_normal_error_in_first_read_does_not_drop_second_read(store) -> None:  # type: ignore[no-untyped-def]
    def handler(call: ToolCall) -> ToolResult:
        if call.tool_name == "test.first":
            return ToolResult.failure(call.call_id, call.tool_name, "not_found", "Not found.")
        return _success(call)

    builder = ToolRegistryBuilder()
    for name in ("test.first", "test.second"):
        builder.register(_definition(name), handler)
    backend = _backend()
    session = store.create_session()
    await ChatRuntime(store, backend, builder.freeze(), LocalAccessAdapter()).submit(
        session, "Read both"
    )
    results = [
        item.payload["result"] for item in store.timeline(session) if item.kind == "tool_result"
    ]
    assert [result["status"] for result in results] == ["error", "success"]
    assert len(backend.calls) == 2
