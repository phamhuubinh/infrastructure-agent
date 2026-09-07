from __future__ import annotations

import asyncio

import pytest

from orion.access import LocalAccessAdapter
from orion.chat.deadline import (
    MutationOutcomeUnknown,
    RequestBudget,
    RequestBudgetSettings,
    RequestDeadlineExceeded,
)
from orion.chat.runtime import ChatRuntime
from orion.contracts import (
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.models.backend import ModelBackend, ModelSettings
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistryBuilder


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


async def _never() -> None:
    await asyncio.Event().wait()


async def _wait_without_expiring(_: float) -> None:
    await asyncio.Event().wait()


@pytest.mark.anyio
async def test_request_budget_expires_without_sleeping_in_real_time() -> None:
    clock = FakeClock()

    async def advance_to_deadline(seconds: float) -> None:
        clock.advance(seconds)

    budget = RequestBudget.start(
        RequestBudgetSettings(request_deadline_seconds=10, finalization_reserve_seconds=2),
        clock=clock,
        sleeper=advance_to_deadline,
    )

    with pytest.raises(RequestDeadlineExceeded) as error:
        await budget.await_work(_never(), asyncio.Event(), phase="model")

    assert error.value.phase == "model"
    assert clock.value == 8


@pytest.mark.anyio
async def test_request_budget_observes_user_cancellation_before_starting_work() -> None:
    clock = FakeClock()
    budget = RequestBudget.start(
        RequestBudgetSettings(request_deadline_seconds=10, finalization_reserve_seconds=2),
        clock=clock,
    )
    cancellation = asyncio.Event()
    cancellation.set()
    operation = _never()

    try:
        with pytest.raises(asyncio.CancelledError):
            await budget.await_work(operation, cancellation, phase="tool")
    finally:
        operation.close()


class _ExpiringBackend(ModelBackend):
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock

    async def stream(self, messages, tools, settings: ModelSettings, cancellation):  # type: ignore[no-untyped-def]
        self._clock.advance(8)
        yield ModelTurnCompleted(
            turn=ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="expired-call", tool_name="fake.count", arguments={}),
                )
            )
        )


@pytest.mark.anyio
async def test_runtime_deadline_prevents_tool_dispatch_after_work_deadline(store) -> None:  # type: ignore[no-untyped-def]
    executions = 0

    def handler(call: ToolCall) -> ToolResult:
        nonlocal executions
        executions += 1
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success", data={})

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="fake.count",
            description="Count calls.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler_key="fake.count",
        ),
        handler,
    )
    clock = FakeClock()
    session_id = store.create_session()
    chat = ChatRuntime(
        store,
        _ExpiringBackend(clock),
        builder.freeze(),
        LocalAccessAdapter(),
        request_budget_settings=RequestBudgetSettings(
            request_deadline_seconds=10, finalization_reserve_seconds=2
        ),
        monotonic_clock=clock,
        deadline_sleeper=_wait_without_expiring,
    )

    outcome = await chat.submit(session_id, "Count")

    assert executions == 0
    assert outcome.status == "incomplete"
    assert store.request(outcome.request_id)["status"] == "incomplete"
    notices = [item for item in store.timeline(session_id) if item.kind == "runtime_notice"]
    assert notices[-1].payload == {
        "stage": "terminal",
        "status": "incomplete",
        "stop_reason": "request_deadline_exceeded",
        "observation_source_ref_ids": [],
        "phase": "model",
        "elapsed_ms": 8000,
    }


@pytest.mark.anyio
async def test_terminal_turn_hang_persists_one_incomplete_fallback(store) -> None:  # type: ignore[no-untyped-def]
    class Backend(ModelBackend):
        def __init__(self) -> None:
            self.calls: list[tuple[object, object]] = []
            self.turns = [
                ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id="expand",
                            tool_name=EXPAND_TOOL_NAME,
                            arguments={"tool_names": ["fake.recover"]},
                        ),
                    )
                ),
                *[
                    ModelTurn(
                        tool_calls=(
                            ModelToolCall(
                                call_id=f"recover-{index}",
                                tool_name="fake.recover",
                                arguments={},
                            ),
                        )
                    )
                    for index in range(1, 4)
                ],
            ]

        async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
            self.calls.append((messages, tools))
            if not self.turns:
                await asyncio.Event().wait()
            else:
                yield ModelTurnCompleted(turn=self.turns.pop(0))

    executions = 0

    def recover(call: ToolCall) -> ToolResult:
        nonlocal executions
        executions += 1
        return ToolResult.failure(
            call.call_id,
            call.tool_name,
            "recover",
            "Retry cannot progress.",
            model_recovery_required=True,
        )

    clock = FakeClock()

    async def advance_terminal_to_work_deadline(seconds: float) -> None:
        await asyncio.sleep(0)
        if len(backend.calls) >= 5:
            clock.advance(seconds)
            return
        await asyncio.Event().wait()

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="fake.recover",
            description="Always returns a recoverable error.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler_key="fake.recover",
        ),
        recover,
    )
    backend = Backend()
    session_id = store.create_session()
    chat = ChatRuntime(
        store,
        backend,
        builder.freeze(),
        LocalAccessAdapter(),
        request_budget_settings=RequestBudgetSettings(
            request_deadline_seconds=10, finalization_reserve_seconds=2
        ),
        monotonic_clock=clock,
        deadline_sleeper=advance_terminal_to_work_deadline,
    )

    outcome = await chat.submit(session_id, "Recover safely")

    assert outcome.status == "incomplete"
    assert executions == 3
    assert len(backend.calls) == 5
    assert backend.calls[-1][1] == ()
    terminal_events = [
        event for event in store.events(outcome.request_id) if event["type"] == "request.incomplete"
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0]["payload"]["stop_reason"] == "request_deadline_exceeded"


