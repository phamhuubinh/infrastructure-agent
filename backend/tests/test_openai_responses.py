from __future__ import annotations

import asyncio
import copy
import json

import httpx
import pytest
from provider_fixtures import SplitStream, use_provider

from orion.bootstrap import build_application
from orion.contracts import ContextMessage, ModelTurnCompleted
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.models.backend import ModelBackendError, ModelSettings
from orion.models.providers.openai_responses import OpenAIResponsesBackend
from orion.models.providers.tool_names import ToolNameMap
from orion.tool_runtime.calculator import calculator_definition


def configured(**changes):
    profile = ModelProfile.model_validate(
        {
            "profile_id": "responses-fixture",
            "provider_id": "openai",
            "protocol": "openai_responses",
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
        "event: "
        + value["type"]
        + "\ndata: "
        + json.dumps({**value, "sequence_number": index}, ensure_ascii=False)
        + "\n\n"
        for index, value in enumerate(events)
    )


def created():
    return event(
        "response.created", response={"id": "resp-fixture", "status": "in_progress", "output": []}
    )


def completed(items):
    return event(
        "response.completed",
        response={
            "id": "resp-fixture",
            "status": "completed",
            "output": items,
            "usage": {
                "input_tokens": 12,
                "output_tokens": 7,
                "input_tokens_details": {"cached_tokens": 3},
            },
        },
    )


def text_events(text="Hello 秘"):
    part = {"type": "output_text", "text": text, "annotations": []}
    item = {
        "type": "message",
        "id": "msg-fixture",
        "role": "assistant",
        "content": [part],
        "status": "completed",
    }
    common = {"item_id": item["id"], "output_index": 0, "content_index": 0}
    return [
        created(),
        event(
            "response.output_item.added",
            output_index=0,
            item={**item, "content": [], "status": "in_progress"},
        ),
        event("response.content_part.added", **common, part={**part, "text": ""}),
        event("response.output_text.delta", **common, delta=text[:3]),
        event("response.output_text.delta", **common, delta=text[3:]),
        event("response.output_text.done", **common, text=text),
        event("response.content_part.done", **common, part=part),
        event("response.output_item.done", output_index=0, item=item),
        completed([item]),
    ]


def tool_events(*, tool_name=None, arguments=None):
    wire = tool_name or ToolNameMap((calculator_definition(),)).to_wire("calculator.evaluate")
    reason = {
        "type": "reasoning",
        "id": "rs-fixture",
        "summary": [],
        "encrypted_content": "private-openai-encrypted-state",
    }
    calls = [
        {
            "type": "function_call",
            "id": "fc-" + str(index),
            "call_id": "calc-" + str(index),
            "name": wire,
            "arguments": (
                arguments
                if arguments is not None
                else json.dumps({"expression": "2+3" if index == 1 else "3+5"})
            ),
            "status": "completed",
        }
        for index in (1, 2)
    ]
    events = [
        created(),
        event(
            "response.output_item.added", output_index=0, item={**reason, "encrypted_content": None}
        ),
    ]
    events += [
        event(
            "response.reasoning_summary_text.delta",
            output_index=0,
            item_id=reason["id"],
            summary_index=0,
            delta="private-openai-summary",
        )
    ]
    events += [event("response.output_item.done", output_index=0, item=reason)]
    events += [
        event(
            "response.output_item.added",
            output_index=index,
            item={**item, "arguments": "", "status": "in_progress"},
        )
        for index, item in enumerate(calls, 1)
    ]
    for index in (2, 1):
        item = calls[index - 1]
        for fragment in (item["arguments"][:5], item["arguments"][5:]):
            events.append(
                event(
                    "response.function_call_arguments.delta",
                    output_index=index,
                    item_id=item["id"],
                    delta=fragment,
                )
            )
    for index, item in enumerate(calls, 1):
        events.extend(
            [
                event(
                    "response.function_call_arguments.done",
                    output_index=index,
                    item_id=item["id"],
                    arguments=item["arguments"],
                ),
                event("response.output_item.done", output_index=index, item=item),
            ]
        )
    return [*events, completed([reason, *calls])]


@pytest.mark.anyio
async def test_default_responses_encrypted_state_multiple_functions_then_later_user_history(
    tmp_path, monkeypatch
):
    requests, streams = [], []
    monkeypatch.setenv("ORION_FIXTURE_KEY", "fixture-provider-key")
    monkeypatch.setenv("ORION_LOG_PATH", str(tmp_path / "application.log"))

    def provider(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer fixture-provider-key"
        assert payload["model"] == "owner-selected-model" and payload["store"] is False
        assert payload["include"] == ["reasoning.encrypted_content"]
        assert isinstance(payload["instructions"], str) and "messages" not in payload
        assert all(
            tool["type"] == "function" and tool["strict"] is False and "." not in tool["name"]
            for tool in payload["tools"]
        )
        assert "previous_response_id" not in payload
        if len(requests) == 1:
            events = tool_events()
        elif len(requests) == 2:
            outputs = [
                item for item in payload["input"] if item.get("type") == "function_call_output"
            ]
            assert {item["call_id"] for item in outputs} == {"calc-1", "calc-2"}
            reasons = [item for item in payload["input"] if item.get("type") == "reasoning"]
            assert reasons[0]["encrypted_content"] == "private-openai-encrypted-state"
            assert (
                len([item for item in payload["input"] if item.get("type") == "function_call"]) == 2
            )
            events = text_events("The results are 5 and 8. 秘")
        else:
            assert len(requests) == 3
            assert all(item.get("role") == "user" for item in payload["input"])
            assert "Historical conversation record" in json.dumps(payload)
            assert "private-openai" not in json.dumps(payload)
            events = text_events("Hello")
        stream = SplitStream(framed(events))
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    use_provider(monkeypatch, provider)
    app = build_application(tmp_path / "application.db", seed_model_from_environment=False)
    try:
        bound = configured()
        app.store.create_model_config(
            "openai", bound.base_url, bound.model_id, None, profile=bound.profile
        )
        session = app.store.create_session()
        first = await app.runtime.submit(session, "Calculate 2+3 and 3+5")
        assert first.assistant_content == "The results are 5 and 8. 秘"
        assert (await app.runtime.submit(session, "Hello")).assistant_content == "Hello"
        assert sum(item.kind == "tool_result" for item in app.store.timeline(session)) == 2
        public = json.dumps([item.model_dump(mode="json") for item in app.store.timeline(session)])
        public += json.dumps(app.store.events(first.request_id))
        public += (tmp_path / "application.log").read_text(encoding="utf-8")
        assert "private-openai" not in public and "fixture-provider-key" not in public
        assert all(stream.closed for stream in streams)
    finally:
        app.store.close()


@pytest.mark.anyio
async def test_usage_and_explicit_controls_are_native_request_fields(monkeypatch):
    payloads = []

    def provider(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, text=framed(text_events()))

    use_provider(monkeypatch, provider)
    settings = configured(options={"max_output_tokens": 512, "reasoning_effort": "high"})
    events = [
        value
        async for value in OpenAIResponsesBackend().stream(
            (ContextMessage(role="user", content="Hello"),), (), settings, asyncio.Event()
        )
    ]
    assert isinstance(events[-1], ModelTurnCompleted)
    assert events[-1].usage.input_tokens == 12 and events[-1].usage.output_tokens == 7
    assert payloads[0]["reasoning"] == {"effort": "high"}
    assert payloads[0]["max_output_tokens"] == 512 and "tools" not in payloads[0]


@pytest.mark.anyio
@pytest.mark.parametrize("arguments", ["", "{", '{"x":NaN}', '{"x":1,"x":2}', "[1]"])
async def test_partial_ambiguous_nonobject_tool_json_never_completes(monkeypatch, arguments):
    use_provider(
        monkeypatch,
        lambda request: httpx.Response(200, text=framed(tool_events(arguments=arguments))),
    )
    with pytest.raises(ModelBackendError) as caught:
        await OpenAIResponsesBackend().complete(
            (), (calculator_definition(),), configured(), asyncio.Event()
        )
    assert caught.value.kind.value == "malformed_stream"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "fault",
    [
        "missing_terminal",
        "wrong_response",
        "wrong_item",
        "arguments_contradiction",
        "missing_item_done",
        "duplicate_terminal",
        "missing_encrypted",
        "incomplete",
    ],
)
async def test_lifecycle_identity_state_failures_never_authorize_dispatch(monkeypatch, fault):
    events = copy.deepcopy(tool_events())
    if fault == "missing_terminal":
        events.pop()
    elif fault == "wrong_response":
        events[-1]["response"]["id"] = "wrong"
    elif fault == "wrong_item":
        events[6]["item_id"] = "wrong"
    elif fault == "arguments_contradiction":
        next(value for value in events if value["type"] == "response.function_call_arguments.done")[
            "arguments"
        ] = "{}"
    elif fault == "missing_item_done":
        events = [value for value in events if value["type"] != "response.output_item.done"]
    elif fault == "duplicate_terminal":
        events.append(events[-1])
    elif fault == "missing_encrypted":
        events[-1]["response"]["output"][0]["encrypted_content"] = None
    else:
        events[-1] = event("response.incomplete", response={"id": "resp-fixture"})
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=framed(events)))
    with pytest.raises(ModelBackendError) as caught:
        await OpenAIResponsesBackend().complete(
            (), (calculator_definition(),), configured(), asyncio.Event()
        )
    assert caught.value.kind.value in {"malformed_stream", "incomplete_stream"}


