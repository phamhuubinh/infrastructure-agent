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
from orion.models.providers.deepseek import DeepSeekBackend
from orion.models.providers.tool_names import ToolNameMap
from orion.tool_runtime.calculator import calculator_definition


def configured(**changes):
    profile = ModelProfile.model_validate(
        {
            "profile_id": "deepseek-fixture",
            "provider_id": "deepseek",
            "protocol": "chat_completions",
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


def framed(delta, *, reason="stop", usage=None):
    chunk = {"choices": [{"delta": delta, "finish_reason": reason}]}
    if usage is not None:
        chunk["usage"] = usage
    return "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"


@pytest.mark.anyio
async def test_default_application_runs_multiple_native_thinking_tools_then_later_user_history(
    tmp_path, monkeypatch
):
    requests, streams = [], []
    wire = ToolNameMap((calculator_definition(),)).to_wire("calculator.evaluate")
    monkeypatch.setenv("ORION_FIXTURE_KEY", "fixture-provider-key")
    monkeypatch.setenv("ORION_LOG_PATH", str(tmp_path / "application.log"))

    def provider(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer fixture-provider-key"
        assert payload["model"] == "owner-selected-model"
        assert payload["thinking"] == {"type": "enabled"}
        assert all("." not in tool["function"]["name"] for tool in payload["tools"])
        assert any(tool["function"]["name"] == wire for tool in payload["tools"])
        assert all(tool["function"]["strict"] is False for tool in payload["tools"])
        if len(requests) == 1:
            body = framed({"reasoning_content": "private-reason-first"}, reason=None)
            body += framed(
                {
                    "tool_calls": [
                        {
                            "index": 1,
                            "id": "calc-b",
                            "function": {"name": wire, "arguments": '{"expression":"3'},
                        },
                        {
                            "index": 0,
                            "id": "calc-a",
                            "function": {"name": wire, "arguments": '{"expression":"2'},
                        },
                    ]
                },
                reason=None,
            )
            body += framed(
                {
                    "tool_calls": [
                        {"index": 0, "function": {"arguments": '+3"}'}},
                        {"index": 1, "function": {"arguments": '+5"}'}},
                    ]
                },
                reason="tool_calls",
            )
        elif len(requests) == 2:
            native = [m for m in payload["messages"] if m["role"] == "assistant"]
            assert native[0]["reasoning_content"] == "private-reason-first"
            assert [c["id"] for c in native[0]["tool_calls"]] == ["calc-a", "calc-b"]
            results = [m for m in payload["messages"] if m["role"] == "tool"]
            assert {m["tool_call_id"] for m in results} == {"calc-a", "calc-b"}
            body = framed(
                {
                    "reasoning_content": "private-reason-second",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "calc-c",
                            "function": {"name": wire, "arguments": '{"expression":"5+8"}'},
                        }
                    ],
                },
                reason="tool_calls",
            )
        elif len(requests) == 3:
            native = [m for m in payload["messages"] if m["role"] == "assistant"]
            assert [m["reasoning_content"] for m in native] == [
                "private-reason-first",
                "private-reason-second",
            ]
            body = framed({"reasoning_content": "private-reason-final", "content": "13. 秘"})
        else:
            assert len(requests) == 4
            assert not any(m["role"] in {"assistant", "tool"} for m in payload["messages"])
            assert "Historical conversation record" in json.dumps(payload, ensure_ascii=False)
            assert "private-reason" not in json.dumps(payload)
            body = framed({"content": "Hello"})
        stream = SplitStream(body + "data: [DONE]\n\n")
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    use_provider(monkeypatch, provider)
    app = build_application(tmp_path / "application.db", seed_model_from_environment=False)
    try:
        settings = configured()
        app.store.create_model_config(
            "deepseek", settings.base_url, settings.model_id, None, profile=settings.profile
        )
        session = app.store.create_session()
        first = await app.runtime.submit(session, "Calculate 2+3, 3+5, then add the results")
        assert first.assistant_content == "13. 秘"
        second = await app.runtime.submit(session, "Hello")
        assert second.assistant_content == "Hello"
        assert sum(item.kind == "tool_result" for item in app.store.timeline(session)) == 3
        public = json.dumps([item.model_dump(mode="json") for item in app.store.timeline(session)])
        public += json.dumps(
            app.store.events(first.request_id) + app.store.events(second.request_id)
        )
        public += (tmp_path / "application.log").read_text(encoding="utf-8")
        assert "private-reason" not in public
        assert "fixture-provider-key" not in public
        assert all(stream.closed for stream in streams)
    finally:
        app.store.close()


@pytest.mark.anyio
async def test_usage_options_and_reasoning_override_are_actual_wire_fields(monkeypatch):
    requests = []

    def provider(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            text=framed({"content": "answer"}, usage={"prompt_tokens": 12, "completion_tokens": 7})
            + "data: [DONE]\n\n",
        )

    use_provider(monkeypatch, provider)
    settings = configured(options={"thinking": "disabled", "max_tokens": 1024})
    events = [
        event
        async for event in DeepSeekBackend().stream(
            (ContextMessage(role="user", content="Hello"),), (), settings, asyncio.Event()
        )
    ]
    assert isinstance(events[-1], ModelTurnCompleted)
    assert events[-1].usage.input_tokens == 12 and events[-1].usage.output_tokens == 7
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["max_tokens"] == 1024
    assert "tools" not in requests[0] and "temperature" not in requests[0]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body,kind",
    [
        (framed({"content": "partial"}, reason=None), "incomplete_stream"),
        (framed({"content": "partial"}, reason="length") + "data: [DONE]\n\n", "incomplete_stream"),
        (framed({"content": "partial"}), "incomplete_stream"),
        ("data: [DONE]\n\n", "incomplete_stream"),
        ('data: {"error":{"message":"private upstream error"}}\n\n', "upstream_stream_error"),
        ('data: {"choices":[],"choices":[]}\n\n', "malformed_stream"),
        (
            framed(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "a",
                            "function": {"name": "unadvertised", "arguments": "{}"},
                        }
                    ]
                },
                reason="tool_calls",
            )
            + "data: [DONE]\n\n",
            "protocol",
        ),
    ],
)
async def test_native_protocol_failures_do_not_return_a_dispatchable_turn(monkeypatch, body, kind):
    stream = SplitStream(body)
    use_provider(monkeypatch, lambda request: httpx.Response(200, stream=stream))
    with pytest.raises(ModelBackendError) as caught:
        await DeepSeekBackend().complete(
            (ContextMessage(role="user", content="Hello"),),
            (calculator_definition(),),
            configured(),
            asyncio.Event(),
        )
    assert caught.value.kind.value == kind
    assert "private upstream error" not in str(caught.value)
    assert stream.closed


