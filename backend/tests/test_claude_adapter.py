from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from provider_fixtures import SplitStream, use_provider

from orion.bootstrap import build_application
from orion.contracts import ContextMessage, ModelTurnCompleted
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.models.backend import ModelBackendError, ModelSettings
from orion.models.providers.claude import ClaudeBackend
from orion.models.providers.tool_names import ToolNameMap
from orion.tool_runtime.calculator import calculator_definition


def configured(**changes):
    profile = ModelProfile.model_validate(
        {
            "profile_id": "claude-fixture",
            "provider_id": "claude",
            "protocol": "anthropic_messages",
            "endpoint": "http://fixture.test/v1",
            "model_id": "owner-selected-model",
            "credential_ref": "env:ORION_FIXTURE_KEY",
            "capabilities": ModelCapabilities(
                streaming=True, tools=True, tool_result_continuation=True, reasoning_controls=True
            ),
            **changes,
        }
    )
    return ModelSettings(
        provider_type=profile.provider_id,
        base_url=profile.endpoint,
        model_id=profile.model_id,
        profile=profile,
        api_key="fixture-provider-key",
    )


def event(kind, **values):
    return {"type": kind, **values}


def framed(events):
    return "".join(
        "event: " + value["type"] + "\ndata: " + json.dumps(value, ensure_ascii=False) + "\n\n"
        for value in events
    )


def start():
    return event(
        "message_start",
        message={
            "id": "msg-fixture",
            "role": "assistant",
            "content": [],
            "usage": {
                "input_tokens": 4,
                "output_tokens": 0,
                "cache_read_input_tokens": 3,
                "cache_creation_input_tokens": 2,
            },
        },
    )


def text_events(text="Hello 秘"):
    return [
        start(),
        event("content_block_start", index=0, content_block={"type": "text", "text": ""}),
        event("content_block_delta", index=0, delta={"type": "text_delta", "text": text}),
        event("content_block_stop", index=0),
        event("message_delta", delta={"stop_reason": "end_turn"}, usage={"output_tokens": 7}),
        event("message_stop"),
    ]


def tool_events():
    wire = ToolNameMap((calculator_definition(),)).to_wire("calculator.evaluate")
    return [
        start(),
        event("ping"),
        event("content_block_start", index=0, content_block={"type": "thinking", "thinking": ""}),
        event(
            "content_block_delta",
            index=0,
            delta={"type": "thinking_delta", "thinking": "private-claude-thinking"},
        ),
        event(
            "content_block_delta",
            index=0,
            delta={"type": "signature_delta", "signature": "private-claude-signature"},
        ),
        event("content_block_stop", index=0),
        event(
            "content_block_start",
            index=1,
            content_block={"type": "tool_use", "id": "calc-a", "name": wire, "input": {}},
        ),
        event(
            "content_block_start",
            index=2,
            content_block={"type": "tool_use", "id": "calc-b", "name": wire, "input": {}},
        ),
        event(
            "content_block_delta",
            index=2,
            delta={"type": "input_json_delta", "partial_json": '{"expression":"3'},
        ),
        event(
            "content_block_delta",
            index=1,
            delta={"type": "input_json_delta", "partial_json": '{"expression":"2+3"}'},
        ),
        event("content_block_stop", index=1),
        event(
            "content_block_delta",
            index=2,
            delta={"type": "input_json_delta", "partial_json": '+5"}'},
        ),
        event("content_block_stop", index=2),
        event("message_delta", delta={"stop_reason": "tool_use"}, usage={"output_tokens": 12}),
        event("message_stop"),
    ]


