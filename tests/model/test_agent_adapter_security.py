from __future__ import annotations

import pytest

from src.model.agent_adapter import (
    AgentModelAdapter,
    AgentModelError,
    AgentProviderRequest,
)


class ExplodingProvider:
    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ):
        raise RuntimeError(
            "provider failed "
            "api_key=sk-abcdefghijklmnopqrstuvwxyz "
            "Authorization: Bearer top-secret-token "
            "https://user:password@example.com/path"
        )


def test_provider_failure_redacts_credentials() -> None:
    adapter = AgentModelAdapter(
        (ExplodingProvider(),)
    )

    with pytest.raises(AgentModelError) as captured:
        adapter.decide(
            system_prompt="system",
            user_prompt="user",
        )

    message = str(captured.value)

    assert "abcdefghijklmnopqrstuvwxyz" not in message
    assert "top-secret-token" not in message
    assert "password@example.com" not in message
    assert "<redacted>" in message

    failure = captured.value.failures[0]
    assert "top-secret-token" not in failure.message
