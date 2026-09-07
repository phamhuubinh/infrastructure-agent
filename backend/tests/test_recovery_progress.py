from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import ScriptedBackend, runtime

from orion.chat.runtime import _read_progress_evidence, _recoverable_failure_fingerprint
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ReadProgress,
    SourceRef,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.models.backend import ModelBackendError, ModelBackendErrorKind
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistryBuilder

_TOOL_NAME = "test.recover"


def _definition() -> ToolDefinition:
    return ToolDefinition(
        name=_TOOL_NAME,
        description="Test recoverable input progression.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler_key=_TOOL_NAME,
    )


def _handler(call: ToolCall) -> ToolResult:
    if call.arguments["value"] == "ok":
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success", data={})
    return ToolResult.failure(
        call.call_id,
        call.tool_name,
        "needs_correction",
        "Try a corrected value.",
        model_recovery_required=True,
    )


def _registry():  # type: ignore[no-untyped-def]
    builder = ToolRegistryBuilder()
    builder.register(_definition(), _handler)
    return builder.freeze()


def _call(call_id: str, value: str) -> ModelTurn:
    return ModelTurn(
        tool_calls=(
            ModelToolCall(call_id=call_id, tool_name=_TOOL_NAME, arguments={"value": value}),
        )
    )


def _mixed_call(call_id: str, *, reversed_order: bool = False) -> ModelTurn:
    calls = (
        ModelToolCall(call_id=f"{call_id}-failed", tool_name=_TOOL_NAME, arguments={"value": "a"}),
        ModelToolCall(
            call_id=f"{call_id}-success", tool_name=_TOOL_NAME, arguments={"value": "ok"}
        ),
    )
    return ModelTurn(tool_calls=tuple(reversed(calls)) if reversed_order else calls)


def _expand() -> ModelTurn:
    return ModelTurn(
        tool_calls=(
            ModelToolCall(
                call_id="expand",
                tool_name=EXPAND_TOOL_NAME,
                arguments={"tool_names": [_TOOL_NAME]},
            ),
        )
    )


def test_recovery_fingerprint_normalizes_argument_key_order() -> None:
    first = ModelToolCall(call_id="one", tool_name="test.tool", arguments={"b": 2, "a": {"z": 1}})
    second = ModelToolCall(call_id="two", tool_name="test.tool", arguments={"a": {"z": 1}, "b": 2})
    first_result = ToolResult.failure(
        "one", "test.tool", "recover", "retry", model_recovery_required=True
    )
    second_result = ToolResult.failure(
        "two", "test.tool", "recover", "retry", model_recovery_required=True
    )

    assert _recoverable_failure_fingerprint(first, first_result) == (
        _recoverable_failure_fingerprint(second, second_result)
    )


def _read_evidence(
    *,
    call_id: str,
    arguments: dict[str, object],
    data: object,
    progress: ReadProgress | None,
    retrieved_at: datetime,
    definition: ToolDefinition | None = None,
    observations: dict[tuple[str, str], str],
):
    call = ModelToolCall(call_id=call_id, tool_name=_TOOL_NAME, arguments=arguments)
    result = ToolResult(
        call_id=call_id,
        tool_name=_TOOL_NAME,
        status="success",
        data=data,
        sources=(
            SourceRef(
                source_ref_id="source",
                source_kind="test",
                source_id="target",
                retrieved_at=retrieved_at,
            ),
        ),
        read_progress=progress,
    )
    return _read_progress_evidence(call, result, definition or _definition(), observations)


def test_read_progress_ignores_call_id_and_retrieval_timestamp() -> None:
    observations: dict[tuple[str, str], str] = {}
    progress = ReadProgress(observation_id="target", version="v1", certainty="confirmed")
    now = datetime.now(UTC)

    first = _read_evidence(
        call_id="one",
        arguments={"value": "same"},
        data={"value": 1},
        progress=progress,
        retrieved_at=now,
        observations=observations,
    )
    repeated = _read_evidence(
        call_id="two",
        arguments={"value": "same"},
        data={"value": 1},
        progress=progress,
        retrieved_at=now + timedelta(minutes=1),
        observations=observations,
    )

    assert first is not None and first.classification == "confirmed_progress"
    assert repeated is not None and repeated.classification == "confirmed_no_progress"


