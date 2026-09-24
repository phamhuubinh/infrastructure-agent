from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from conftest import ScriptedBackend
from test_qa_runner import qa_runner as qa_runner

from orion.access import LocalAccessAdapter
from orion.chat.context_builder import MAX_CONVERSATION_BYTES, _messages_bytes
from orion.chat.deadline import RequestBudgetSettings
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime, RequestCancelled, RequestFailed
from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ModelUsage,
    ReasoningDelta,
    SourceRef,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.registry import ToolRegistryBuilder


@pytest.mark.anyio
@pytest.mark.parametrize("correction_succeeds", [True, False])
async def test_citation_allowlist_and_rejection_ids_are_recorded_without_draft_content(
    store, correction_succeeds
) -> None:  # type: ignore[no-untyped-def]
    allowed = "5b30120f-f311-5b1f-a6a4-7076537e9e65"
    invented = "77777777-f311-5b1f-a6a4-7076537e9e65"
    source = SourceRef(source_ref_id=allowed, source_kind="grafana", source_id="grafana")
    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="grafana.alert.list",
            handler_key="grafana.alert.list",
            description="List alerts.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        lambda call: ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"alerts": [{"name": "Example alert"}]},
            sources=(source,),
        ),
    )
    rejected_text = "REJECTED_DRAFT_TEXT_SHOULD_NOT_BE_LOGGED"
    final_id = allowed if correction_succeeds else invented
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="alerts", tool_name="grafana.alert.list", arguments={}),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content=f"{rejected_text} [[source:{invented}]]",
                    citation_source_ref_ids=(invented,),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content=f"Example alert. [[source:{final_id}]]",
                    citation_source_ref_ids=(final_id,),
                )
            ),
        ]
    )
    sink = BoundedModelInputDiagnostics()
    session = store.create_session()
    chat = ChatRuntime(store, backend, builder.freeze(), LocalAccessAdapter(), diagnostic_sink=sink)
    prompt = "List alerts and cite the source."
    request_id = chat.begin(session, prompt)
    if correction_succeeds:
        outcome = await chat.run(session, request_id)
        assert outcome.assistant_content == f"Example alert. [[source:{allowed}]]"
    else:
        with pytest.raises(RequestFailed, match="unavailable source"):
            await chat.run(session, request_id)

    assert len(backend.calls) == 3
    messages, tools = backend.calls[-1]
    assert [m.role for m in messages[-2:]] == ["assistant", "user"]
    correction = messages[-1].content
    allowlist = json.loads(
        correction.split("Allowed evidence_ref aliases:\n", 1)[1].splitlines()[0]
    )
    assert allowlist == ["S1"]
    assert allowed not in correction
    assert "Do not use source_id, target_ref, document_id" in correction
    assert tools == builder.freeze().model_definitions()
    timeline = store.timeline(session)
    assert [item.payload["content"] for item in timeline if item.kind == "user_message"] == [prompt]
    assistants = [
        item for item in timeline if item.kind == "assistant_message" and item.payload["content"]
    ]
    assert len(assistants) == (1 if correction_succeeds else 0)

    captured = sink.records(request_id)
    rejected = [r for r in captured["records"] if r.get("stage") == "citation_validation"]
    assert len(rejected) == (1 if correction_succeeds else 2)
    for index, record in enumerate(rejected):
        assert record["request_id"] == request_id
        assert record["model_turn_id"]
        assert record["error_kind"] == "unavailable_source"
        assert record["attempted_source_ref_ids"] == [invented]
        assert record["visible_source_ref_ids"] == [allowed]
        assert record["citation_correction_attempted"] is (index == 1)
    assert rejected_text not in json.dumps(captured)
    if not correction_succeeds:
        notice = next(item.payload for item in timeline if item.kind == "runtime_notice")
        assert notice["attempted_source_ref_ids"] == [invented]
        assert notice["visible_source_ref_ids"] == [allowed]
        assert notice["citation_correction_attempted"] is True


