from __future__ import annotations

import asyncio

import pytest

from orion.contracts import ContextMessage, ModelToolCall
from orion.models.backend import ModelBackendError, ModelSettings
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.tools.calculator.tool import calculator_definition


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": "Done.", "tool_calls": []}}]}


class FakeClient:
    captured: dict[str, object] = {}

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        return None

    async def post(self, url: str, headers, json) -> FakeResponse:  # type: ignore[no-untyped-def]
        self.captured = {"url": url, "headers": headers, "json": json}
        type(self).captured = self.captured
        return FakeResponse()


@pytest.mark.anyio
async def test_adapter_serializes_tool_result_continuation(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("orion.models.providers.openai_compatible.httpx.AsyncClient", FakeClient)
    backend = OpenAICompatibleBackend()
    turn = await backend.complete(
        (
            ContextMessage(role="user", content="calculate"),
            ContextMessage(
                role="assistant",
                content="",
                tool_calls=(
                    ModelToolCall(
                        call_id="calc-1",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "2+2"},
                    ),
                ),
            ),
            ContextMessage(
                role="tool",
                content='{"status":"success","data":{"value":4}}',
                tool_call_id="calc-1",
                tool_name="calculator.evaluate",
            ),
        ),
        (calculator_definition(),),
        ModelSettings(
            provider_type="openai_compatible", base_url="http://local/v1", model_id="local"
        ),
        asyncio.Event(),
    )

    payload = FakeClient.captured["json"]
    assert isinstance(payload, dict)
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert messages[-1]["role"] == "tool"
    assert messages[-1]["tool_call_id"] == "calc-1"
    assert messages[-2]["tool_calls"][0]["function"]["name"] == "calculator.evaluate"
    assert "handler_key" not in str(payload["tools"])
    assert turn.assistant.content == "Done."


def test_adapter_rejects_an_empty_provider_turn() -> None:
    with pytest.raises(ModelBackendError, match="invalid tool-call response"):
        OpenAICompatibleBackend()._normalize({"choices": [{"message": {}}]})


def test_adapter_normalizes_assistant_only_turn() -> None:
    turn = OpenAICompatibleBackend()._normalize({"choices": [{"message": {"content": "Answer."}}]})

    assert turn.assistant is not None
    assert turn.assistant.content == "Answer."
    assert not turn.tool_calls


def test_adapter_normalizes_tool_only_turn() -> None:
    turn = OpenAICompatibleBackend()._normalize(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "calculator.evaluate",
                                    "arguments": '{"expression":"2+2"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
    )

    assert turn.assistant is None
    assert turn.tool_calls[0].call_id == "call-1"


def test_adapter_normalizes_assistant_and_tool_call_turn() -> None:
    turn = OpenAICompatibleBackend()._normalize(
        {
            "choices": [
                {
                    "message": {
                        "content": "I will calculate.",
                        "tool_calls": [
                            {
                                "id": "call-2",
                                "function": {
                                    "name": "calculator.evaluate",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ]
        }
    )

    assert turn.assistant is not None
    assert turn.assistant.content == "I will calculate."
    assert len(turn.tool_calls) == 1
