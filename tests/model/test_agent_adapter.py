from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from src.agent.contracts import (
    AgentDecision,
    DecisionKind,
    decision_to_json,
)
from src.model.agent_adapter import (
    AgentModelAdapter,
    AgentModelError,
    AgentModelFailureReason,
    AgentProviderRequest,
    AgentProviderResponse,
)


class FakeProvider:
    def __init__(
        self,
        responses: list[AgentProviderResponse | Exception],
    ) -> None:
        self.responses = responses
        self.requests: list[AgentProviderRequest] = []

    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ) -> AgentProviderResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _final_response(
    *,
    provider: str = "mock",
    model: str = "mock-model",
    raw_usage: Mapping[str, object] | None = None,
) -> AgentProviderResponse:
    decision = AgentDecision(
        kind=DecisionKind.FINAL,
        goal="Answer the user.",
        answer="Done.",
    )
    return AgentProviderResponse(
        payload=decision_to_json(decision),
        provider=provider,
        model=model,
        raw_usage=raw_usage,
    )


def test_adapter_returns_canonical_decision() -> None:
    provider = FakeProvider(
        [
            _final_response(
                raw_usage={
                    "input_tokens": 10,
                    "output_tokens": 4,
                }
            )
        ]
    )

    result = AgentModelAdapter([provider]).decide(
        system_prompt="You are Orion.",
        user_prompt='{"request":"hello"}',
        request_id="req-1",
    )

    assert result.decision == AgentDecision(
        kind=DecisionKind.FINAL,
        goal="Answer the user.",
        answer="Done.",
    )
    assert result.provider == "mock"
    assert result.model == "mock-model"
    assert result.raw_usage == {
        "input_tokens": 10,
        "output_tokens": 4,
    }
    assert result.provider_attempt_count == 1

    request = provider.requests[0]
    assert request.request_id == "req-1"
    assert request.timeout_seconds == 30.0
    assert request.response_schema["title"] == "OrionAgentDecisionV3"


def test_selected_capability_schema_is_forwarded_to_transport() -> None:
    provider = FakeProvider([_final_response()])

    AgentModelAdapter([provider]).decide(
        system_prompt="system",
        user_prompt="user",
        selected_capability_schema={
            "capability_id": "host.cpu",
            "target_ref": {"applicable": True, "allowed_refs": ["monitor"]},
            "source_ref": {"applicable": False},
            "arguments_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["window_seconds"],
                "properties": {
                    "window_seconds": {"type": "integer"},
                },
            },
        },
    )

    schema = provider.requests[0].response_schema
    action_branch = next(
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["kind"]["enum"] == ["action"]
    )
    action = action_branch["properties"]["action"]

    assert action["properties"]["capability_id"]["enum"] == [
        "host.cpu"
    ]
    assert action["properties"]["arguments"]["required"] == [
        "window_seconds"
    ]


def test_no_provider_fails_closed() -> None:
    with pytest.raises(AgentModelError) as captured:
        AgentModelAdapter([]).decide(
            system_prompt="system",
            user_prompt="user",
        )

    assert captured.value.reason is AgentModelFailureReason.NO_PROVIDER
    assert captured.value.failures == ()


def test_timeout_fails_over_once_to_next_provider() -> None:
    first = FakeProvider([TimeoutError("slow")])
    second = FakeProvider(
        [_final_response(provider="fallback", model="fallback-model")]
    )

    result = AgentModelAdapter(
        [first, second],
        timeout_seconds=12,
    ).decide(
        system_prompt="system",
        user_prompt="user",
    )

    assert result.provider == "fallback"
    assert result.model == "fallback-model"
    assert result.provider_attempt_count == 2
    assert len(first.requests) == 1
    assert len(second.requests) == 1
    assert first.requests[0].timeout_seconds == 12


def test_invalid_output_fails_over_without_repair_parser() -> None:
    first = FakeProvider(
        [
            AgentProviderResponse(
                payload='{"v":1,"k":"final"}',
                provider="bad",
                model="bad-model",
            )
        ]
    )
    second = FakeProvider([_final_response(provider="good")])

    result = AgentModelAdapter([first, second]).decide(
        system_prompt="system",
        user_prompt="user",
    )

    assert result.provider == "good"
    assert result.provider_attempt_count == 2


def test_invalid_action_wire_reports_sanitized_parser_diagnostics() -> None:
    malformed_action = {
        "version": 3,
        "kind": "action",
            "action": {
                "capability_id": "compute.deterministic",
                "arguments": {},
                "unexpected": True,
            },
    }
    provider = FakeProvider(
        [
            AgentProviderResponse(
                payload=json.dumps(malformed_action),
                provider="qwen",
                model="qwen-test",
            )
        ]
    )

    with pytest.raises(AgentModelError) as captured:
        AgentModelAdapter([provider]).decide(
            system_prompt="system",
            user_prompt="user",
        )

    failure = captured.value.failures[0]
    assert failure.reason is AgentModelFailureReason.INVALID_OUTPUT
    assert failure.diagnostics == {
        "response_type": "str",
        "response_length": len(json.dumps(malformed_action).encode("utf-8")),
        "parse_error_category": "contract_error",
        "schema_validation_error_path": None,
        "parser_error_path": "action",
        "json_parseable": True,
        "stripped_starts_with_object": True,
        "stripped_ends_with_object": True,
        "contains_markdown_code_fence": False,
        "contains_think_open_tag": False,
        "contains_think_close_tag": False,
        "leading_format": "json_object",
        "trailing_format": "json_object_end",
        "json_object_candidate_count": 1,
        "json_top_level_keys": [
            "action",
            "kind",
            "version",
        ],
        "unknown_top_level_key_count": 0,
        "decision_kind": "action",
    }


