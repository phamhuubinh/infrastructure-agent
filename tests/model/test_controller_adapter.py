from __future__ import annotations

from typing import cast

import pytest

from src.agent.controller_contracts import (
    AgentAction,
    AgentDecision,
    AgentDecisionKind,
    AgentRunState,
    ControllerCallStage,
    agent_decision_to_json,
)
from src.model.controller_adapter import (
    ControllerAdapter,
    ControllerAdapterError,
    ControllerCallPurpose,
    ControllerFailureReason,
    ControllerProviderRequest,
    ControllerProviderResponse,
)
from src.model.protocol.controller_prompt import ControllerContinuationInput
from src.model.reasoning_effort import ReasoningEffort
from src.model.usage_recorder import ModelUsageRecorder
from src.pipeline.hard_request_constraints import HardRequestConstraints


class FakeControllerProvider:
    def __init__(self, responses: list[ControllerProviderResponse | Exception]) -> None:
        self.responses = responses
        self.requests: list[ControllerProviderRequest] = []

    def generate_controller(
        self, request: ControllerProviderRequest
    ) -> ControllerProviderResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(
    decision: AgentDecision | str,
    *,
    provider: str = "mock",
    model: str = "mock-model",
) -> ControllerProviderResponse:
    payload = (
        agent_decision_to_json(decision)
        if isinstance(decision, AgentDecision)
        else decision
    )
    return ControllerProviderResponse(
        payload=payload,
        provider=provider,
        model=model,
        raw_usage={"prompt_tokens": 21, "completion_tokens": 8},
    )


def test_valid_final_and_action_decisions_are_strictly_returned() -> None:
    final = AgentDecision(
        kind=AgentDecisionKind.FINAL,
        goal="Answer the greeting.",
        final_answer="Hello.",
        clarification_question=None,
    )
    action = AgentDecision(
        kind=AgentDecisionKind.ACTION,
        goal="Inspect CPU.",
        action=AgentAction("host.cpu"),
        clarification_question=None,
    )
    provider = FakeControllerProvider([_response(final), _response(action)])
    adapter = ControllerAdapter([provider])

    assert (
        adapter.decide("Hello", hard_constraints=HardRequestConstraints()).decision
        == final
    )
    result = adapter.decide("Check CPU", hard_constraints=HardRequestConstraints())
    assert result.decision == action
    assert result.purpose is ControllerCallPurpose.CONTROLLER
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    "payload, expected",
    [
        ("not json", "not valid JSON"),
        (
            '{"v":1,"k":"execute","g":"Do work.","c":null,"a":null,"f":null,"q":null,"r":null}',
            "unknown enum",
        ),
    ],
)
def test_malformed_json_and_unknown_enums_fail_closed(
    payload: str, expected: str
) -> None:
    provider = FakeControllerProvider([_response(payload)])

    with pytest.raises(ControllerAdapterError) as captured:
        ControllerAdapter([provider]).decide(
            "Check CPU", hard_constraints=HardRequestConstraints()
        )

    failure = captured.value.failures[0]
    assert failure.reason is ControllerFailureReason.INVALID_OUTPUT
    assert expected in failure.message


def test_provider_failover_is_one_bounded_attempt_per_provider() -> None:
    decision = AgentDecision(
        kind=AgentDecisionKind.DISCOVER,
        goal="Find an observation capability.",
        category="host",
        clarification_question=None,
    )
    first = FakeControllerProvider([TimeoutError("slow")])
    second = FakeControllerProvider([_response(decision, provider="fallback")])

    result = ControllerAdapter([first, second], timeout_seconds=12).decide(
        "Check CPU", hard_constraints=HardRequestConstraints()
    )

    assert result.provider == "fallback"
    assert len(first.requests) == len(second.requests) == 1
    assert first.requests[0].timeout_seconds == 12


def test_failover_preserves_total_result_latency_and_attempt_usage_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = AgentDecision(
        kind=AgentDecisionKind.FINAL,
        goal="Answer the greeting.",
        final_answer="Hello.",
        clarification_question=None,
    )
    clock = iter((10.0, 11.0, 12.0, 13.0, 14.0, 16.0, 20.0))
    monkeypatch.setattr(
        "src.model.controller_adapter.time.perf_counter", lambda: next(clock)
    )
    recorder = ModelUsageRecorder()
    result = ControllerAdapter(
        [
            FakeControllerProvider([TimeoutError("slow")]),
            FakeControllerProvider([_response(final, provider="fallback")]),
        ],
        usage_recorder=recorder,
    ).decide("Hello", hard_constraints=HardRequestConstraints())

    assert result.provider_attempt_count == 2
    assert result.latency_ms == 10_000.0
    assert [call.latency_ms for call in recorder.calls] == [1_000.0, 2_000.0]
    assert result.latency_ms != recorder.calls[1].latency_ms


