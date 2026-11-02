"""A malformed normalized stream must never authorize a partial tool dispatch."""

import asyncio

import pytest
from conftest import runtime

from orion.chat.runtime import RequestFailed
from orion.contracts import AssistantDelta, ModelToolCall, ModelTurn, ModelTurnCompleted
from orion.models.backend import (
    ModelBackend,
    ModelBackendError,
    ModelBackendErrorKind,
    ModelSettings,
)


def tool_turn():
    return ModelTurnCompleted(
        turn=ModelTurn(
            tool_calls=(
                ModelToolCall(
                    call_id="calc-a",
                    tool_name="calculator.evaluate",
                    arguments={"expression": "1+1"},
                ),
            )
        )
    )


class InvalidBackend(ModelBackend):
    def __init__(self, events):
        self.events = events
        self.closed = False

    async def stream(self, messages, tools, settings, cancellation):
        try:
            for event in self.events:
                yield event
        finally:
            self.closed = True


@pytest.mark.anyio
@pytest.mark.parametrize(
    "events",
    [
        [],
        [AssistantDelta(content="unfinished")],
        [tool_turn(), tool_turn()],
        [tool_turn(), AssistantDelta(content="late")],
        [object()],
    ],
)
async def test_runtime_rejects_invalid_stream_before_tool_dispatch(store, events):
    session = store.create_session()
    backend = InvalidBackend(events)
    with pytest.raises(RequestFailed):
        await runtime(store, backend).submit(session, "Calculate")
    assert not any(item.kind in {"tool_call", "tool_result"} for item in store.timeline(session))
    assert backend.closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "events,kind",
    [
        ([], ModelBackendErrorKind.INCOMPLETE_STREAM),
        ([tool_turn(), tool_turn()], ModelBackendErrorKind.PROTOCOL),
        ([tool_turn(), AssistantDelta(content="late")], ModelBackendErrorKind.PROTOCOL),
    ],
)
async def test_complete_collector_checks_the_entire_stream(events, kind):
    settings = ModelSettings(
        provider_type="openai_compatible", base_url="http://fixture.test", model_id="fixture"
    )
    backend = InvalidBackend(events)
    with pytest.raises(ModelBackendError) as caught:
        await backend.complete((), (), settings, asyncio.Event())
    assert caught.value.kind == kind
    assert backend.closed
