"""Deterministic tests for AnthropicAssessmentAdapter usage-state safety.

No network and no real SDK: a fake ``anthropic`` module is injected so
``last_usage`` reset semantics are verified without the package installed.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from src.model.providers.anthropic_adapter import AnthropicAssessmentAdapter
from src.pipeline.assessment_request import AssessmentRequest


class FakeAnthropicMessages:
    """Scripted Messages API double; responses may be payloads or errors."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def create(self, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeAnthropicClient:
    def __init__(self, responses: list[object]) -> None:
        self.messages = FakeAnthropicMessages(responses)


@pytest.fixture
def fake_client(monkeypatch) -> FakeAnthropicClient:
    client = FakeAnthropicClient([])
    module = ModuleType("anthropic")
    module.Anthropic = lambda **_kwargs: client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return client


def _response(text: str = "ok", *, input_tokens: int = 30, output_tokens: int = 90):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        model="claude-fake",
    )


def test_assess_raw_success_then_failure_leaves_no_stale_usage(fake_client) -> None:
    fake_client.messages._responses.extend([_response(), RuntimeError("down")])
    adapter = AnthropicAssessmentAdapter(api_key="fake-key")

    assert adapter.assess_raw("hello") == "ok"
    assert adapter.last_usage is not None
    assert adapter.last_usage.input_tokens == 30
    # No thinking block was present, so the adapter may declare visible == total.
    assert adapter.last_usage.visible_output_tokens == 90

    with pytest.raises(RuntimeError):
        adapter.assess_raw("hello again")
    # The failed call must never expose the previous call's usage.
    assert adapter.last_usage is None


def test_usage_recovers_after_a_failed_raw_call(fake_client) -> None:
    fake_client.messages._responses.extend([RuntimeError("down"), _response()])
    adapter = AnthropicAssessmentAdapter(api_key="fake-key")

    with pytest.raises(RuntimeError):
        adapter.assess_raw("hello")
    assert adapter.last_usage is None

    assert adapter.assess_raw("hello again") == "ok"
    assert adapter.last_usage is not None
    assert adapter.last_usage.input_tokens == 30


def test_structured_assessment_failure_does_not_keep_previous_usage(
    fake_client,
) -> None:
    fake_client.messages._responses.extend(
        [_response(text="all fine"), RuntimeError("down")]
    )
    adapter = AnthropicAssessmentAdapter(api_key="fake-key")

    assert adapter.assess(AssessmentRequest(raw_request="check cpu")) == "all fine"
    assert adapter.last_usage is not None
    assert adapter.last_usage.purpose == "assessment"

    failed = adapter.assess(AssessmentRequest(raw_request="check cpu again"))
    assert failed == ""
    assert adapter.last_usage is None


def test_structured_usage_recovers_after_a_failed_call(fake_client) -> None:
    fake_client.messages._responses.extend(
        [RuntimeError("down"), _response(text="recovered")]
    )
    adapter = AnthropicAssessmentAdapter(api_key="fake-key")

    failed = adapter.assess(AssessmentRequest(raw_request="check cpu"))
    assert failed == ""
    assert adapter.last_usage is None

    assert adapter.assess(AssessmentRequest(raw_request="check cpu")) == "recovered"
    assert adapter.last_usage is not None
    assert adapter.last_usage.purpose == "assessment"