@pytest.mark.anyio
async def test_real_tool_elapsed_time_reaches_qa_totals(store, qa_runner) -> None:  # type: ignore[no-untyped-def]
    async def read(call: ToolCall) -> ToolResult:
        await asyncio.sleep(0.02)
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success")

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="test.timed_read",
            handler_key="test.timed_read",
            description="Timed read.",
            input_schema={"type": "object", "properties": {}},
        ),
        read,
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="read",
                        tool_name="test.timed_read",
                        arguments={},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Done.")),
        ]
    )
    sink = BoundedModelInputDiagnostics()
    session = store.create_session()
    outcome = await ChatRuntime(
        store,
        backend,
        builder.freeze(),
        LocalAccessAdapter(),
        diagnostic_sink=sink,
    ).submit(session, "Read once")
    timeline = [item.model_dump(mode="json") for item in store.timeline(session)]

    timing = qa_runner.behavioral_timing(
        timeline,
        [{"capture": sink.records(outcome.request_id)}],
        100,
    )

    assert timing["model_attempt_count"] == timing["model_completed_count"] == 2
    assert timing["tool_elapsed_ms_observed_count"] == 1
    elapsed = next(
        item["payload"]["elapsed_ms"] for item in timeline if item["kind"] == "tool_result"
    )
    assert timing["tool_elapsed_ms_total"] == elapsed
    assert elapsed >= 15


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


def _stream_progress_records(sink, request_id):  # type: ignore[no-untyped-def]
    return [
        record
        for record in _model_records(sink, request_id)
        if record["status"] == "stream_progress"
    ]


