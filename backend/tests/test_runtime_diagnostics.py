from __future__ import annotations

import asyncio
import json

import pytest
from conftest import ScriptedBackend

from orion.access import LocalAccessAdapter
from orion.chat.deadline import RequestBudgetSettings
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime, RequestCancelled
from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ModelUsage,
    ToolCallDelta,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.registry import ToolRegistryBuilder


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _TimedScriptedBackend:
    def __init__(self, clock: _FakeClock, streams) -> None:  # type: ignore[no-untyped-def]
        self._clock = clock
        self._streams = list(streams)

    async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
        for elapsed_seconds, event in self._streams.pop(0):
            self._clock.advance(elapsed_seconds)
            yield event


def _runtime(store, backend, sink, **kwargs):  # type: ignore[no-untyped-def]
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
        store, backend, registry.freeze(), LocalAccessAdapter(), diagnostic_sink=sink, **kwargs
    )


def _model_records(sink, request_id):  # type: ignore[no-untyped-def]
    return [record for record in sink.records(request_id)["records"] if record["phase"] == "model"]


def _completed_record(sink, request_id):  # type: ignore[no-untyped-def]
    return next(
        record for record in _model_records(sink, request_id) if record["status"] == "completed"
    )


def _stream_progress_record(sink, request_id):  # type: ignore[no-untyped-def]
    return next(
        record
        for record in _model_records(sink, request_id)
        if record["status"] == "stream_progress"
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


@pytest.mark.anyio
async def test_model_stream_diagnostics_measure_first_assistant_delta_with_monotonic_clock(
    store,
) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (0.125, AssistantDelta(content="Hello")),
                (
                    0.375,
                    ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Hello"))),
                ),
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "Hi"
    )

    record = _completed_record(sink, outcome.request_id)
    assert record["first_normalized_event_elapsed_ms"] == 125
    assert record["first_assistant_delta_elapsed_ms"] == 125
    assert record["first_tool_call_delta_elapsed_ms"] is None
    assert record["completed_elapsed_ms"] == 500
    assert record["first_normalized_event_to_completed_elapsed_ms"] == 375
    progress = _stream_progress_record(sink, outcome.request_id)
    assert progress["first_actionable_delta_kind"] == "assistant"
    assert progress["elapsed_ms"] == 125


@pytest.mark.anyio
async def test_model_stream_diagnostics_measure_first_tool_call_delta_with_monotonic_clock(
    store,
) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (0.2, ToolCallDelta(index=0, call_id="candidate", tool_name="test.read")),
                (
                    0.3,
                    ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Done."))),
                ),
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "Read"
    )

    record = _completed_record(sink, outcome.request_id)
    assert record["first_normalized_event_elapsed_ms"] == 200
    assert record["first_assistant_delta_elapsed_ms"] is None
    assert record["first_tool_call_delta_elapsed_ms"] == 200
    assert record["tool_call_delta_count"] == 1
    assert record["tool_call_count"] == 0
    assert (
        _stream_progress_record(sink, outcome.request_id)["first_actionable_delta_kind"]
        == "tool_call"
    )


@pytest.mark.anyio
async def test_model_stream_diagnostics_distinguish_both_delta_shapes_in_one_turn(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (0.1, AssistantDelta(content="Draft")),
                (0.02, ToolCallDelta(index=0, tool_name="test.read")),
                (
                    0.18,
                    ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Done."))),
                ),
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "Both"
    )

    record = _completed_record(sink, outcome.request_id)
    assert record["first_normalized_event_elapsed_ms"] == 100
    assert record["first_assistant_delta_elapsed_ms"] == 100
    assert record["first_tool_call_delta_elapsed_ms"] == 120
    assert record["assistant_delta_count"] == 1
    assert record["tool_call_delta_count"] == 1


@pytest.mark.anyio
async def test_model_stream_diagnostics_leave_delta_timings_unavailable_without_deltas(
    store,
) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (
                    0.456,
                    ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Done."))),
                )
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "No deltas"
    )

    record = _completed_record(sink, outcome.request_id)
    assert record["first_normalized_event_elapsed_ms"] == 456
    assert record["first_assistant_delta_elapsed_ms"] is None
    assert record["first_tool_call_delta_elapsed_ms"] is None
    assert record["assistant_delta_count"] == 0
    assert record["assistant_delta_characters"] == 0
    assert record["tool_call_delta_count"] == 0


