from __future__ import annotations

import asyncio
import json

import pytest
from conftest import runtime
from pydantic import SecretStr

from orion.bootstrap import build_application
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import RequestFailed
from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
)
from orion.models.backend import ModelBackend, ModelSettings
from orion.security import SecretStreamRedactor, redact_text

KEY = "fixture-protected-provider-key"


@pytest.mark.parametrize("size", [1, 2, 3, 7, 29, 100])
def test_literal_key_redaction_survives_every_delta_size(size):
    redactor = SecretStreamRedactor((KEY,))
    content = "Before " + KEY + " after"
    visible = "".join(
        redactor.feed(content[index : index + size]) for index in range(0, len(content), size)
    )
    visible += redactor.finish()
    assert visible == "Before [REDACTED] after"


def test_overlapping_secret_prefixes_and_ordinary_suffix_remain_correct():
    redactor = SecretStreamRedactor(("abcdabcd",))
    assert redactor.feed("abcd") == ""
    assert redactor.feed("abcd") == "[REDACTED]"
    assert redactor.finish() == ""
    plain = SecretStreamRedactor((KEY,))
    assert plain.feed("This is a fi") + plain.finish() == "This is a fi"


class EchoBackend(ModelBackend):
    async def stream(self, messages, tools, settings, cancellation):
        for fragment in ("Before ", KEY[:8], KEY[8:18], KEY[18:], " after"):
            yield AssistantDelta(content=fragment)
        yield ModelTurnCompleted(
            turn=ModelTurn(assistant=AssistantMessage(content="Before " + KEY + " after"))
        )


@pytest.mark.anyio
async def test_protected_key_echo_does_not_reach_runtime_history_events_diagnostics_log_or_outcome(
    tmp_path, monkeypatch
):
    path = tmp_path / "application.db"
    log = tmp_path / "application.log"
    monkeypatch.setenv("ORION_LOG_PATH", str(log))
    application = build_application(path, EchoBackend(), seed_model_from_environment=False)
    sink = BoundedModelInputDiagnostics()
    application.runtime._diagnostic_sink = sink
    try:
        reference = application.model_configurations.store_credential(SecretStr(KEY))
        application.store.create_model_config(
            "openai_compatible",
            "http://fixture.test/v1",
            "configured",
            None,
            credential_ref=reference,
        )
        session = application.store.create_session()
        outcome = await application.runtime.submit(session, "Hello")
        assert outcome.assistant_content == "Before [REDACTED] after"
        events = application.store.events(outcome.request_id)
        streamed = "".join(
            event["payload"]["content"] for event in events if event["type"] == "assistant.delta"
        )
        assert streamed == outcome.assistant_content
        public = json.dumps(
            {
                "history": [
                    item.model_dump(mode="json") for item in application.store.timeline(session)
                ],
                "events": events,
                "diagnostics": sink.records(outcome.request_id),
            }
        ) + log.read_text(encoding="utf-8")
        assert KEY not in public
        assert redact_text(KEY) == KEY  # Request-local registration is reset.
    finally:
        application.store.close()


@pytest.mark.anyio
async def test_credential_in_model_tool_arguments_fails_before_tool_dispatch(store):
    class BadBackend(ModelBackend):
        async def stream(self, messages, tools, settings, cancellation):
            yield ModelTurnCompleted(
                turn=ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id="bad",
                            tool_name="calculator.evaluate",
                            arguments={"expression": KEY},
                        ),
                    )
                )
            )

    store.update_model_config(
        store.active_model_config()["model_config_id"],
        "openai_compatible",
        "http://fixture.test/v1",
        "configured",
        KEY,
    )
    session = store.create_session()
    with pytest.raises(RequestFailed, match="protected credential material"):
        await runtime(store, BadBackend()).submit(session, "Calculate")
    assert not any(item.kind in {"tool_call", "tool_result"} for item in store.timeline(session))
    assert KEY not in json.dumps([item.model_dump(mode="json") for item in store.timeline(session)])


@pytest.mark.anyio
async def test_complete_collector_also_redacts_credential_echo():
    turn = await EchoBackend().complete(
        (),
        (),
        ModelSettings(
            provider_type="openai_compatible",
            base_url="http://fixture.test",
            model_id="configured",
            api_key=KEY,
        ),
        asyncio.Event(),
    )
    assert turn.assistant.content == "Before [REDACTED] after"