def test_usage_is_recorded_for_success_and_malformed_provider_output() -> None:
    final = AgentDecision(
        kind=AgentDecisionKind.FINAL,
        goal="Answer the greeting.",
        final_answer="Hello.",
        clarification_question=None,
    )
    recorder = ModelUsageRecorder()
    provider = FakeControllerProvider([_response(final), _response("not json")])
    adapter = ControllerAdapter([provider], usage_recorder=recorder)

    adapter.decide("Hello", hard_constraints=HardRequestConstraints())
    outcome = adapter.decide_safely("Again", hard_constraints=HardRequestConstraints())

    assert outcome.decision is None
    assert [call.purpose for call in recorder.calls] == ["controller", "controller"]
    assert [call.input_tokens for call in recorder.calls] == [21, 21]
    assert recorder.to_trace_dict()["by_purpose"]["controller"]["calls"] == 2
    assert [call.call_stage for call in recorder.calls] == [
        "first_decision",
        "first_decision",
    ]


def test_invalid_configured_effort_fails_closed_and_records_safe_usage() -> None:
    final = AgentDecision(
        kind=AgentDecisionKind.FINAL,
        goal="Answer the greeting.",
        final_answer="Hello.",
        clarification_question=None,
    )
    recorder = ModelUsageRecorder()
    response = ControllerProviderResponse(
        payload=agent_decision_to_json(final),
        provider="mock",
        model="mock-model",
        raw_usage={"prompt_tokens": 21, "completion_tokens": 8},
        configured_effort=cast(ReasoningEffort, "invalid"),
    )

    with pytest.raises(ControllerAdapterError) as captured:
        ControllerAdapter(
            [FakeControllerProvider([response])], usage_recorder=recorder
        ).decide("Hello", hard_constraints=HardRequestConstraints())

    assert captured.value.failures[0].reason is ControllerFailureReason.INVALID_OUTPUT
    assert len(recorder.calls) == 1
    usage = recorder.calls[0]
    assert usage.input_tokens == 21
    assert usage.total_output_tokens == 8
    assert usage.configured_effort is None


def test_invalid_configured_effort_records_one_attempt_then_fails_over() -> None:
    final = AgentDecision(
        kind=AgentDecisionKind.FINAL,
        goal="Answer the greeting.",
        final_answer="Hello.",
        clarification_question=None,
    )
    recorder = ModelUsageRecorder()
    invalid = ControllerProviderResponse(
        payload=agent_decision_to_json(final),
        provider="invalid-provider",
        model="mock-model",
        raw_usage={"prompt_tokens": 21, "completion_tokens": 8},
        configured_effort=cast(ReasoningEffort, "invalid"),
    )
    valid = _response(final, provider="valid-provider")

    result = ControllerAdapter(
        [FakeControllerProvider([invalid]), FakeControllerProvider([valid])],
        usage_recorder=recorder,
    ).decide("Hello", hard_constraints=HardRequestConstraints())

    assert result.decision == final
    assert len(recorder.calls) == 2
    assert recorder.calls[0].configured_effort is None
    assert recorder.calls[1].configured_effort is None


def test_stage_metadata_and_effort_are_based_on_loop_stage() -> None:
    action = AgentDecision(
        kind=AgentDecisionKind.ACTION,
        goal="Inspect CPU.",
        action=AgentAction("host.cpu", {}),
        clarification_question=None,
    )
    provider = FakeControllerProvider([_response(action)])
    adapter = ControllerAdapter([provider])
    state = AgentRunState(raw_request="Check CPU.")

    result = adapter.decide(
        state.raw_request,
        hard_constraints=HardRequestConstraints(),
        continuation=ControllerContinuationInput(
            run_state=state,
            selected_capability_schema={
                "capability_id": "host.cpu",
                "arguments_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [],
                    "properties": {},
                },
            },
        ),
        call_stage=ControllerCallStage.ACTION_CONTINUATION,
    )

    request = provider.requests[0]
    assert result.call_stage is ControllerCallStage.ACTION_CONTINUATION
    assert request.reasoning_effort is ReasoningEffort.LOW
    assert request.input_budget_class == "controller_action"
    assert request.actual_input_chars <= request.input_budget_max_chars


@pytest.mark.parametrize(
    ("stage", "expected"),
    (
        (ControllerCallStage.FIRST_DECISION, ReasoningEffort.MINIMAL),
        (ControllerCallStage.DISCOVERY_CONTINUATION, ReasoningEffort.LOW),
        (ControllerCallStage.ACTION_CONTINUATION, ReasoningEffort.LOW),
        (ControllerCallStage.OBSERVATION_CONTINUATION, ReasoningEffort.LOW),
    ),
)
def test_controller_effort_is_determined_only_by_call_stage(
    stage: ControllerCallStage, expected: ReasoningEffort
) -> None:
    request = ControllerProviderRequest(
        purpose=ControllerCallPurpose.CONTROLLER,
        call_stage=stage,
        system_prompt="system",
        user_prompt='{"request":"debug the current issue"}',
        response_schema={},
        timeout_seconds=30,
    )

    assert request.reasoning_effort is expected
