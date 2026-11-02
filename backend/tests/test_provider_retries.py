from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from test_provider_registry import configured_settings, registered

from orion.access import LocalAccessAdapter
from orion.chat.runtime import ChatRuntime, RequestFailed
from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ModelTurn,
    ModelTurnCompleted,
    MutationMode,
    ToolDefinition,
    ToolResult,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelBackendErrorKind
from orion.models.providers.claude import ADAPTER_ID as CLAUDE_ADAPTER_ID
from orion.models.providers.claude import CLAUDE_OPTIONS, ClaudeBackend
from orion.models.providers.deepseek import ADAPTER_ID, DEEPSEEK_OPTIONS, DeepSeekBackend
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.models.providers.openai_responses import ADAPTER_ID as RESPONSES_ADAPTER_ID
from orion.models.providers.openai_responses import RESPONSES_OPTIONS, OpenAIResponsesBackend
from orion.models.registry import ProviderRegistry
from orion.tool_runtime.mutation_authorization import MutationAuthorizationPolicy
from orion.tool_runtime.registry import ToolRegistryBuilder


class FailingConnection(ModelBackend):
    def __init__(self, *, failures=1, safe=True, event=None, cancellation=None):
        self.attempts = 0
        self.failures = failures
        self.safe = safe
        self.event = event
        self.cancellation = cancellation
        self.closed = 0

    async def stream(self, messages, tools, settings, cancellation):
        self.attempts += 1
        try:
            if self.attempts <= self.failures:
                if self.event is not None:
                    yield self.event
                if self.cancellation is not None:
                    self.cancellation.set()
                raise ModelBackendError(
                    "Connection failed.",
                    kind=ModelBackendErrorKind.CONNECTION,
                    retry_safe=self.safe,
                )
            yield ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content="done")))
        finally:
            self.closed += 1


@pytest.mark.anyio
@pytest.mark.parametrize("retries", [0, 1, 2])
async def test_safe_connect_retries_are_bounded_and_close_every_attempt(retries):
    backend = FailingConnection(failures=3)
    registry = ProviderRegistry((registered(backend),))
    with pytest.raises(ModelBackendError, match="Connection failed"):
        await registry.complete(
            (), (), configured_settings(safe_transport_retries=retries), asyncio.Event()
        )
    assert backend.attempts == retries + 1 == backend.closed


@pytest.mark.anyio
async def test_safe_connect_can_recover_without_falling_back():
    backend = FailingConnection()
    turn = await ProviderRegistry((registered(backend),)).complete(
        (), (), configured_settings(safe_transport_retries=1), asyncio.Event()
    )
    assert turn.assistant.content == "done"
    assert backend.attempts == backend.closed == 2


@pytest.mark.anyio
@pytest.mark.parametrize("fragment", [None, "visible", "fixture-"])
async def test_uncertain_request_or_any_received_delta_prevents_replay(fragment):
    # The last fragment is held by secret redaction, but still counts as received.
    backend = FailingConnection(
        safe=fragment is not None,
        event=AssistantDelta(content=fragment) if fragment else None,
    )
    settings = configured_settings(safe_transport_retries=2).model_copy(
        update={"api_key": "fixture-protected-key"}
    )
    with pytest.raises(ModelBackendError):
        await ProviderRegistry((registered(backend),)).complete((), (), settings, asyncio.Event())
    assert backend.attempts == backend.closed == 1


@pytest.mark.anyio
async def test_cancel_between_attempts_prevents_retry():
    cancellation = asyncio.Event()
    backend = FailingConnection(cancellation=cancellation)
    with pytest.raises(asyncio.CancelledError):
        await ProviderRegistry((registered(backend),)).complete(
            (), (), configured_settings(safe_transport_retries=2), cancellation
        )
    assert backend.attempts == backend.closed == 1