@pytest.mark.anyio
async def test_cancel_awaits_native_body_cleanup(monkeypatch):
    started, closed, cancellation = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Blocking(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        async def aclose(self):
            closed.set()

    use_provider(monkeypatch, lambda request: httpx.Response(200, stream=Blocking()))
    task = asyncio.create_task(
        OpenAIResponsesBackend().complete((), (), configured(), cancellation)
    )
    await started.wait()
    cancellation.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
async def test_http_error_status_never_replays_or_exposes_body(monkeypatch, status):
    use_provider(monkeypatch, lambda request: httpx.Response(status, text="private-openai-body"))
    with pytest.raises(ModelBackendError) as caught:
        await OpenAIResponsesBackend().complete((), (), configured(), asyncio.Event())
    assert caught.value.kind.value == "upstream_http" and not caught.value.retry_safe
    assert "private-openai-body" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "options",
    [
        {"temperature": 1},
        {"max_output_tokens": True},
        {"reasoning_effort": "unsupported"},
        {"store": True},
    ],
)
async def test_unsupported_options_reject_before_transport(monkeypatch, options):
    def unexpected(**kwargs):
        pytest.fail("Unsupported Responses options reached HTTP transport")

    monkeypatch.setattr("orion.models.providers.openai_responses.httpx.AsyncClient", unexpected)
    with pytest.raises(ModelBackendError):
        await OpenAIResponsesBackend().complete(
            (), (), configured(options=options), asyncio.Event()
        )


