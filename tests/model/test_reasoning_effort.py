from __future__ import annotations

import json
from unittest import mock

from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.model.reasoning_effort import (
    ModelRequestClass,
    ReasoningEffort,
    ReasoningEffortPolicy,
)
from src.model.semantic_planner_adapter import (
    PlannerProviderRequest,
    PlannerProviderResponse,
    SemanticPlannerAdapter,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_wire import planner_output_to_wire


def _mock_response(payload: bytes) -> mock.MagicMock:
    response = mock.MagicMock()
    response.read.return_value = payload
    response.__enter__.return_value = response
    return response


def test_policy_uses_minimum_effort_for_trivial_and_more_for_complex_calls() -> None:
    assert (
        ReasoningEffortPolicy.for_call(
            purpose="planner",
            request_class=ModelRequestClass.TRIVIAL,
        )
        is ReasoningEffort.MINIMAL
    )
    assert (
        ReasoningEffortPolicy.for_call(
            purpose="response",
            request_class=ModelRequestClass.NORMAL,
        )
        is ReasoningEffort.LOW
    )
    assert (
        ReasoningEffortPolicy.for_call(
            purpose="assessment",
            request_class=ModelRequestClass.EVIDENCE_ASSISTED,
        )
        is ReasoningEffort.MEDIUM
    )
    assert (
        ReasoningEffortPolicy.for_call(
            purpose="assessment",
            request_class=ModelRequestClass.MULTI_SOURCE_DIAGNOSIS,
        )
        is ReasoningEffort.HIGH
    )


@mock.patch("urllib.request.urlopen")
def test_supported_openai_compatible_client_sends_effort_and_records_actual_usage(
    mock_urlopen: mock.Mock,
) -> None:
    mock_urlopen.return_value = _mock_response(
        b'{"choices":[{"message":{"content":"ok"}}],'
        b'"usage":{"prompt_tokens":9,"completion_tokens":15,'
        b'"completion_tokens_details":{"reasoning_tokens":6}}}'
    )
    client = LLMClient(
        base_url="https://api.openai.com",
        supports_reasoning_effort=True,
    )

    assert (
        client.generate(
            "hello",
            purpose="response",
            reasoning_effort=ReasoningEffort.LOW,
        )
        == "ok"
    )

    request = mock_urlopen.call_args[0][0]
    body = json.loads(request.data)
    assert body["reasoning_effort"] == "low"
    usage = client.last_usage
    assert usage is not None
    assert usage.configured_effort == "low"
    assert usage.reasoning_tokens == 6


@mock.patch("urllib.request.urlopen")
def test_unsupported_openai_compatible_client_omits_effort_option(
    mock_urlopen: mock.Mock,
) -> None:
    mock_urlopen.return_value = _mock_response(
        b'{"choices":[{"message":{"content":"ok"}}]}'
    )
    client = LLMClient(supports_reasoning_effort=False)

    client.generate("hello", reasoning_effort=ReasoningEffort.HIGH)

    request = mock_urlopen.call_args[0][0]
    body = json.loads(request.data)
    assert "reasoning_effort" not in body
    assert client.last_usage is not None
    assert client.last_usage.configured_effort is None


def test_assessment_adapter_uses_low_for_raw_and_high_for_multi_source() -> None:
    client = mock.Mock(spec=LLMClient)
    client._model = "test-model"
    client.generate.return_value = "ok"
    client.last_usage = None
    adapter = LLMAssessmentAdapter(client)

    assert adapter.assess_raw("hello") == "ok"
    assert client.generate.call_args.kwargs["reasoning_effort"] is ReasoningEffort.LOW

    client.generate.reset_mock()
    request = AssessmentRequest(
        raw_request="compare monitoring sources",
        intent="MACHINE_ASSESSMENT",
        evidence=(
            EvidencePackage(
                capability_name="grafana-cpu",
                evidence_name="cpu",
                data={"value": 30},
                source_tool="grafana",
            ),
            EvidencePackage(
                capability_name="zabbix-cpu",
                evidence_name="cpu",
                data={"value": 31},
                source_tool="zabbix",
            ),
        ),
        raw_evidence_required=True,
    )

    assert adapter.assess(request) == "ok"
    assert client.generate.call_args.kwargs["reasoning_effort"] is ReasoningEffort.HIGH


class _PlannerProvider:
    def __init__(self, plan: SemanticPlan) -> None:
        self.plan = plan
        self.requests: list[PlannerProviderRequest] = []

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        self.requests.append(request)
        return PlannerProviderResponse(
            payload=planner_output_to_wire(self.plan, "Hello!"),
            provider="mock",
            model="planner",
            raw_usage={
                "prompt_tokens": 10,
                "completion_tokens": 8,
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
            configured_effort=request.reasoning_effort,
        )


def test_planner_metadata_prefers_minimal_effort_and_records_provider_choice() -> None:
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        concept="greeting",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )
    provider = _PlannerProvider(plan)

    outcome = SemanticPlannerAdapter([provider]).plan_safely("hello")

    assert provider.requests[0].reasoning_effort is ReasoningEffort.MINIMAL
    assert outcome.result is not None
    assert outcome.result.configured_effort == "minimal"
    assert outcome.to_trace_dict()["configured_effort"] == "minimal"
