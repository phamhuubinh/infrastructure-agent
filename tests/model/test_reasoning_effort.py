from __future__ import annotations

import json
from unittest import mock

from src.model.llm_client import LLMClient
from src.model.reasoning_effort import (
    ModelRequestClass,
    ReasoningEffort,
    ReasoningEffortPolicy,
)


def _mock_response(
    payload: bytes,
) -> mock.MagicMock:
    response = mock.MagicMock()
    response.read.return_value = payload
    response.__enter__.return_value = response
    return response


def test_policy_scales_effort_by_request_class() -> None:
    assert (
        ReasoningEffortPolicy.for_call(
            purpose="planner",
            request_class=(
                ModelRequestClass.TRIVIAL
            ),
        )
        is ReasoningEffort.MINIMAL
    )

    assert (
        ReasoningEffortPolicy.for_call(
            purpose="response",
            request_class=(
                ModelRequestClass.NORMAL
            ),
        )
        is ReasoningEffort.LOW
    )

    assert (
        ReasoningEffortPolicy.for_call(
            purpose="assessment",
            request_class=(
                ModelRequestClass
                .MULTI_SOURCE_DIAGNOSIS
            ),
        )
        is ReasoningEffort.HIGH
    )


@mock.patch("urllib.request.urlopen")
def test_supported_client_sends_reasoning_effort(
    mock_urlopen: mock.Mock,
) -> None:
    mock_urlopen.return_value = (
        _mock_response(
            b'{"choices":[{"message":'
            b'{"content":"ok"}}],'
            b'"usage":{"prompt_tokens":9,'
            b'"completion_tokens":15,'
            b'"completion_tokens_details":'
            b'{"reasoning_tokens":6}}}'
        )
    )

    client = LLMClient(
        base_url="https://api.openai.com",
        supports_reasoning_effort=True,
    )

    assert (
        client.generate(
            "hello",
            purpose="response",
            reasoning_effort=(
                ReasoningEffort.LOW
            ),
        )
        == "ok"
    )

    request = mock_urlopen.call_args[0][0]
    body = json.loads(request.data)

    assert body["reasoning_effort"] == "low"
    assert client.last_usage is not None
    assert (
        client.last_usage.reasoning_tokens
        == 6
    )


@mock.patch("urllib.request.urlopen")
def test_unsupported_client_omits_reasoning_effort(
    mock_urlopen: mock.Mock,
) -> None:
    mock_urlopen.return_value = (
        _mock_response(
            b'{"choices":[{"message":'
            b'{"content":"ok"}}]}'
        )
    )

    client = LLMClient(
        supports_reasoning_effort=False
    )

    client.generate(
        "hello",
        reasoning_effort=(
            ReasoningEffort.HIGH
        ),
    )

    request = mock_urlopen.call_args[0][0]
    body = json.loads(request.data)

    assert "reasoning_effort" not in body