@pytest.mark.anyio
async def test_native_wire_bound_rejects_before_transport(monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("Oversized Responses request reached HTTP transport")

    monkeypatch.setattr("orion.models.providers.openai_responses.httpx.AsyncClient", unexpected)
    with pytest.raises(ModelBackendError, match="byte limit"):
        await OpenAIResponsesBackend().complete(
            (ContextMessage(role="user", content="秘" * 2000),),
            (),
            configured(context_max_bytes=4096, request_max_bytes=4096),
            asyncio.Event(),
        )


@pytest.mark.anyio
async def test_private_state_rejects_new_request_before_transport(monkeypatch):
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=framed(tool_events())))
    backend, settings = OpenAIResponsesBackend(), configured()
    turn = await backend.complete((), (calculator_definition(),), settings, asyncio.Event())

    def unexpected(**kwargs):
        pytest.fail("Cross-request private state reached HTTP transport")

    monkeypatch.setattr("orion.models.providers.openai_responses.httpx.AsyncClient", unexpected)
    with pytest.raises(ModelBackendError) as caught:
        await backend.complete(
            (),
            (calculator_definition(),),
            settings.model_copy(
                update={
                    "provider_continuation": turn.provider_continuation,
                    "request_binding": "another",
                }
            ),
            asyncio.Event(),
        )
    assert caught.value.kind.value == "protocol"


