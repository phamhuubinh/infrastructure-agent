from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import httpx
import pytest

from orion.contracts import ContextMessage
from orion.models.backend import ModelBackendError, ModelSettings


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("body", "error_kind", "json_state", "done"),
    [
        (
            'data: {"choices":[{"delta":{"reasoning_content":"secret thought"},'
            '"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
            "empty_turn",
            [],
            True,
        ),
        (
            'data: {"choices":[{"delta":{"role":"assistant","content":""}}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":216,"completion_tokens":2}}\n\n'
            "data: [DONE]\n\n",
            "empty_turn",
            [],
            True,
        ),
        (
            'data: {"error":{"message":"secret provider error","code":"secret"}}\n\n'
            "data: [DONE]\n\n",
            "upstream_stream_error",
            [],
            False,
        ),
        (
            'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            'data: {"object":"error","message":"secret provider error"}\n\n'
            "data: [DONE]\n\n",
            "upstream_stream_error",
            [],
            False,
        ),
        (
            'data: {"choices":[{"delta":{"content":"sensitive text"},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n",
            None,
            [],
            True,
        ),
        ('data: {"choices":[{"delta":{"content":"secret"}}]}\n\n', "incomplete_stream", [], False),
        ("data: not-json-secret\n\n", "malformed_stream", [], False),
        (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"id","function":'
            '{"name":"calculator.evaluate","arguments":"{"}}]},"finish_reason":"tool_calls"}]}\n\n'
            "data: [DONE]\n\n",
            "malformed_stream",
            ["incomplete_or_malformed"],
            True,
        ),
        (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"id","function":'
            '{"name":"calculator.evaluate","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}\n\n'
            "data: [DONE]\n\n",
            None,
            ["valid_object"],
            True,
        ),
    ],
)
async def test_diagnostics_observe_without_changing_adapter_or_leaking_payload(
    monkeypatch, body, error_kind, json_state, done
):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module("semantic_stream_diagnostics")
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))
    observer = module.DiagnosticProvider()
    settings = ModelSettings(
        provider_type="openai_compatible", base_url="http://fixture.invalid/v1", model_id="fixture"
    )
    try:
        events = [
            event
            async for event in observer.stream(
                (ContextMessage(role="system", content="secret instruction"),),
                (),
                settings,
                asyncio.Event(),
            )
        ]
        assert error_kind is None
        assert events[-1].__class__.__name__ == "ModelTurnCompleted"
    except ModelBackendError as error:
        assert error.kind.value == error_kind
        assert "secret" not in str(error)
    record = observer.diagnostics[0]
    assert record["adapter_error_category"] == error_kind
    assert record["http_status"] == 200
    assert record["roles"] == ["system"]
    assert record["sse_done"] is done
    assert record["tool_argument_json"] == json_state
    assert record["elapsed_ms"] >= 0
    assert "secret" not in json.dumps(record)
    assert "sensitive" not in json.dumps(record)
    if error_kind == "empty_turn":
        assert record["stage"] == "build_turn"
        assert record["exception_types"] == ["ModelBackendError"]
        assert record["sse_ended_normally"] is True
    if "reasoning_content" in body:
        # Valid SSE framing is not a usable completed turn: no answer or tool call.
        assert record["normalized_event_counts"] == {"ReasoningDelta": 1}
