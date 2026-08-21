from __future__ import annotations

import pytest

from src.agent.controller_contracts import (
    AgentAction,
    AgentDecision,
    AgentDecisionKind,
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
    payload = agent_decision_to_json(decision) if isinstance(decision, AgentDecision) else decision
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
    result = adapter.decide(
        "Check CPU", hard_constraints=HardRequestConstraints()
    )
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