@pytest.mark.anyio
async def test_cancel_during_native_body_read_closes_transport(monkeypatch):
    started, closed, cancellation = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Blocking(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        async def aclose(self):
            closed.set()

    use_provider(monkeypatch, lambda request: httpx.Response(200, stream=Blocking()))
    task = asyncio.create_task(DeepSeekBackend().complete((), (), configured(), cancellation))
    await started.wait()
    cancellation.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.anyio
@pytest.mark.parametrize("arguments", ["", "{", '{"x":NaN}', '{"x":1,"x":2}', "[1]", '{"x":1e999}'])
async def test_partial_ambiguous_or_nonobject_arguments_never_complete(monkeypatch, arguments):
    wire = ToolNameMap((calculator_definition(),)).to_wire("calculator.evaluate")
    body = (
        framed(
            {
                "tool_calls": [
                    {"index": 0, "id": "a", "function": {"name": wire, "arguments": arguments}}
                ]
            },
            reason="tool_calls",
        )
        + "data: [DONE]\n\n"
    )
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=body))
    with pytest.raises(ModelBackendError) as caught:
        await DeepSeekBackend().complete(
            (), (calculator_definition(),), configured(), asyncio.Event()
        )
    assert caught.value.kind.value == "malformed_stream"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
async def test_http_errors_do_not_expose_body_or_attest_replay_safety(monkeypatch, status):
    use_provider(monkeypatch, lambda request: httpx.Response(status, text="private-provider-body"))
    with pytest.raises(ModelBackendError) as caught:
        await DeepSeekBackend().complete((), (), configured(), asyncio.Event())
    assert caught.value.kind.value == "upstream_http"
    assert caught.value.retry_safe is False
    assert "private-provider-body" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "options",
    [
        {"temperature": 1},
        {"reasoning_effort": "unknown"},
        {"max_tokens": True},
        {"thinking": "disabled", "reasoning_effort": "high"},
    ],
)
async def test_unsupported_options_reject_before_http_client_creation(monkeypatch, options):
    def unexpected(**kwargs):
        pytest.fail("Unsupported options reached transport")

    monkeypatch.setattr("orion.models.providers.deepseek.httpx.AsyncClient", unexpected)
    with pytest.raises(ModelBackendError):
        await DeepSeekBackend().complete((), (), configured(options=options), asyncio.Event())


@pytest.mark.anyio
async def test_actual_wire_request_bound_is_checked_before_transport(monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("Oversized wire request reached transport")

    monkeypatch.setattr("orion.models.providers.deepseek.httpx.AsyncClient", unexpected)
    settings = configured(context_max_bytes=4096, request_max_bytes=4096)
    with pytest.raises(ModelBackendError, match="byte limit"):
        await DeepSeekBackend().complete(
            (ContextMessage(role="user", content="秘" * 2000),), (), settings, asyncio.Event()
        )