def test_read_progress_preserves_event_data_cursor_and_query_coverage() -> None:
    observations: dict[tuple[str, str], str] = {}
    now = datetime.now(UTC)
    first = _read_evidence(
        call_id="one",
        arguments={"query": "first"},
        data={"events": []},
        progress=ReadProgress(
            observation_id="events",
            cursor="page-1",
            coverage={"window": "first"},
            event_time=now,
            certainty="confirmed",
        ),
        retrieved_at=now,
        observations=observations,
    )
    data_changed = _read_evidence(
        call_id="two",
        arguments={"query": "first"},
        data={"events": [{"id": "new"}]},
        progress=ReadProgress(
            observation_id="events",
            cursor="page-1",
            coverage={"window": "first"},
            event_time=now,
            certainty="confirmed",
        ),
        retrieved_at=now + timedelta(minutes=1),
        observations=observations,
    )
    event_changed = _read_evidence(
        call_id="three",
        arguments={"query": "first"},
        data={"events": [{"id": "new"}]},
        progress=ReadProgress(
            observation_id="events",
            cursor="page-1",
            coverage={"window": "first"},
            event_time=now + timedelta(seconds=1),
            certainty="confirmed",
        ),
        retrieved_at=now + timedelta(minutes=2),
        observations=observations,
    )
    next_page = _read_evidence(
        call_id="four",
        arguments={"query": "first"},
        data={"events": [{"id": "new"}]},
        progress=ReadProgress(
            observation_id="events",
            cursor="page-2",
            coverage={"window": "first"},
            event_time=now + timedelta(seconds=1),
            certainty="confirmed",
        ),
        retrieved_at=now + timedelta(minutes=3),
        observations=observations,
    )
    query_coverage_changed = _read_evidence(
        call_id="five",
        arguments={"query": "second"},
        data={"events": [{"id": "new"}]},
        progress=ReadProgress(
            observation_id="events",
            cursor="page-2",
            coverage={"window": "second"},
            event_time=now + timedelta(seconds=1),
            certainty="confirmed",
        ),
        retrieved_at=now + timedelta(minutes=4),
        observations=observations,
    )

    assert first is not None and first.classification == "confirmed_progress"
    assert data_changed is not None and data_changed.classification == "confirmed_progress"
    assert event_changed is not None and event_changed.classification == "confirmed_progress"
    assert next_page is not None and next_page.classification == "confirmed_progress"
    assert (
        query_coverage_changed is not None
        and query_coverage_changed.classification == "confirmed_progress"
    )


def test_read_progress_without_contract_or_for_mutation_is_conservative() -> None:
    observations: dict[tuple[str, str], str] = {}
    now = datetime.now(UTC)
    unknown = _read_evidence(
        call_id="unknown",
        arguments={"value": "empty"},
        data={},
        progress=None,
        retrieved_at=now,
        observations=observations,
    )
    mutation = _read_evidence(
        call_id="mutation",
        arguments={"value": "changed"},
        data={"changed": True},
        progress=ReadProgress(observation_id="target", certainty="confirmed"),
        retrieved_at=now,
        definition=_definition().model_copy(update={"operation_kind": "mutation"}),
        observations=observations,
    )

    assert unknown is not None and unknown.classification == "unknown_progress"
    assert mutation is None


def test_empty_initial_query_is_evidence_when_coverage_is_declared() -> None:
    observations: dict[tuple[str, str], str] = {}
    evidence = _read_evidence(
        call_id="empty-initial",
        arguments={"query": "new scope"},
        data={"results": []},
        progress=ReadProgress(
            observation_id="search-target",
            coverage={"query": "new scope"},
            certainty="confirmed",
        ),
        retrieved_at=datetime.now(UTC),
        observations=observations,
    )

    assert evidence is not None and evidence.classification == "confirmed_progress"


