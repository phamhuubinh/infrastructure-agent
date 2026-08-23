from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from src.model.providers.anthropic_agent_adapter import (
    AnthropicAgentAdapter,
)


class FakeMessages:
    def __init__(
        self,
        responses: list[object],
    ) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def create(
        self,
        **kwargs: object,
    ) -> SimpleNamespace:
        self.calls.append(dict(kwargs))
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response  # type: ignore[return-value]


class FakeClient:
    def __init__(
        self,
        responses: list[object],
    ) -> None:
        self.messages = FakeMessages(
            responses
        )


def response(
    text: str = "ok",
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(
                type="text",
                text=text,
            )
        ],
        usage=SimpleNamespace(
            input_tokens=30,
            output_tokens=9,
        ),
        model="claude-fake",
    )


@pytest.fixture
def fake_client(
    monkeypatch,
) -> FakeClient:
    client = FakeClient([])

    module = ModuleType("anthropic")
    module.Anthropic = (  # type: ignore[attr-defined]
        lambda **_kwargs: client
    )

    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        module,
    )

    return client


def adapter() -> AnthropicAgentAdapter:
    return AnthropicAgentAdapter(
        api_key="fake-key",
        model="claude-fake",
    )


def test_complete_records_usage(
    fake_client: FakeClient,
) -> None:
    fake_client.messages.responses.append(
        response("answer")
    )

    backend = adapter()

    assert backend.complete("hello") == "answer"
    assert backend.last_usage is not None
    assert backend.last_usage.input_tokens == 30
    assert (
        backend.last_usage
        .estimated_input_tokens
        is not None
    )


def test_failed_complete_clears_previous_usage(
    fake_client: FakeClient,
) -> None:
    fake_client.messages.responses.extend(
        [
            response(),
            RuntimeError("down"),
        ]
    )

    backend = adapter()

    assert backend.complete("one") == "ok"
    assert backend.last_usage is not None

    with pytest.raises(
        RuntimeError,
        match="down",
    ):
        backend.complete("two")

    assert backend.last_usage is None


def test_health_check_fails_closed(
    fake_client: FakeClient,
) -> None:
    fake_client.messages.responses.append(
        RuntimeError("down")
    )

    assert adapter().health_check() is False