@pytest.mark.anyio
async def test_default_native_messages_multi_tool_signature_replay_and_later_user_history(
    tmp_path, monkeypatch
):
    requests, streams = [], []
    monkeypatch.setenv("ORION_FIXTURE_KEY", "fixture-provider-key")
    monkeypatch.setenv("ORION_LOG_PATH", str(tmp_path / "application.log"))

    def provider(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "fixture-provider-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in request.headers
        assert isinstance(payload["system"], str) and payload["system"]
        assert all(m["role"] in {"user", "assistant"} for m in payload["messages"])
        assert payload["model"] == "owner-selected-model"
        assert all("input_schema" in tool and "." not in tool["name"] for tool in payload["tools"])
        if len(requests) == 1:
            events = tool_events()
        elif len(requests) == 2:
            assistant = next(m for m in payload["messages"] if m["role"] == "assistant")
            assert assistant["content"][0] == {
                "type": "thinking",
                "thinking": "private-claude-thinking",
                "signature": "private-claude-signature",
            }
            results = [
                block
                for m in payload["messages"]
                if m["role"] == "user"
                for block in m["content"]
                if block["type"] == "tool_result"
            ]
            assert {block["tool_use_id"] for block in results} == {"calc-a", "calc-b"}
            assert all(block["is_error"] is False for block in results)
            events = text_events("The results are 5 and 8. 秘")
        else:
            assert len(requests) == 3
            assert all(m["role"] == "user" for m in payload["messages"])
            assert "Historical conversation record" in json.dumps(payload)
            assert "private-claude" not in json.dumps(payload)
            events = text_events("Hello")
        stream = SplitStream(framed(events))
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    use_provider(monkeypatch, provider)
    app = build_application(tmp_path / "application.db", seed_model_from_environment=False)
    try:
        bound = configured()
        app.store.create_model_config(
            "claude", bound.base_url, bound.model_id, None, profile=bound.profile
        )
        session = app.store.create_session()
        first = await app.runtime.submit(session, "Calculate 2+3 and 3+5")
        assert first.assistant_content == "The results are 5 and 8. 秘"
        assert (await app.runtime.submit(session, "Hello")).assistant_content == "Hello"
        assert sum(item.kind == "tool_result" for item in app.store.timeline(session)) == 2
        public = json.dumps([item.model_dump(mode="json") for item in app.store.timeline(session)])
        public += json.dumps(app.store.events(first.request_id))
        public += (tmp_path / "application.log").read_text(encoding="utf-8")
        assert "private-claude" not in public and "fixture-provider-key" not in public
        assert all(stream.closed for stream in streams)
    finally:
        app.store.close()


@pytest.mark.anyio
async def test_usage_and_explicit_adaptive_effort_match_native_wire(monkeypatch):
    payloads = []

    def provider(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, text=framed(text_events()))

    use_provider(monkeypatch, provider)
    settings = configured(options={"thinking": "adaptive", "effort": "high", "max_tokens": 512})
    events = [
        value
        async for value in ClaudeBackend().stream(
            (ContextMessage(role="user", content="Hello"),), (), settings, asyncio.Event()
        )
    ]
    assert isinstance(events[-1], ModelTurnCompleted)
    assert events[-1].usage.input_tokens == 9 and events[-1].usage.output_tokens == 7
    assert payloads[0]["thinking"] == {"type": "adaptive"}
    assert payloads[0]["output_config"] == {"effort": "high"}
    assert payloads[0]["max_tokens"] == 512 and "tools" not in payloads[0]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "events,kind",
    [
        (text_events()[:-1], "incomplete_stream"),
        (text_events() + [event("message_stop")], "malformed_stream"),
        (
            [event("content_block_delta", index=0, delta={"type": "text_delta", "text": "x"})],
            "malformed_stream",
        ),
        ([start(), event("message_stop")], "malformed_stream"),
        (
            [start(), event("message_delta", delta={"stop_reason": "max_tokens"}, usage={})],
            "incomplete_stream",
        ),
        (
            [start(), event("error", error={"message": "private upstream failure"})],
            "upstream_stream_error",
        ),
        (
            [
                start(),
                event("content_block_start", index=0, content_block={"type": "server_tool_use"}),
            ],
            "unsupported",
        ),
        (
            [
                start(),
                event(
                    "content_block_start", index=True, content_block={"type": "text", "text": ""}
                ),
            ],
            "malformed_stream",
        ),
    ],
)
async def test_invalid_lifecycle_or_unsupported_blocks_never_complete(monkeypatch, events, kind):
    stream = SplitStream(framed(events))
    use_provider(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    with pytest.raises(ModelBackendError) as caught:
        await ClaudeBackend().complete(
            (ContextMessage(role="user", content="Hello"),),
            (calculator_definition(),),
            configured(),
            asyncio.Event(),
        )
    assert caught.value.kind.value == kind
    assert "private upstream failure" not in str(caught.value)
    assert stream.closed


@pytest.mark.anyio
async def test_cancellation_awaits_body_cleanup(monkeypatch):
    started, closed, cancellation = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Blocking(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        async def aclose(self):
            closed.set()

    use_provider(monkeypatch, lambda request: httpx.Response(200, stream=Blocking()))
    task = asyncio.create_task(ClaudeBackend().complete((), (), configured(), cancellation))
    await started.wait()
    cancellation.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.anyio
@pytest.mark.parametrize("arguments", ['{"x":1,"x":2}', '{"x":NaN}', "{", "[1]"])
async def test_invalid_fragmented_tool_input_never_completes(monkeypatch, arguments):
    events = tool_events()
    for value in events:
        if value["type"] == "content_block_delta" and value["index"] == 1:
            value["delta"]["partial_json"] = arguments
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=framed(events)))
    with pytest.raises(ModelBackendError) as caught:
        await ClaudeBackend().complete(
            (), (calculator_definition(),), configured(), asyncio.Event()
        )
    assert caught.value.kind.value == "malformed_stream"