@pytest.mark.anyio
async def test_changed_recoverable_arguments_continue_beyond_old_turn_count(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-1", "one"),
            _call("bad-2", "two"),
            _call("bad-3", "three"),
            _call("bad-4", "four"),
            _call("ok", "ok"),
            ModelTurn(assistant=AssistantMessage(content="Recovered.")),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(
        session, "Keep correcting the input"
    )

    assert outcome.assistant_content == "Recovered."
    for model_call_index in (2, 3, 4, 5):
        assert _TOOL_NAME in {tool.name for tool in backend.calls[model_call_index][1]}


@pytest.mark.anyio
async def test_identical_recoverable_failure_state_eventually_disables_tools(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-1", "same"),
            _call("bad-2", "same"),
            _call("bad-3", "same"),
            ModelTurn(assistant=AssistantMessage(content="I need corrected input.")),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Use the tool")

    assert outcome.assistant_content == "I need corrected input."
    assert backend.calls[-1][1] == ()
    assert any(
        "same recoverable tool failure state" in message.content
        for message in backend.calls[-1][0]
        if message.role == "system"
    )


@pytest.mark.anyio
async def test_terminal_turn_tool_call_is_never_dispatched(store) -> None:  # type: ignore[no-untyped-def]
    executions: list[str] = []

    def handler(call: ToolCall) -> ToolResult:
        executions.append(call.call_id)
        return _handler(call)

    builder = ToolRegistryBuilder()
    builder.register(_definition(), handler)
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-1", "same"),
            _call("bad-2", "same"),
            _call("bad-3", "same"),
            _call("malicious-final", "ok"),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, builder.freeze()).submit(session, "Use the tool")

    assert outcome.status == "incomplete"
    assert executions == ["bad-1", "bad-2", "bad-3"]
    assert backend.calls[-1][1] == ()
    assert all(
        item.call_id != "malicious-final"
        for item in store.timeline(session)
        if item.kind == "tool_call"
    )
    terminal_events = [
        event for event in store.events(outcome.request_id) if event["type"] == "request.incomplete"
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0]["payload"]["stop_reason"] == "terminal_turn_did_not_return_an_answer"


@pytest.mark.anyio
async def test_terminal_turn_with_invalid_citation_persists_incomplete(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-1", "same"),
            _call("bad-2", "same"),
            _call("bad-3", "same"),
            ModelTurn(
                assistant=AssistantMessage(
                    content="Unsupported. [[source:not-observed]]",
                    citation_source_ref_ids=("not-observed",),
                )
            ),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Use the tool")

    assert outcome.status == "incomplete"
    assert store.request(outcome.request_id)["status"] == "incomplete"
    assert all(
        "Unsupported." not in item.payload.get("content", "")
        for item in store.timeline(session)
        if item.kind == "assistant_message"
    )


@pytest.mark.anyio
async def test_terminal_malformed_backend_result_persists_incomplete(store) -> None:  # type: ignore[no-untyped-def]
    class MalformedFinalBackend(ScriptedBackend):
        async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
            self.calls.append((messages, tools))
            if not self.turns:
                raise ModelBackendError(
                    "Model stream was malformed.", kind=ModelBackendErrorKind.MALFORMED_STREAM
                )
            yield ModelTurnCompleted(turn=self.turns.pop(0))

    backend = MalformedFinalBackend(
        [_expand(), _call("bad-1", "same"), _call("bad-2", "same"), _call("bad-3", "same")]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Use the tool")

    assert outcome.status == "incomplete"
    assert backend.calls[-1][1] == ()
    event = next(
        event for event in store.events(outcome.request_id) if event["type"] == "request.incomplete"
    )
    assert event["payload"] == {
        "stop_reason": "terminal_model_failure",
        "observation_source_ref_ids": [],
        "model_error_kind": "malformed_stream",
    }


@pytest.mark.anyio
async def test_terminal_turn_accepts_a_valid_existing_citation(store) -> None:  # type: ignore[no-untyped-def]
    source_tool = ToolDefinition(
        name="test.source",
        description="Return one visible source.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler_key="test.source",
    )

    def source_handler(call: ToolCall) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"observed": True},
            sources=(
                SourceRef(
                    source_ref_id="terminal-visible",
                    source_kind="internet",
                    source_id="target",
                    url="https://example.test/evidence",
                ),
            ),
        )

    builder = ToolRegistryBuilder()
    builder.register(_definition(), _handler)
    builder.register(source_tool, source_handler)
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="expand",
                        tool_name=EXPAND_TOOL_NAME,
                        arguments={"tool_names": [_TOOL_NAME, source_tool.name]},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="source", tool_name=source_tool.name, arguments={}),
                )
            ),
            _call("bad-1", "same"),
            _call("bad-2", "same"),
            _call("bad-3", "same"),
            ModelTurn(
                assistant=AssistantMessage(
                    content="Only the observed source is available. [[source:terminal-visible]]",
                    citation_source_ref_ids=("terminal-visible",),
                )
            ),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, builder.freeze()).submit(session, "Use the evidence")

    assert outcome.status == "completed"
    assert outcome.assistant_content.startswith("Only the observed source")
    assert backend.calls[-1][1] == ()
    terminal_events = [
        event
        for event in store.events(outcome.request_id)
        if event["type"] in {"request.completed", "request.incomplete"}
    ]
    assert [event["type"] for event in terminal_events] == ["request.completed"]