@pytest.mark.anyio
async def test_opt_in_diagnostics_record_exact_model_projection_and_phase_data(store) -> None:  # type: ignore[no-untyped-def]
    sink = BoundedModelInputDiagnostics(text_limit=120, canonical_result_limit=120)
    backend = ScriptedBackend(
        [
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
    assert len(model_inputs) == 2
    assert all("system" not in json.dumps(value).lower() for value in model_inputs)
    second = model_inputs[1]
    assert second["tool_names"] == ["test.read"]
    assert second["tool_schema_bytes"] > 0
    projection = model_inputs[-1]["tool_result_projections"][-1]
    assert projection["tool_name"] == "test.read"
    assert projection["content_truncated"] is True
    assert "ORION_TEST_SECRET_TOKEN" not in json.dumps(capture)
    assert '"current_request":true' in projection["content"]
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
    assert progress["first_stream_activity_kind"] == "assistant"
    assert progress["first_actionable_delta_kind"] == "assistant"
    assert progress["stream_progress_milestone"] == "actionable"
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
        _stream_progress_record(sink, outcome.request_id)["first_stream_activity_kind"]
        == "tool_call"
    )
    assert (
        _stream_progress_record(sink, outcome.request_id)["first_actionable_delta_kind"]
        == "tool_call"
    )
    assert (
        _stream_progress_record(sink, outcome.request_id)["stream_progress_milestone"]
        == "actionable"
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
    assert record["first_stream_activity_elapsed_ms"] is None
    assert record["first_assistant_delta_elapsed_ms"] is None
    assert record["first_tool_call_delta_elapsed_ms"] is None
    assert record["assistant_delta_count"] == 0
    assert record["assistant_delta_characters"] == 0
    assert record["tool_call_delta_count"] == 0
    assert not _stream_progress_records(sink, outcome.request_id)


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
    def __init__(
        self, clock: _FakeClock, delta: AssistantDelta | ReasoningDelta | None = None
    ) -> None:
        self._clock = clock
        self._delta = delta or AssistantDelta(content="partial")
        self.delta_emitted = asyncio.Event()

    async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
        self._clock.advance(0.15)
        self.delta_emitted.set()
        yield self._delta
        await asyncio.Event().wait()


class _BlockedBeforeFirstEventBackend:
    def __init__(self) -> None:
        self.entered = asyncio.Event()

    async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
        if False:
            yield AssistantDelta(content="unreachable")
        self.entered.set()
        await asyncio.Event().wait()


class _ReasoningThenToolThenHangBackend:
    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self.reasoning_emitted = asyncio.Event()
        self.release_tool_call = asyncio.Event()
        self.tool_call_emitted = asyncio.Event()

    async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
        self._clock.advance(0.1)
        yield ReasoningDelta(content="PRIVATE_REASONING")
        self.reasoning_emitted.set()
        await self.release_tool_call.wait()
        self._clock.advance(30)
        yield ToolCallDelta(index=0, tool_name="test.read", arguments_delta="PRIVATE_ARGUMENTS")
        self.tool_call_emitted.set()
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
    assert milestone["first_stream_activity_kind"] == "assistant"
    assert milestone["stream_progress_milestone"] == "actionable"
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
async def test_reasoning_only_stream_activity_is_visible_without_persisting_reasoning(
    store,
) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _ProgressThenHangBackend(clock, ReasoningDelta(content="PRIVATE_REASONING"))
    runtime = _runtime(store, backend, sink, monotonic_clock=clock)
    session_id = store.create_session()
    request_id = runtime.begin(session_id, "Reasoning boundary")
    task = asyncio.create_task(runtime.run(session_id, request_id))
    await backend.delta_emitted.wait()
    await _wait_for_stream_progress(sink, request_id)

    milestone = _stream_progress_record(sink, request_id)
    assert milestone["first_stream_activity_kind"] == "reasoning"
    assert milestone["first_actionable_delta_kind"] is None
    assert milestone["stream_progress_milestone"] == "reasoning"
    assert milestone["first_normalized_event_elapsed_ms"] == 150
    assert milestone["first_reasoning_delta_elapsed_ms"] == 150
    assert milestone["reasoning_delta_count"] == 1
    assert milestone["reasoning_delta_characters"] == len("PRIVATE_REASONING")
    assert milestone["first_assistant_delta_elapsed_ms"] is None
    assert milestone["first_stream_activity_elapsed_ms"] == 150
    assert "PRIVATE_REASONING" not in json.dumps(sink.records(request_id))
    assert not task.done()

    assert runtime.cancel(request_id) is True
    with pytest.raises(RequestCancelled):
        await task
    assert "PRIVATE_REASONING" not in json.dumps(
        [item.payload for item in store.timeline(session_id)]
    )


@pytest.mark.anyio
async def test_in_flight_reasoning_does_not_hide_first_tool_call_milestone(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _ReasoningThenToolThenHangBackend(clock)
    runtime = _runtime(store, backend, sink, monotonic_clock=clock)
    session_id = store.create_session()
    request_id = runtime.begin(session_id, "Reason then tool")
    task = asyncio.create_task(runtime.run(session_id, request_id))
    await backend.reasoning_emitted.wait()
    await _wait_for_stream_progress(sink, request_id)

    before_actionable = _stream_progress_records(sink, request_id)
    assert len(before_actionable) == 1
    assert before_actionable[0]["stream_progress_milestone"] == "reasoning"
    assert before_actionable[0]["first_actionable_delta_kind"] is None

    backend.release_tool_call.set()
    await backend.tool_call_emitted.wait()
    for _ in range(20):
        if len(_stream_progress_records(sink, request_id)) == 2:
            break
        await asyncio.sleep(0)
    else:
        pytest.fail("First actionable tool-call milestone was not recorded.")

    milestones = _stream_progress_records(sink, request_id)
    reasoning, actionable = milestones
    assert reasoning["stream_progress_milestone"] == "reasoning"
    assert reasoning["first_reasoning_delta_elapsed_ms"] == 100
    assert actionable["stream_progress_milestone"] == "actionable"
    assert actionable["first_actionable_delta_kind"] == "tool_call"
    assert actionable["first_tool_call_delta_elapsed_ms"] == 30100
    assert actionable["reasoning_observed_before_first_actionable_delta"] is True
    snapshot = json.dumps(sink.records(request_id))
    assert "PRIVATE_REASONING" not in snapshot
    assert "PRIVATE_ARGUMENTS" not in snapshot
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
async def test_reasoning_diagnostics_preserve_later_assistant_and_tool_delta_behavior(
    store,
) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics()
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                (0.05, ReasoningDelta(content="private")),
                (0.05, AssistantDelta(content="Draft")),
                (0.05, ToolCallDelta(index=0, tool_name="test.read")),
                (
                    0.05,
                    ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="Done."))),
                ),
            ]
        ],
    )

    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        store.create_session(), "Reason then act"
    )

    record = _completed_record(sink, outcome.request_id)
    assert record["first_normalized_event_elapsed_ms"] == 50
    assert record["first_reasoning_delta_elapsed_ms"] == 50
    assert record["reasoning_delta_count"] == 1
    assert record["reasoning_delta_characters"] == len("private")
    assert record["first_assistant_delta_elapsed_ms"] == 100
    assert record["first_tool_call_delta_elapsed_ms"] == 150
    assert record["first_actionable_delta_kind"] == "assistant"
    assert record["reasoning_observed_before_first_actionable_delta"] is True
    assert record["assistant_delta_count"] == 1
    assert record["tool_call_delta_count"] == 1
    milestones = _stream_progress_records(sink, outcome.request_id)
    assert [milestone["stream_progress_milestone"] for milestone in milestones] == [
        "reasoning",
        "actionable",
    ]
    assert milestones[1]["first_actionable_delta_kind"] == "assistant"


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
                (0.1, ReasoningDelta(content="REASONING_CONTENT_SECRET")),
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

    session_id = store.create_session()
    outcome = await _runtime(store, backend, sink, monotonic_clock=clock).submit(
        session_id, "PROMPT_SECRET raw SSE: data: RAW_SSE_SECRET"
    )

    persisted = json.dumps(sink.records(outcome.request_id))
    for secret in (
        "ASSISTANT_CONTENT_SECRET",
        "TOOL_ARGUMENT_SECRET",
        "REASONING_CONTENT_SECRET",
        "PROMPT_SECRET",
        "API_KEY_SECRET",
        "REASONING_SECRET",
        "RAW_SSE_SECRET",
    ):
        assert secret not in persisted
    assert "REASONING_CONTENT_SECRET" not in json.dumps(
        [item.payload for item in store.timeline(session_id)]
    )


