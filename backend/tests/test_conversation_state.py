from __future__ import annotations

import pytest
from conftest import ScriptedBackend, runtime

from orion.chat.context_builder import ContextBuilder
from orion.contracts import AssistantMessage, ModelTurn


def test_legacy_checkpoint_rows_remain_persistent_but_are_not_model_context(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    boundary = store.append_timeline(session_id, None, "user_message", {"content": "old"})
    store.save_conversation_state_checkpoint(
        session_id, "stale generated summary", boundary.item_id
    )
    store.append_timeline(session_id, None, "user_message", {"content": "current"})

    context = ContextBuilder(store).build(session_id)

    assert store.conversation_state_checkpoint(session_id) is not None
    assert "stale generated summary" not in "".join(message.content for message in context)


@pytest.mark.anyio
async def test_long_conversation_starts_the_ordinary_model_turn_without_a_summary_call(
    store,
) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    for index in range(24):
        store.append_timeline(
            session_id, None, "user_message", {"content": f"user {index} " + "x" * 500}
        )
        store.append_timeline(
            session_id,
            None,
            "assistant_message",
            {
                "content": f"assistant {index} " + "y" * 500,
                "citation_source_ref_ids": [],
                "tool_calls": [],
            },
        )
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="ordinary answer"))])

    outcome = await runtime(store, backend).submit(session_id, "current message is retained")

    assert outcome.assistant_content == "ordinary answer"
    assert len(backend.calls) == 1
    assert any(message.content == "current message is retained" for message in backend.calls[0][0])