@pytest.mark.parametrize(
    "error,safe",
    [
        (httpx.ConnectError("private"), True),
        (httpx.ConnectTimeout("private"), True),
        (httpx.ReadError("private"), False),
        (httpx.ReadTimeout("private"), False),
        (httpx.WriteError("private"), False),
        (httpx.WriteTimeout("private"), False),
        (httpx.PoolTimeout("private"), False),
        (httpx.RemoteProtocolError("private"), False),
    ],
)
def test_transport_retry_attestation_excludes_uncertain_delivery(error, safe):
    classified = OpenAICompatibleBackend._transport_error(error)
    assert classified.retry_safe is safe
    assert "private" not in str(classified)


@pytest.mark.anyio
@pytest.mark.parametrize("validated", [False, True])
async def test_early_consumer_close_synchronously_closes_all_registry_layers(validated):
    class Source(ModelBackend):
        closed = False

        async def stream(self, *args):
            try:
                yield AssistantDelta(content="visible")
                await asyncio.Event().wait()
            finally:
                self.closed = True

    backend = Source()
    registry = ProviderRegistry((registered(backend),))
    method = registry.validated_stream if validated else registry.stream
    stream = method((), (), configured_settings(), asyncio.Event())
    await anext(stream)
    await stream.aclose()
    assert backend.closed


@pytest.mark.anyio
async def test_connection_error_after_response_headers_is_never_retried(monkeypatch):
    from test_profile_limits import profile, settings

    from orion.models.registry import AdapterRegistration

    requests, closed = [], []

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ConnectError("private post-header failure")
            yield b"unreachable"

        async def aclose(self):
            closed.append(True)

    def provider(request):
        requests.append(request)
        return httpx.Response(200, stream=BrokenBody())

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(provider), **kwargs),
    )
    registry = ProviderRegistry(
        (
            AdapterRegistration(
                "compatible.fixture",
                "openai_compatible",
                "chat_completions",
                OpenAICompatibleBackend(),
                {"type": "object", "additionalProperties": False},
            ),
        )
    )
    with pytest.raises(ModelBackendError) as caught:
        await registry.complete(
            (), (), settings(profile(safe_transport_retries=2)), asyncio.Event()
        )
    assert caught.value.retry_safe is False
    assert len(requests) == 1
    assert closed == [True]


