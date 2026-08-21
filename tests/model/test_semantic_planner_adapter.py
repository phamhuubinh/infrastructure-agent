from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest

from src.model.semantic_planner_adapter import (
    MAX_PLANNER_ERROR_CHARS,
    ModelCallPurpose,
    PlannerFailureReason,
    PlannerProviderRequest,
    PlannerProviderResponse,
    SemanticPlannerAdapter,
    SemanticPlannerError,
)
from src.pipeline.request_semantics import ExecutionIntent, RequestDomain
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_wire import (
    planner_output_to_json,
    planner_output_to_wire,
    semantic_plan_to_json,
    semantic_plan_to_wire,
)


class FakeStructuredProvider:
    def __init__(
        self,
        response: PlannerProviderResponse | Exception,
    ) -> None:
        self.response = response
        self.requests: list[PlannerProviderRequest] = []

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def greeting_plan() -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        concept="greeting",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def test_openai_compatible_json_response_produces_valid_plan(
    greeting_plan: SemanticPlan,
) -> None:
    provider = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=semantic_plan_to_json(greeting_plan),
            provider="openai-compatible",
            model="planner-model",
            raw_usage={"prompt_tokens": 90, "completion_tokens": 32},
        )
    )

    result = SemanticPlannerAdapter([provider]).plan("hello", request_id="req-1")

    assert result.plan == greeting_plan
    assert result.provider == "openai-compatible"
    assert result.model == "planner-model"
    assert result.raw_usage == {"prompt_tokens": 90, "completion_tokens": 32}
    assert result.purpose is ModelCallPurpose.PLANNER
    request = provider.requests[0]
    assert request.purpose is ModelCallPurpose.PLANNER
    assert request.request_id == "req-1"
    assert request.response_schema["title"] == "OrionPlannerOutputV1"


def test_primary_adapter_uses_v2_hard_constraints_not_legacy_hints(
    greeting_plan: SemanticPlan,
) -> None:
    provider = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=semantic_plan_to_json(greeting_plan),
            provider="test",
            model="planner-model",
        )
    )

    SemanticPlannerAdapter([provider]).plan("Tính 15% của 2 triệu.")

    payload = json.loads(provider.requests[0].user_prompt)
    assert "hints" not in payload
    assert "hard_constraints" in payload
    assert "calculation" not in payload["hard_constraints"]


def test_anthropic_style_object_response_produces_same_plan(
    greeting_plan: SemanticPlan,
) -> None:
    provider = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=semantic_plan_to_wire(greeting_plan),
            provider="anthropic",
            model="claude-planner",
            raw_usage={"input_tokens": 88, "output_tokens": 30},
        )
    )

    result = SemanticPlannerAdapter([provider]).plan("hello")

    assert result.plan == greeting_plan
    assert result.raw_usage == {"input_tokens": 88, "output_tokens": 30}


def test_provider_fallback_preserves_order_and_schema(
    greeting_plan: SemanticPlan,
) -> None:
    first = FakeStructuredProvider(TimeoutError("primary timed out"))
    second = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=semantic_plan_to_wire(greeting_plan),
            provider="fallback",
            model="fallback-model",
        )
    )

    result = SemanticPlannerAdapter([first, second], timeout_seconds=12).plan("hello")

    assert result.plan == greeting_plan
    assert len(first.requests) == 1
    assert len(second.requests) == 1
    assert first.requests[0].timeout_seconds == 12
    assert first.requests[0].response_schema == second.requests[0].response_schema
    assert first.requests[0].response_schema is not second.requests[0].response_schema


def test_malformed_output_is_not_a_valid_plan_and_can_fallback(
    greeting_plan: SemanticPlan,
) -> None:
    malformed = semantic_plan_to_wire(greeting_plan)
    malformed["r"] = "invented"
    first = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=malformed,
            provider="bad-provider",
            model="bad-model",
        )
    )
    second = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=semantic_plan_to_json(greeting_plan),
            provider="good-provider",
            model="good-model",
        )
    )

    result = SemanticPlannerAdapter([first, second]).plan("hello")

    assert result.plan == greeting_plan
    assert result.provider == "good-provider"