@pytest.mark.anyio
async def test_tool_error_is_function_call_output_with_exact_call_id(monkeypatch):
    requests = []

    def provider(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 2:
            result = next(
                item
                for item in payload["input"]
                if item.get("type") == "function_call_output" and item["call_id"] == "calc-1"
            )
            assert result["type"] == "function_call_output" and result["call_id"] == "calc-1"
            assert json.loads(result["output"])["status"] == "error"
            assert "is_error" not in result
        return httpx.Response(
            200, text=framed(tool_events() if len(requests) == 1 else text_events())
        )

    use_provider(monkeypatch, provider)
    backend, settings = OpenAIResponsesBackend(), configured()
    tools = (calculator_definition(),)
    turn = await backend.complete((), tools, settings, asyncio.Event())
    await backend.complete(
        (
            ContextMessage(role="assistant", content="", tool_calls=turn.tool_calls),
            ContextMessage(
                role="tool",
                tool_call_id="calc-1",
                tool_name="calculator.evaluate",
                content='{"status":"error","error":{"code":"fixture"}}',
            ),
            ContextMessage(
                role="tool",
                tool_call_id="calc-2",
                tool_name="calculator.evaluate",
                content='{"status":"success","data":{"value":8}}',
            ),
        ),
        tools,
        settings.model_copy(update={"provider_continuation": turn.provider_continuation}),
        asyncio.Event(),
    )


@pytest.mark.anyio
async def test_credential_echo_is_redacted_in_native_complete_and_private_payload_stays_private(
    monkeypatch,
):
    use_provider(
        monkeypatch,
        lambda request: httpx.Response(
            200, text=framed(text_events("Before fixture-provider-key after"))
        ),
    )
    turn = await OpenAIResponsesBackend().complete((), (), configured(), asyncio.Event())
    assert turn.assistant.content == "Before [REDACTED] after"
    assert "fixture-provider-key" not in turn.model_dump_json() + repr(turn)


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["usage", "sequence", "text", "error_metadata", "failed"])
async def test_completed_text_and_metadata_must_match_observed_stream(monkeypatch, fault):
    events = text_events()
    if fault == "usage":
        events[-1]["response"]["usage"]["output_tokens"] = True
    elif fault == "text":
        events[5]["text"] = "contradictory"
    elif fault == "error_metadata":
        events[-1]["response"]["error"] = {"message": "private"}
    elif fault == "failed":
        events[-1] = event("response.failed", response={"error": "private"})
    body = framed(events)
    if fault == "sequence":
        body = body.replace('"sequence_number": 1}', '"sequence_number": 0}', 1)
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=body))
    with pytest.raises(ModelBackendError):
        await OpenAIResponsesBackend().complete((), (), configured(), asyncio.Event())


@pytest.mark.anyio
async def test_native_refusal_parts_are_visible_text_without_function_authority(monkeypatch):
    events = copy.deepcopy(text_events("I cannot help with that request."))

    def project(value):
        if isinstance(value, list):
            for item in value:
                project(item)
        elif isinstance(value, dict):
            kind = value.get("type")
            if kind == "output_text":
                value["type"] = "refusal"
                value["refusal"] = value.pop("text")
                value.pop("annotations", None)
            elif kind in {"response.output_text.delta", "response.output_text.done"}:
                value["type"] = kind.replace("output_text", "refusal")
                if "text" in value:
                    value["refusal"] = value.pop("text")
            for item in list(value.values()):
                project(item)

    project(events)
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=framed(events)))
    turn = await OpenAIResponsesBackend().complete((), (), configured(), asyncio.Event())
    assert turn.assistant.content == "I cannot help with that request."
    assert not turn.tool_calls