@pytest.mark.anyio
async def test_model_stream_diagnostics_aggregate_multiple_deltas_without_content(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (0.1, AssistantDelta(content="hi")),
                (0.05, AssistantDelta(content="世界")),
                (0.05, ToolCallDelta(index=0, arguments_delta='{"x":')),
                (0.05, ToolCallDelta(index=0, arguments_delta='"y"}')),
                (
                    0.05,
                    ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Done."))),
                ),
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "Aggregate"
    )

    record = _completed_record(sink, outcome.request_id)
    assert record["assistant_delta_count"] == 2
    assert record["assistant_delta_characters"] == 4
    assert record["tool_call_delta_count"] == 2
    assert "hi" not in json.dumps(record)
    assert "世界" not in json.dumps(record)
    assert "arguments_delta" not in record


@pytest.mark.anyio
async def test_model_stream_diagnostics_include_provider_usage_when_available(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (
                    0.04,
                    ModelTurnCompleted(
                        turn=ModelTurn(assistant=AssistantMessage(content="Done.")),
                        usage=ModelUsage(input_tokens=31, output_tokens=7),
                    ),
                )
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "Usage"
    )

    record = _completed_record(sink, outcome.request_id)
    assert record["input_tokens"] == 31
    assert record["output_tokens"] == 7