@pytest.mark.anyio
async def test_tool_error_is_returned_as_native_is_error_without_losing_signature(monkeypatch):
    requests = []

    def provider(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 2:
            results = payload["messages"][-1]["content"]
            assert [(block["tool_use_id"], block["is_error"]) for block in results] == [
                ("calc-a", True),
                ("calc-b", False),
            ]
        return httpx.Response(
            200, text=framed(tool_events() if len(requests) == 1 else text_events())
        )

    use_provider(monkeypatch, provider)
    backend, settings = ClaudeBackend(), configured()
    tools = (calculator_definition(),)
    turn = await backend.complete((), tools, settings, asyncio.Event())
    messages = (
        ContextMessage(role="assistant", content="", tool_calls=turn.tool_calls),
        ContextMessage(
            role="tool",
            content='{"status":"error","error":{"code":"fixture"}}',
            tool_call_id="calc-a",
            tool_name="calculator.evaluate",
        ),
        ContextMessage(
            role="tool",
            content='{"status":"success","data":{"value":8}}',
            tool_call_id="calc-b",
            tool_name="calculator.evaluate",
        ),
    )
    result = await backend.complete(
        messages,
        tools,
        settings.model_copy(update={"provider_continuation": turn.provider_continuation}),
        asyncio.Event(),
    )
    assert result.assistant.content == "Hello 秘"


@pytest.mark.anyio
async def test_native_private_state_rejects_new_request_before_transport(monkeypatch):
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=framed(tool_events())))
    backend, settings = ClaudeBackend(), configured()
    turn = await backend.complete((), (calculator_definition(),), settings, asyncio.Event())

    def unexpected(**kwargs):
        pytest.fail("Cross-request native state reached transport")

    monkeypatch.setattr("orion.models.providers.claude.httpx.AsyncClient", unexpected)
    changed = settings.model_copy(
        update={
            "provider_continuation": turn.provider_continuation,
            "request_binding": "different-request",
        }
    )
    with pytest.raises(ModelBackendError) as caught:
        await backend.complete((), (calculator_definition(),), changed, asyncio.Event())
    assert caught.value.kind.value == "protocol"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 529])
async def test_http_error_status_never_replays_or_exposes_body(monkeypatch, status):
    use_provider(monkeypatch, lambda request: httpx.Response(status, text="private-claude-body"))
    with pytest.raises(ModelBackendError) as caught:
        await ClaudeBackend().complete((), (), configured(), asyncio.Event())
    assert caught.value.kind.value == "upstream_http" and not caught.value.retry_safe
    assert "private-claude-body" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "options",
    [
        {"thinking": "enabled", "budget_tokens": 1024},
        {"temperature": 1},
        {"max_tokens": True},
        {"thinking": "disabled", "effort": "high"},
    ],
)
async def test_unsupported_controls_reject_before_transport(monkeypatch, options):
    def unexpected(**kwargs):
        pytest.fail("Unsupported Claude options reached transport")

    monkeypatch.setattr("orion.models.providers.claude.httpx.AsyncClient", unexpected)
    with pytest.raises(ModelBackendError):
        await ClaudeBackend().complete((), (), configured(options=options), asyncio.Event())


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["signature", "duplicate_block", "usage", "event_name"])
async def test_identity_signature_and_usage_failures_are_safe(monkeypatch, fault):
    events = tool_events()
    if fault == "signature":
        events = [
            value
            for value in events
            if not (
                value["type"] == "content_block_delta"
                and value["delta"]["type"] == "signature_delta"
            )
        ]
    elif fault == "duplicate_block":
        events.insert(3, events[2])
    elif fault == "usage":
        events[0]["message"]["usage"]["input_tokens"] = True
    body = framed(events)
    if fault == "event_name":
        body = body.replace("event: message_start", "event: message_stop", 1)
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=body))
    with pytest.raises(ModelBackendError) as caught:
        await ClaudeBackend().complete(
            (), (calculator_definition(),), configured(), asyncio.Event()
        )
    assert caught.value.kind.value == "malformed_stream"


@pytest.mark.anyio
async def test_native_request_byte_bound_rejects_before_transport(monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("Oversized Claude request reached HTTP transport")

    monkeypatch.setattr("orion.models.providers.claude.httpx.AsyncClient", unexpected)
    with pytest.raises(ModelBackendError, match="byte limit"):
        await ClaudeBackend().complete(
            (ContextMessage(role="user", content="秘" * 2000),),
            (),
            configured(context_max_bytes=4096, request_max_bytes=4096),
            asyncio.Event(),
        )


@pytest.mark.anyio
async def test_future_metadata_event_is_ignored_without_replacing_terminal_validation(monkeypatch):
    events = text_events()
    events.insert(1, event("future_metadata", payload="private-not-a-response"))
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=framed(events)))
    result = await ClaudeBackend().complete((), (), configured(), asyncio.Event())
    assert result.assistant.content == "Hello 秘"