@pytest.mark.anyio
async def test_model_stream_diagnostics_keep_record_cardinality_bounded(store) -> None:  # type: ignore[no-untyped-def]
    clock = _FakeClock()
    sink = BoundedModelInputDiagnostics(records_limit=4)
    backend = _TimedScriptedBackend(
        clock,
        [
            [
                *[(0.001, ReasoningDelta(content="x")) for _ in range(40)],
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
    assert len(capture["records"]) == 4
    assert capture["records_truncated"] is False
    assert [
        record["stream_progress_milestone"]
        for record in _stream_progress_records(sink, outcome.request_id)
    ] == ["reasoning", "actionable"]
    record = _completed_record(sink, outcome.request_id)
    assert record["reasoning_delta_count"] == 40
    assert record["assistant_delta_count"] == 40
    assert record["tool_call_delta_count"] == 40


@pytest.mark.anyio
async def test_citation_allowlist_is_rebuilt_from_sources_visible_after_budget_reservation(
    store, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    allowed = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    dropped = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    invented = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    source_allowed = SourceRef(
        source_ref_id=allowed,
        source_kind="grafana",
        source_id="grafana",
    )
    source_dropped = SourceRef(
        source_ref_id=dropped,
        source_kind="grafana",
        source_id="grafana-extra",
    )

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="grafana.alert.list",
            handler_key="grafana.alert.list",
            description="List alerts.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        lambda call: ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"alerts": [{"name": "Example alert"}]},
            sources=(source_allowed,),
        ),
    )

    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="alerts",
                        tool_name="grafana.alert.list",
                        arguments={},
                    ),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content=f"Example alert. [[source:{invented}]]",
                    citation_source_ref_ids=(invented,),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content=f"Example alert. [[source:{allowed}]]",
                    citation_source_ref_ids=(allowed,),
                )
            ),
        ]
    )

    session = store.create_session()
    chat = ChatRuntime(
        store,
        backend,
        builder.freeze(),
        LocalAccessAdapter(),
    )

    original_build = chat._context_builder.build_with_metadata
    original_record_citation_failure = chat._record_citation_failure
    citation_correction_started = False
    correction_build_count = 0

    def record_citation_failure(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal citation_correction_started
        result = original_record_citation_failure(*args, **kwargs)
        citation_correction_started = True
        return result

    def build_with_changed_visible_sources(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal correction_build_count

        result = original_build(*args, **kwargs)

        if not citation_correction_started:
            return result

        correction_build_count += 1

        if correction_build_count == 1:
            # First correction-context build still has both sources.
            return replace(
                result,
                visible_sources=(source_allowed, source_dropped),
            )

        # After reserving bytes for the explicit allowlist, source B no
        # longer fits. The final allowlist must therefore contain only A.
        return replace(
            result,
            visible_sources=(source_allowed,),
        )

    monkeypatch.setattr(
        chat,
        "_record_citation_failure",
        record_citation_failure,
    )
    monkeypatch.setattr(
        chat._context_builder,
        "build_with_metadata",
        build_with_changed_visible_sources,
    )

    outcome = await chat.submit(
        session,
        "List Grafana alerts and cite the source.",
    )

    assert outcome.assistant_content == f"Example alert. [[source:{allowed}]]"
    assert len(backend.calls) == 3
    assert correction_build_count == 2

    correction_messages, _ = backend.calls[-1]
    correction_request = correction_messages[-1]

    assert correction_request.role == "user"

    allowlist = json.loads(
        correction_request.content.split(
            "Allowed evidence_ref aliases:\n",
            1,
        )[1].splitlines()[0]
    )

    assert allowlist == ["S1"]
    assert allowed not in correction_request.content
    assert dropped not in correction_request.content
    assert invented not in correction_request.content
    assert _messages_bytes(correction_messages) <= MAX_CONVERSATION_BYTES


@pytest.mark.anyio
async def test_successfully_repaired_missing_citation_records_rejection_diagnostic(
    store,
) -> None:  # type: ignore[no-untyped-def]
    allowed = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    source = SourceRef(
        source_ref_id=allowed,
        source_kind="internet",
        source_id="https://example.test/",
        url="https://example.test/",
    )

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="internet.fetch",
            handler_key="internet.fetch",
            description="Read a webpage.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        lambda call: ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"content": "Example fact."},
            sources=(source,),
        ),
    )

    rejected_text = "REJECTED_MISSING_CITATION_DRAFT"

    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="fetch",
                        tool_name="internet.fetch",
                        arguments={},
                    ),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content=rejected_text,
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content=f"Example fact. [[source:{allowed}]]",
                    citation_source_ref_ids=(allowed,),
                )
            ),
        ]
    )

    sink = BoundedModelInputDiagnostics()
    session = store.create_session()

    chat = ChatRuntime(
        store,
        backend,
        builder.freeze(),
        LocalAccessAdapter(),
        diagnostic_sink=sink,
    )

    prompt = "Read the page and cite the source."
    request_id = chat.begin(session, prompt)

    outcome = await chat.run(session, request_id)

    assert outcome.assistant_content == f"Example fact. [[source:{allowed}]]"
    assert len(backend.calls) == 3

    captured = sink.records(request_id)
    rejected = [
        record for record in captured["records"] if record.get("stage") == "citation_validation"
    ]

    assert len(rejected) == 1

    diagnostic = rejected[0]
    assert diagnostic["request_id"] == request_id
    assert diagnostic["model_turn_id"]
    assert diagnostic["error_kind"] == "missing_citation"
    assert diagnostic["attempted_source_ref_ids"] == []
    assert diagnostic["visible_source_ref_ids"] == [allowed]
    assert diagnostic["citation_correction_attempted"] is False

    assert rejected_text not in json.dumps(captured)

    assert not [
        item
        for item in store.timeline(session)
        if item.kind == "runtime_notice" and item.payload.get("stage") == "citation_validation"
    ]
