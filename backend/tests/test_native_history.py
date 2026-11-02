from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from provider_fixtures import use_provider
from test_claude_adapter import configured as claude_settings
from test_claude_adapter import framed as claude_frames
from test_claude_adapter import tool_events as claude_tools
from test_deepseek_adapter import configured as deepseek_settings
from test_deepseek_adapter import framed as deepseek_frame
from test_openai_responses import configured as openai_settings
from test_openai_responses import framed as openai_frames
from test_openai_responses import tool_events as openai_tools

from orion.contracts import ContextMessage
from orion.models.backend import ModelBackendError
from orion.models.providers.claude import ClaudeBackend
from orion.models.providers.deepseek import DeepSeekBackend
from orion.models.providers.openai_responses import OpenAIResponsesBackend
from orion.models.providers.tool_names import ToolNameMap
from orion.tool_runtime.calculator import calculator_definition


@pytest.mark.anyio
@pytest.mark.parametrize("vendor", ["deepseek", "claude", "openai"])
@pytest.mark.parametrize("fault", ["missing", "orphan", "duplicate", "user_between"])
async def test_native_history_requires_exact_complete_tool_exchange_before_http(
    monkeypatch, vendor, fault
):
    tools = (calculator_definition(),)
    if vendor == "claude":
        backend, settings, body = ClaudeBackend(), claude_settings(), claude_frames(claude_tools())
    elif vendor == "openai":
        backend, settings, body = (
            OpenAIResponsesBackend(),
            openai_settings(),
            openai_frames(openai_tools()),
        )
    else:
        backend, settings = DeepSeekBackend(), deepseek_settings()
        wire = ToolNameMap(tools).to_wire("calculator.evaluate")
        body = (
            deepseek_frame(
                {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": "calc-" + str(index),
                            "function": {
                                "name": wire,
                                "arguments": json.dumps({"expression": "2+3"}),
                            },
                        }
                        for index in (0, 1)
                    ]
                },
                reason="tool_calls",
            )
            + "data: [DONE]\n\n"
        )
    use_provider(monkeypatch, lambda request: httpx.Response(200, text=body))
    turn = await backend.complete((), tools, settings, asyncio.Event())
    assistant = ContextMessage(role="assistant", content="", tool_calls=turn.tool_calls)
    results = tuple(
        ContextMessage(
            role="tool",
            content='{"status":"success","data":{"value":5}}',
            tool_name=call.tool_name,
            tool_call_id=call.call_id,
        )
        for call in turn.tool_calls
    )
    if fault == "missing":
        messages = (assistant, results[0])
    elif fault == "orphan":
        messages = results
    elif fault == "duplicate":
        messages = (assistant, *results, assistant, *results)
    else:
        messages = (assistant, ContextMessage(role="user", content="new request"), *results)

    def unexpected(**kwargs):
        pytest.fail("Malformed native exchange reached HTTP transport")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected)
    with pytest.raises(ModelBackendError) as caught:
        await backend.complete(
            messages,
            tools,
            settings.model_copy(update={"provider_continuation": turn.provider_continuation}),
            asyncio.Event(),
        )
    assert caught.value.kind.value == "protocol"
