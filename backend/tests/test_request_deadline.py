from __future__ import annotations

import asyncio

import pytest

from orion.access import LocalAccessAdapter
from orion.chat.deadline import RequestBudget, RequestBudgetSettings, RequestDeadlineExceeded
from orion.chat.runtime import ChatRuntime, RequestFailed
from orion.contracts import (
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.models.backend import ModelBackend, ModelSettings
from orion.tool_runtime.registry import ToolRegistryBuilder


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

    with pytest.raises(RequestFailed, match="Request deadline exceeded"):
        await chat.submit(session_id, "Count")

    assert executions == 0
    notices = [item for item in store.timeline(session_id) if item.kind == "runtime_notice"]
    assert notices[-1].payload == {
        "stage": "request_deadline",
        "status": "failed",
        "error_kind": "deadline_exceeded",
        "phase": "model",
        "elapsed_ms": 8000,
    }