@pytest.mark.anyio
async def test_request_budget_cancels_and_drains_a_hanging_read() -> None:
    budget = RequestBudget.start(RequestBudgetSettings(request_deadline_seconds=10))
    cancellation = asyncio.Event()
    stopped = asyncio.Event()

    async def read() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            stopped.set()
            raise

    async def cancel_on_next_turn() -> None:
        await asyncio.sleep(0)
        cancellation.set()

    canceller = asyncio.create_task(cancel_on_next_turn())
    with pytest.raises(asyncio.CancelledError):
        await budget.await_work(read(), cancellation, phase="tool")
    await canceller
    assert stopped.is_set()


@pytest.mark.anyio
async def test_request_budget_drains_dispatched_mutation_before_terminal_handoff() -> None:
    budget = RequestBudget.start(RequestBudgetSettings(request_deadline_seconds=10))
    cancellation = asyncio.Event()
    released = asyncio.Event()

    async def dispatched_mutation() -> str:
        await released.wait()
        return "outcome_unknown"

    async def interrupt_then_release() -> None:
        await asyncio.sleep(0)
        cancellation.set()
        released.set()

    interrupter = asyncio.create_task(interrupt_then_release())
    result = await budget.await_work(
        dispatched_mutation(),
        cancellation,
        phase="tool",
        preserve_on_interrupt=True,
    )
    await interrupter
    assert result == "outcome_unknown"


@pytest.mark.anyio
async def test_preserved_mutation_never_waits_past_absolute_deadline() -> None:
    clock = FakeClock()

    async def advance(seconds: float) -> None:
        clock.advance(seconds)

    budget = RequestBudget.start(
        RequestBudgetSettings(request_deadline_seconds=10, finalization_reserve_seconds=2),
        clock=clock,
        sleeper=advance,
    )

    with pytest.raises(MutationOutcomeUnknown) as error:
        await budget.await_work(
            _never(),
            asyncio.Event(),
            phase="tool",
            preserve_on_interrupt=True,
        )

    assert error.value.cancelled is False
    assert clock.value == 10


@pytest.mark.anyio
async def test_runtime_persists_mutation_outcome_before_deadline_terminalization(store) -> None:  # type: ignore[no-untyped-def]
    clock = FakeClock()

    class Backend(ModelBackend):
        def __init__(self) -> None:
            self.turns = [
                ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id="expand",
                            tool_name=EXPAND_TOOL_NAME,
                            arguments={"tool_names": ["fake.mutate"]},
                        ),
                    )
                ),
                ModelTurn(
                    tool_calls=(
                        ModelToolCall(call_id="mutation", tool_name="fake.mutate", arguments={}),
                    )
                ),
            ]

        async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
            yield ModelTurnCompleted(turn=self.turns.pop(0))

    async def mutation(call: ToolCall) -> ToolResult:
        clock.advance(8)
        return ToolResult.failure(
            call.call_id,
            call.tool_name,
            "outcome_unknown",
            "The side effect may have happened; final state is unknown.",
        )

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="fake.mutate",
            description="Mutation test double.",
            operation_kind="mutation",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler_key="fake.mutate",
        ),
        mutation,
    )
    session_id = store.create_session()
    chat = ChatRuntime(
        store,
        Backend(),
        builder.freeze(),
        LocalAccessAdapter(),
        request_budget_settings=RequestBudgetSettings(
            request_deadline_seconds=10, finalization_reserve_seconds=2
        ),
        monotonic_clock=clock,
        deadline_sleeper=_wait_without_expiring,
    )

    request_id = chat.begin(session_id, "Mutate")
    outcome = await chat.run(session_id, request_id)

    result = next(
        item.payload["result"]
        for item in store.timeline(session_id)
        if item.kind == "tool_result" and item.tool_name == "fake.mutate"
    )
    assert result["error"]["code"] == "outcome_unknown"
    assert outcome.status == "incomplete"
    assert store.request(request_id)["status"] == "incomplete"
