from __future__ import annotations

import asyncio
import json

import pytest
from conftest import ScriptedBackend

from orion.access import LocalAccessAdapter
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime, RequestCancelled
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, ToolDefinition, ToolResult
from orion.tool_runtime.registry import ToolRegistryBuilder


def _runtime(store, backend, sink):  # type: ignore[no-untyped-def]
    definition = ToolDefinition(
        name="test.read",
        handler_key="test.read",
        description="Read test data.",
        input_schema={"type": "object", "properties": {}},
    )
    registry = ToolRegistryBuilder()
    registry.register(
        definition,
        lambda call: ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"credential": "ORION_TEST_SECRET_TOKEN", "payload": "x" * 80},
        ),
    )
    return ChatRuntime(
        store, backend, registry.freeze(), LocalAccessAdapter(), diagnostic_sink=sink
    )


@pytest.mark.anyio
async def test_opt_in_diagnostics_record_exact_model_projection_and_phase_data(store) -> None:  # type: ignore[no-untyped-def]
    sink = BoundedModelInputDiagnostics(text_limit=120, canonical_result_limit=120)
    backend = ScriptedBackend(
        [
            ModelTurn(
                assistant=AssistantMessage(content=""),
                tool_calls=(
                    ModelToolCall(
                        call_id="expand-1",
                        tool_name="orion.tools.expand",
                        arguments={"tool_names": ["test.read"]},
                    ),
                ),
            ),
            ModelTurn(
                assistant=AssistantMessage(content=""),
                tool_calls=(ModelToolCall(call_id="read-1", tool_name="test.read", arguments={}),),
            ),
            ModelTurn(assistant=AssistantMessage(content="Done.")),
        ]
    )
    session_id = store.create_session()

    outcome = await _runtime(store, backend, sink).submit(session_id, "Read it")

    capture = sink.records(outcome.request_id)
    records = capture["records"]
    assert isinstance(records, list)
    model_inputs = [record["model_input"] for record in records if "model_input" in record]
    assert len(model_inputs) == 3
    assert all("system" not in json.dumps(value).lower() for value in model_inputs)
    second = model_inputs[1]
    assert second["exposed_tool_names"] == ["orion.tools.expand", "test.read"]
    projection = model_inputs[-1]["tool_result_projections"][-1]
    assert projection["tool_name"] == "test.read"
    assert projection["content_truncated"] is True
    assert "ORION_TEST_SECRET_TOKEN" not in json.dumps(capture)
    assert "[REDACTED]" in projection["content"]
    phases = [(record["phase"], record["status"]) for record in records]
    assert ("model", "started") in phases
    assert ("model", "completed") in phases
    assert ("tool", "started") in phases
    assert ("tool", "completed") in phases
    assert all(isinstance(record["elapsed_ms"], int) for record in records)


class _HangingBackend:
    async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
        if False:
            yield None
        await cancellation.wait()
        raise asyncio.CancelledError


@pytest.mark.anyio
async def test_cancelled_model_turn_keeps_running_phase_and_termination(store) -> None:  # type: ignore[no-untyped-def]
    sink = BoundedModelInputDiagnostics()
    runtime = _runtime(store, _HangingBackend(), sink)
    session_id = store.create_session()
    request_id = runtime.begin(session_id, "Wait")
    task = asyncio.create_task(runtime.run(session_id, request_id))
    for _ in range(20):
        if sink.records(request_id)["records"]:
            break
        await asyncio.sleep(0)
    assert sink.records(request_id)["records"]
    assert runtime.cancel(request_id) is True
    with pytest.raises(RequestCancelled):
        await task

    records = sink.records(request_id)["records"]
    assert any(record["phase"] == "model" and record["status"] == "started" for record in records)
    assert any(record["phase"] == "model" and record["status"] == "cancelled" for record in records)


class _BrokenSink:
    def record(self, record):  # type: ignore[no-untyped-def]
        raise RuntimeError("diagnostic sink failed")


@pytest.mark.anyio
async def test_sink_failure_does_not_change_request_outcome(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Done."))])
    session_id = store.create_session()

    outcome = await _runtime(store, backend, _BrokenSink()).submit(session_id, "Hello")

    assert outcome.assistant_content == "Done."