@pytest.mark.anyio
@pytest.mark.parametrize("safe", [True, False])
@pytest.mark.parametrize("vendor", ["compatible", "deepseek", "claude", "openai"])
async def test_real_http_retry_after_tool_result_never_reexecutes_mutation(
    store, monkeypatch, safe, vendor
):
    from test_profile_limits import profile, settings

    from orion.contracts.profiles import ModelCapabilities
    from orion.models.registry import AdapterRegistration

    requests, mutations = [], []
    native = vendor != "compatible"

    def provider(request):
        payload = json.loads(request.content)
        requests.append(payload)
        wire_name = (
            payload["tools"][0]["name"]
            if vendor in {"claude", "openai"}
            else payload["tools"][0]["function"]["name"]
        )
        if len(requests) == 1:
            delta = {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "mutation-once",
                        "function": {
                            "name": wire_name,
                            "arguments": '{"target_ref":"fixture-target"}',
                        },
                    }
                ]
            }
        elif len(requests) == 2:
            conversation = payload.get("input", payload.get("messages", []))
            assert any(
                message.get("role") == "tool"
                or message.get("type") == "function_call_output"
                or any(
                    block.get("type") == "tool_result"
                    for block in message.get("content", [])
                    if isinstance(block, dict)
                )
                for message in conversation
            )
            error = httpx.ConnectError if safe else httpx.ReadError
            raise error("uncertain upstream private message")
        else:
            delta = {"content": "done"}
        if vendor == "openai":
            from test_openai_responses import completed, created, event, framed, text_events

            events = text_events("done")
            if "tool_calls" in delta:
                item = {
                    "type": "function_call",
                    "id": "fc-fixture",
                    "call_id": "mutation-once",
                    "name": wire_name,
                    "arguments": '{"target_ref":"fixture-target"}',
                }
                events = [
                    created(),
                    event(
                        "response.output_item.added", output_index=0, item={**item, "arguments": ""}
                    ),
                    event(
                        "response.function_call_arguments.delta",
                        output_index=0,
                        item_id=item["id"],
                        delta=item["arguments"],
                    ),
                    event(
                        "response.function_call_arguments.done",
                        output_index=0,
                        item_id=item["id"],
                        arguments=item["arguments"],
                    ),
                    event("response.output_item.done", output_index=0, item=item),
                    completed([item]),
                ]
            return httpx.Response(200, text=framed(events))
        if vendor == "claude":
            from test_claude_adapter import event, framed, start, text_events

            events = text_events("done")
            if "tool_calls" in delta:
                events = [
                    start(),
                    event(
                        "content_block_start",
                        index=0,
                        content_block={
                            "type": "tool_use",
                            "id": "mutation-once",
                            "name": wire_name,
                            "input": {"target_ref": "fixture-target"},
                        },
                    ),
                    event("content_block_stop", index=0),
                    event(
                        "message_delta",
                        delta={"stop_reason": "tool_use"},
                        usage={"output_tokens": 4},
                    ),
                    event("message_stop"),
                ]
            return httpx.Response(200, text=framed(events))
        return httpx.Response(
            200,
            text="data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "delta": delta,
                            "finish_reason": (
                                "tool_calls" if native and "tool_calls" in delta else "stop"
                            ),
                        }
                    ]
                }
            )
            + "\n\ndata: [DONE]\n\n",
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(provider), **kwargs),
    )

    def mutation(call):
        mutations.append(call.call_id)
        return ToolResult(
            call_id=call.call_id, tool_name=call.tool_name, status="success", data={"changed": True}
        )

    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="fixture.change",
            handler_key="fixture.change",
            description="Fixture mutation",
            operation_kind="mutation",
            input_schema={
                "type": "object",
                "properties": {"target_ref": {"type": "string"}},
                "required": ["target_ref"],
                "additionalProperties": False,
            },
        ),
        mutation,
    )
    adapter_id, provider_id, protocol, backend_type, option_schema = {
        "compatible": (
            "compatible.fixture",
            "openai_compatible",
            "chat_completions",
            OpenAICompatibleBackend,
            {"type": "object", "additionalProperties": False},
        ),
        "deepseek": (ADAPTER_ID, "deepseek", "chat_completions", DeepSeekBackend, DEEPSEEK_OPTIONS),
        "claude": (
            CLAUDE_ADAPTER_ID,
            "claude",
            "anthropic_messages",
            ClaudeBackend,
            CLAUDE_OPTIONS,
        ),
        "openai": (
            RESPONSES_ADAPTER_ID,
            "openai",
            "openai_responses",
            OpenAIResponsesBackend,
            RESPONSES_OPTIONS,
        ),
    }[vendor]
    backend = ProviderRegistry(
        (
            AdapterRegistration(
                adapter_id,
                provider_id,
                protocol,
                backend_type(),
                option_schema,
            ),
        )
    )
    bound = settings(
        profile(
            provider_id=provider_id,
            protocol=protocol,
            safe_transport_retries=2,
            capabilities=ModelCapabilities(
                streaming=True,
                tools=True,
                tool_result_continuation=True,
            ),
        )
    ).model_copy(update={"api_key": "fixture-provider-key"})
    chat = ChatRuntime(
        store,
        backend,
        builder.freeze(),
        LocalAccessAdapter(),
        settings_provider=lambda: bound,
        mutation_authorization=MutationAuthorizationPolicy(
            frozenset({("fixture.change", "fixture-target")})
        ),
    )
    session = store.create_session()
    store.set_session_mutation_mode(session, MutationMode.AUTO)
    if safe:
        result = await chat.submit(session, "Apply the fixture change")
        assert result.assistant_content == "done"
        assert len(requests) == 3
    else:
        with pytest.raises(RequestFailed):
            await chat.submit(session, "Apply the fixture change")
        assert len(requests) == 2
    assert mutations == ["mutation-once"]
    assert sum(item.kind == "tool_result" for item in store.timeline(session)) == 1