@pytest.mark.anyio
async def test_model_stream_diagnostics_omit_usage_when_provider_does_not_supply_it(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [[(0.04, ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Done."))))]],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "No usage"
    )

    record = _completed_record(sink, outcome.request_id)
    assert "input_tokens" not in record
    assert "output_tokens" not in record


class _ProgressThenHangBackend:
    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self.delta_emitted = asyncio.Event()

    async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
        self._clock.advance(0.15)
        self.delta_emitted.set()
        yield AssistantDelta(content="partial")
        await asyncio.Event().wait()


class _BlockedBeforeFirstEventBackend:
    def __init__(self) -> None:
        self.entered = asyncio.Event()

    async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
        if False:
            yield AssistantDelta(content="unreachable")
        self.entered.set()
        await asyncio.Event().wait()


async def _wait_for_stream_progress(sink, request_id) -> None:  # type: ignore[no-untyped-def]
    for _ in range(20):
        if any(
            record["status"] == "stream_progress" for record in _model_records(sink, request_id)
        ):
            return
        await asyncio.sleep(0)
    pytest.fail("Model stream progress milestone was not recorded.")


@pytest.mark.anyio
async def test_in_flight_diagnostics_persist_first_stream_milestone_before_termination(
    store,
) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _ProgressThenHangBackend(clock)
    runtime = _runtime(store, backend, sink, monotonic_clock=clock)
    session_id = store.create_session()
    request_id = runtime.begin(session_id, "QA boundary")
    task = asyncio.create_task(runtime.run(session_id, request_id))
    await backend.delta_emitted.wait()
    await _wait_for_stream_progress(sink, request_id)

    snapshot = sink.records(request_id)
    milestone = _stream_progress_record(sink, request_id)
    assert milestone["request_id"] == request_id
    assert milestone["model_turn_id"].startswith(f"{request_id}:1:")
    assert milestone["first_actionable_delta_kind"] == "assistant"
    assert milestone["first_normalized_event_elapsed_ms"] == 150
    assert milestone["first_assistant_delta_elapsed_ms"] == 150
    assert milestone["first_tool_call_delta_elapsed_ms"] is None
    assert milestone["assistant_delta_count"] == 1
    assert milestone["assistant_delta_characters"] == len("partial")
    assert all(record["status"] != "completed" for record in snapshot["records"])
    assert not task.done()

    assert runtime.cancel(request_id) is True
    with pytest.raises(RequestCancelled):
        await task


@pytest.mark.anyio
async def test_in_flight_diagnostics_do_not_invent_stream_timing_before_a_delta(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _BlockedBeforeFirstEventBackend()
    runtime = _runtime(store, backend, sink, monotonic_clock=clock)
    session_id = store.create_session()
    request_id = runtime.begin(session_id, "No stream event yet")
    task = asyncio.create_task(runtime.run(session_id, request_id))
    await backend.entered.wait()

    snapshot = sink.records(request_id)
    model_records = _model_records(sink, request_id)
    assert [record["status"] for record in model_records] == ["started"]
    assert all("first_normalized_event_elapsed_ms" not in record for record in snapshot["records"])
    assert not task.done()

    assert runtime.cancel(request_id) is True
    with pytest.raises(RequestCancelled):
        await task


@pytest.mark.anyio
async def test_cancelled_model_turn_retains_aggregate_stream_progress(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _ProgressThenHangBackend(clock)
    runtime = _runtime(store, backend, sink, monotonic_clock=clock)
    session_id = store.create_session()
    request_id = runtime.begin(session_id, "Cancel")
    task = asyncio.create_task(runtime.run(session_id, request_id))
    await backend.delta_emitted.wait()
    await asyncio.sleep(0)

    assert runtime.cancel(request_id) is True
    with pytest.raises(RequestCancelled):
        await task

    record = next(
        record for record in _model_records(sink, request_id) if record["status"] == "cancelled"
    )
    assert record["first_normalized_event_elapsed_ms"] == 150
    assert record["first_assistant_delta_elapsed_ms"] == 150
    assert record["assistant_delta_count"] == 1
    assert record["assistant_delta_characters"] == len("partial")


@pytest.mark.anyio
async def test_timed_out_model_turn_retains_aggregate_stream_progress(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _ProgressThenHangBackend(clock)

    async def expire_after_delta(seconds: float) -> None:
        await backend.delta_emitted.wait()
        clock.advance(seconds)

    runtime = _runtime(
        store,
        backend,
        sink,
        monotonic_clock=clock,
        deadline_sleeper=expire_after_delta,
        request_budget_settings=RequestBudgetSettings(
            request_deadline_seconds=10, finalization_reserve_seconds=2
        ),
    )

    outcome = await runtime.submit(store.create_session(), "Timeout")

    assert outcome.status == "incomplete"
    record = next(
        record
        for record in _model_records(sink, outcome.request_id)
        if record["status"] == "timed_out"
    )
    assert record["first_normalized_event_elapsed_ms"] == 150
    assert record["assistant_delta_count"] == 1
    assert record["elapsed_ms"] == 8150


@pytest.mark.anyio
async def test_model_stream_diagnostics_exclude_stream_and_request_secrets(store) -> None:  # type: ignore[no-untyped-def]
    active = store.active_model_config()
    assert active is not None
    assert store.update_model_config(
        str(active["model_config_id"]),
        "openai_compatible",
        "http://model.test/v1",
        "fake",
        "API_KEY_SECRET",
    )
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (0.1, AssistantDelta(content="ASSISTANT_CONTENT_SECRET")),
                (
                    0.1,
                    ToolCallDelta(
                        index=0, arguments_delta="TOOL_ARGUMENT_SECRET <think>REASONING_SECRET"
                    ),
                ),
                (
                    0.1,
                    ModelTurnCompleted(
                        turn=ModelTurn(assistant=AssistantMessage(content="FINAL_ASSISTANT_SECRET"))
                    ),
                ),
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "PROMPT_SECRET raw SSE: data: RAW_SSE_SECRET"
    )

    persisted = json.dumps(sink.records(outcome.request_id))
    for secret in (
        "ASSISTANT_CONTENT_SECRET",
        "TOOL_ARGUMENT_SECRET",
        "PROMPT_SECRET",
        "API_KEY_SECRET",
        "REASONING_SECRET",
        "RAW_SSE_SECRET",
    ):
        assert secret not in persisted


@pytest.mark.anyio
async def test_model_stream_diagnostics_keep_record_cardinality_bounded(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics(records_limit=3)
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                *[(0.001, AssistantDelta(content="x")) for _ in range(40)],
                *[(0.001, ToolCallDelta(index=0, arguments_delta="x")) for _ in range(40)],
                (
                    0.001,
                    ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Done."))),
                ),
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "Bounded"
    )

    capture = sink.records(outcome.request_id)
    assert len(capture["records"]) == 3
    assert capture["records_truncated"] is False
    record = _completed_record(sink, outcome.request_id)
    assert record["assistant_delta_count"] == 40
    assert record["tool_call_delta_count"] == 40