def test_invalid_text_payload_reports_format_without_retaining_content() -> None:
    payload = "```json\n{\"kind\":\"action\"}\n```"
    provider = FakeProvider(
        [
            AgentProviderResponse(
                payload=payload,
                provider="qwen",
                model="qwen-test",
            )
        ]
    )

    with pytest.raises(AgentModelError) as captured:
        AgentModelAdapter([provider]).decide(
            system_prompt="system",
            user_prompt="user",
        )

    diagnostics = captured.value.failures[0].diagnostics
    assert diagnostics == {
        "response_type": "str",
        "response_length": len(payload.encode("utf-8")),
        "parse_error_category": "contract_error",
        "schema_validation_error_path": None,
        "parser_error_path": None,
        "json_parseable": False,
        "stripped_starts_with_object": False,
        "stripped_ends_with_object": False,
        "contains_markdown_code_fence": True,
        "contains_think_open_tag": False,
        "contains_think_close_tag": False,
        "leading_format": "code_fence",
        "trailing_format": "code_fence",
        "json_object_candidate_count": 1,
    }


def test_invalid_text_payload_includes_safe_provider_generation_metadata() -> None:
    provider = FakeProvider(
        [
            AgentProviderResponse(
                payload='{"kind":"action"',
                provider="qwen",
                model="qwen-test",
                generation_diagnostics={
                    "finish_reason": "length",
                    "usage_completion_tokens": 1024,
                    "usage_prompt_tokens": 312,
                    "stop_sequence_configured": False,
                    "content_bytes_before_sanitization": 1309,
                    "content_bytes_after_sanitization": 1309,
                    "provider_http_status": 200,
                    "untrusted_payload": "must not be emitted",
                },
            )
        ]
    )

    with pytest.raises(AgentModelError) as captured:
        AgentModelAdapter([provider]).decide(
            system_prompt="system",
            user_prompt="user",
        )

    diagnostics = captured.value.failures[0].diagnostics
    assert diagnostics["provider_generation"] == {
        "finish_reason": "length",
        "usage_completion_tokens": 1024,
        "usage_prompt_tokens": 312,
        "content_bytes_before_sanitization": 1309,
        "content_bytes_after_sanitization": 1309,
        "provider_http_status": 200,
        "stop_sequence_configured": False,
    }


def test_all_failures_preserve_bounded_failure_reasons() -> None:
    providers = [
        FakeProvider([ConnectionError("offline")]),
        FakeProvider(
            [
                AgentProviderResponse(
                    payload="not-json",
                    provider="broken",
                    model="m",
                )
            ]
        ),
    ]

    with pytest.raises(AgentModelError) as captured:
        AgentModelAdapter(providers).decide(
            system_prompt="system",
            user_prompt="user",
        )

    failures = captured.value.failures

    assert [failure.reason for failure in failures] == [
        AgentModelFailureReason.PROVIDER_UNAVAILABLE,
        AgentModelFailureReason.INVALID_OUTPUT,
    ]
    assert failures[0].provider == "provider-1"
    assert failures[1].provider == "broken"


def test_provider_response_contract_is_strict() -> None:
    class InvalidProvider:
        def generate_agent_decision(
            self,
            request: AgentProviderRequest,
        ) -> AgentProviderResponse:
            return "wrong"  # type: ignore[return-value]

    with pytest.raises(AgentModelError) as captured:
        AgentModelAdapter([InvalidProvider()]).decide(
            system_prompt="system",
            user_prompt="user",
        )

    assert (
        captured.value.failures[0].reason
        is AgentModelFailureReason.INVALID_OUTPUT
    )


def test_raw_usage_must_be_mapping() -> None:
    provider = FakeProvider(
        [
            AgentProviderResponse(
                payload=decision_to_json(
                    AgentDecision(
                        kind=DecisionKind.FINAL,
                        goal="Answer.",
                        answer="Done.",
                    )
                ),
                provider="mock",
                model="model",
                raw_usage=["bad"],  # type: ignore[arg-type]
            )
        ]
    )

    with pytest.raises(AgentModelError) as captured:
        AgentModelAdapter([provider]).decide(
            system_prompt="system",
            user_prompt="user",
        )

    assert (
        captured.value.failures[0].reason
        is AgentModelFailureReason.INVALID_OUTPUT
    )


def test_adapter_has_no_semantic_or_execution_inputs() -> None:
    parameters = AgentModelAdapter.decide.__annotations__

    assert "hard_constraints" not in parameters
    assert "target_resolver" not in parameters
    assert "executor" not in parameters
    assert "permission_mode" not in parameters
