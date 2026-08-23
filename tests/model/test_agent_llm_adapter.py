from __future__ import annotations

from unittest import mock

from src.model.agent_backend import (
    AgentModelBackend,
)
from src.model.agent_llm_adapter import (
    AgentLLMAdapter,
)
from src.model.llm_client import LLMClient


def _client() -> LLMClient:
    return LLMClient(
        base_url="http://model.test",
        model="test-model",
        timeout=5,
    )


def test_agent_adapter_implements_canonical_backend() -> None:
    adapter = AgentLLMAdapter(
        _client()
    )

    assert isinstance(
        adapter,
        AgentModelBackend,
    )


def test_agent_adapter_raw_call_uses_model_client() -> None:
    client = _client()

    client.generate = mock.Mock(
        return_value="ok"
    )

    adapter = AgentLLMAdapter(
        client
    )

    result = adapter.complete(
        "summarize"
    )

    assert result == "ok"

    client.generate.assert_called_once()

    call = client.generate.call_args

    assert call.args == (
        "summarize",
    )
    assert (
        call.kwargs["purpose"]
        == "response"
    )
    assert isinstance(
        call.kwargs["system_prompt"],
        str,
    )
    assert call.kwargs[
        "system_prompt"
    ]


def test_agent_adapter_health_check_delegates_to_client() -> None:
    client = _client()

    client.health_check = mock.Mock(
        return_value=True
    )

    adapter = AgentLLMAdapter(
        client
    )

    assert (
        adapter.health_check(
            timeout=2.0
        )
        is True
    )

    client.health_check.assert_called_once_with(
        timeout=2.0
    )


def test_agent_adapter_health_check_fails_closed() -> None:
    client = _client()

    client.health_check = mock.Mock(
        side_effect=RuntimeError(
            "offline"
        )
    )

    adapter = AgentLLMAdapter(
        client
    )

    assert (
        adapter.health_check()
        is False
    )