def test_all_provider_errors_are_explicit_and_bounded() -> None:
    long_secret_like_error = "api_key=supersecret " + ("x" * 1000)
    timeout = FakeStructuredProvider(TimeoutError("slow"))
    unavailable = FakeStructuredProvider(ConnectionError(long_secret_like_error))

    with pytest.raises(SemanticPlannerError) as captured:
        SemanticPlannerAdapter([timeout, unavailable]).plan("hello")

    failures = captured.value.failures
    assert [failure.reason for failure in failures] == [
        PlannerFailureReason.TIMEOUT,
        PlannerFailureReason.PROVIDER_UNAVAILABLE,
    ]
    assert all(len(failure.message) <= MAX_PLANNER_ERROR_CHARS for failure in failures)
    assert "supersecret" not in str(captured.value)
    assert len(str(captured.value)) < 500


def test_no_provider_and_invalid_timeout_fail_explicitly() -> None:
    with pytest.raises(
        SemanticPlannerError, match="No semantic-planner provider"
    ) as error:
        SemanticPlannerAdapter([]).plan("hello")
    assert error.value.reason is PlannerFailureReason.NO_PROVIDER
    with pytest.raises(ValueError, match="at most 60"):
        SemanticPlannerAdapter([], timeout_seconds=61)


def test_single_malformed_response_is_reported_as_invalid_output(
    greeting_plan: SemanticPlan,
) -> None:
    malformed = semantic_plan_to_wire(greeting_plan)
    malformed.pop("r")
    provider = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=malformed,
            provider="bad-provider",
            model="bad-model",
        )
    )

    with pytest.raises(SemanticPlannerError) as captured:
        SemanticPlannerAdapter([provider]).plan("hello")

    assert captured.value.reason is PlannerFailureReason.INVALID_OUTPUT
    assert captured.value.failures[0].provider == "bad-provider"


def test_provider_request_contract_has_no_tool_or_execution_authority() -> None:
    names = {field.name for field in fields(PlannerProviderRequest)}

    assert names == {
        "purpose",
        "system_prompt",
        "user_prompt",
        "response_schema",
        "timeout_seconds",
        "request_id",
    }
    assert not names & {
        "tools",
        "capabilities",
        "commands",
        "execution_engine",
        "knowledge_tool",
    }


def test_envelope_payload_carries_final_answer_beside_the_plan(
    greeting_plan: SemanticPlan,
) -> None:
    provider = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=planner_output_to_wire(greeting_plan, "Xin chào!"),
            provider="openai-compatible",
            model="planner-model",
        )
    )

    result = SemanticPlannerAdapter([provider]).plan("hello")

    assert result.plan == greeting_plan
    assert result.final_answer == "Xin chào!"


def test_envelope_json_payload_with_null_answer_is_valid(
    greeting_plan: SemanticPlan,
) -> None:
    provider = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=planner_output_to_json(greeting_plan),
            provider="openai-compatible",
            model="planner-model",
        )
    )

    result = SemanticPlannerAdapter([provider]).plan("hello")

    assert result.plan == greeting_plan
    assert result.final_answer is None


def test_mismatched_envelope_answer_is_rejected_fail_closed(
    greeting_plan: SemanticPlan,
) -> None:
    mismatched = {
        "v": 1,
        "p": semantic_plan_to_wire(
            replace(greeting_plan, route=SemanticPlanRoute.CAPABILITY_ASSISTED)
        ),
        "a": "answer text",
    }
    provider = FakeStructuredProvider(
        PlannerProviderResponse(
            payload=mismatched,
            provider="bad-provider",
            model="bad-model",
        )
    )

    with pytest.raises(SemanticPlannerError) as captured:
        SemanticPlannerAdapter([provider]).plan("hello")

    assert captured.value.reason is PlannerFailureReason.INVALID_OUTPUT