@pytest.mark.anyio
async def test_alternating_recoverable_failure_cycle_disables_tools(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-a-1", "a"),
            _call("bad-b-1", "b"),
            _call("bad-a-2", "a"),
            _call("bad-b-2", "b"),
            ModelTurn(assistant=AssistantMessage(content="I need corrected input.")),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Use the tool")

    assert outcome.assistant_content == "I need corrected input."
    assert backend.calls[-1][1] == ()


@pytest.mark.anyio
async def test_expansion_between_cycle_failures_preserves_history(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-a-1", "a"),
            _expand(),
            _call("bad-b-1", "b"),
            _call("bad-a-2", "a"),
            _call("bad-b-2", "b"),
            ModelTurn(assistant=AssistantMessage(content="I need corrected input.")),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Use the tool")

    assert outcome.assistant_content == "I need corrected input."

    assert backend.calls[-1][1] == ()


@pytest.mark.anyio
async def test_mixed_success_does_not_hide_repeated_recoverable_failure(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _mixed_call("mixed-1"),
            _mixed_call("mixed-2", reversed_order=True),
            _mixed_call("mixed-3"),
            ModelTurn(assistant=AssistantMessage(content="I need corrected input.")),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Use the tool")

    assert outcome.assistant_content == "I need corrected input."
    assert backend.calls[-1][1] == ()


@pytest.mark.anyio
async def test_recovery_tracker_is_isolated_between_requests(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("first-a-1", "a"),
            _call("first-a-2", "a"),
            ModelTurn(assistant=AssistantMessage(content="Need recovery.")),
            ModelTurn(assistant=AssistantMessage(content="First complete.")),
            _expand(),
            _call("second-a-1", "a"),
            ModelTurn(assistant=AssistantMessage(content="Need recovery.")),
            ModelTurn(assistant=AssistantMessage(content="Second complete.")),
        ]
    )
    session = store.create_session()
    chat = runtime(store, backend, _registry())

    await chat.submit(session, "First request")
    outcome = await chat.submit(session, "Second request")

    assert outcome.assistant_content == "Second complete."
    assert len(backend.calls) == 9
    assert backend.calls[7][1] != ()
