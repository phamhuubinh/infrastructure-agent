from __future__ import annotations

from decimal import Decimal

import pytest

from src.model.assessment_planner_provider import (
    PLANNER_MAX_OUTPUT_TOKENS,
    AssessmentPlannerProvider,
)
from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.model.semantic_planner_adapter import (
    ModelCallPurpose,
    PlannerProviderRequest,
    SemanticPlannerAdapter,
)
from src.pipeline.basic_calculator import CalculatorOperation, CalculatorRequest
from src.pipeline.request_semantics import ExecutionIntent, RequestDomain
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_wire import planner_output_to_json


def test_forwards_decoder_compatible_response_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate(
        self: LLMClient,
        prompt: str,
        **kwargs: object,
    ) -> str:
        del self, prompt
        captured.update(kwargs)
        return "{}"

    monkeypatch.setattr(LLMClient, "generate", fake_generate)

    provider = AssessmentPlannerProvider(LLMAssessmentAdapter(LLMClient(model="gpt-4")))

    schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "nested": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "deps": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "uniqueItems": True,
                        }
                    },
                },
            },
        },
    }

    request = PlannerProviderRequest(
        purpose=ModelCallPurpose.PLANNER,
        system_prompt="planner system",
        user_prompt='{"request":"hello"}',
        response_schema=schema,
        timeout_seconds=30,
    )

    response = provider.generate_structured(request)

    assert response.payload == "{}"
    assert captured["system_prompt"] == "planner system"

    sent = captured["response_schema"]
    assert sent == {
        "type": "object",
        "properties": {
            "sources": {
                "type": "array",
                "items": {"type": "string"},
            },
            "nested": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "deps": {
                            "type": "array",
                            "items": {"type": "integer"},
                        }
                    },
                },
            },
        },
    }

    # Authoritative schema must remain untouched.
    properties = schema["properties"]
    assert isinstance(properties, dict)
    sources = properties["sources"]
    assert isinstance(sources, dict)
    assert sources["uniqueItems"] is True


def test_environment_generation_schema_locks_hard_hints_without_empty_enum() -> None:
    from src.model.assessment_planner_provider import _planner_generation_schema
    from src.pipeline.semantic_plan_wire import planner_output_json_schema

    schema = _planner_generation_schema(
        planner_output_json_schema(),
        (
            '{"request":"Kiểm tra CPU trên monitor.",'
            '"hints":{"domain":"environment",'
            '"intent":"inspect_read_only",'
            '"scope":"live_environment",'
            '"sources":["any"],"exclude":[],'
            '"target":"monitor","concepts":["cpu"]}}'
        ),
    )

    def assert_no_empty_enum(value: object) -> None:
        if isinstance(value, dict):
            assert value.get("enum") != []
            for item in value.values():
                assert_no_empty_enum(item)
        elif isinstance(value, list):
            for item in value:
                assert_no_empty_enum(item)

    assert_no_empty_enum(schema)

    root = schema["properties"]
    props = root["p"]["properties"]

    assert props["r"]["enum"] == ["capability_assisted"]
    assert props["d"]["enum"] == ["environment"]
    assert props["i"]["enum"] == ["inspect_read_only"]
    assert props["f"]["enum"] == ["current"]
    assert props["m"]["enum"] == ["cpu"]
    assert props["c"] == {"type": "null"}
    assert props["sp"] == {"type": "array", "enum": [[]]}

    target = props["t"]["properties"]
    assert target["k"]["enum"] == ["explicit"]
    assert target["v"]["enum"] == ["monitor"]

    assert root["a"] == {"type": "null"}


def test_external_and_url_generation_schema_lock_raw_request_authority() -> None:
    from src.model.assessment_planner_provider import _planner_generation_schema
    from src.pipeline.semantic_plan_wire import planner_output_json_schema

    schema = _planner_generation_schema(
        planner_output_json_schema(),
        (
            '{"request":"Read https://example.com/status",'
            '"hints":{"domain":"external_information",'
            '"intent":"generate_content","scope":"explicit_url",'
            '"sources":["url_only"],"exclude":[],'
            '"url":"https://example.com/status"}}'
        ),
    )
    root = schema["properties"]
    assert isinstance(root, dict)
    plan = root["p"]
    assert isinstance(plan, dict)
    props = plan["properties"]
    assert isinstance(props, dict)

    assert props["r"] == {"type": "string", "enum": ["capability_assisted"]}
    assert props["d"] == {"type": "string", "enum": ["external_information"]}
    assert props["s"] == {"type": "array", "enum": [["url_only"]]}
    assert props["f"] == {"type": "string", "enum": ["current"]}
    assert props["u"] == {"type": "string", "enum": ["https://example.com/status"]}
    assert root["a"] == {"type": "null"}


def test_stable_general_generation_schema_prohibits_invented_subplans() -> None:
    from src.model.assessment_planner_provider import _planner_generation_schema
    from src.pipeline.semantic_plan_wire import planner_output_json_schema

    schema = _planner_generation_schema(
        planner_output_json_schema(),
        (
            '{"request":"Zombie process là gì?",'
            '"hints":{"domain":"general","intent":"explain",'
            '"scope":"stable_knowledge","sources":["any"],"exclude":[]}}'
        ),
    )
    root = schema["properties"]
    assert isinstance(root, dict)
    plan = root["p"]
    assert isinstance(plan, dict)
    props = plan["properties"]
    assert isinstance(props, dict)

    assert props["r"] == {"type": "string", "enum": ["direct_answer"]}
    assert props["f"] == {"type": "string", "enum": ["stable"]}
    assert props["sp"] == {"type": "array", "enum": [[]]}


def test_compliant_native_structured_response_reaches_valid_semantic_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )
    captured: dict[str, object] = {}

    def fake_generate(
        self: LLMClient,
        prompt: str,
        **kwargs: object,
    ) -> str:
        del self, prompt
        captured.update(kwargs)
        return planner_output_to_json(plan)

    monkeypatch.setattr(LLMClient, "generate", fake_generate)
    provider = AssessmentPlannerProvider(LLMAssessmentAdapter(LLMClient()))

    result = SemanticPlannerAdapter([provider]).plan("Xin chào")

    assert result.plan == plan
    assert result.provider == "openai"
    assert result.model == "gpt-4"
    assert isinstance(captured["response_schema"], dict)


def test_native_planner_keeps_arithmetic_contract_and_uses_a_small_token_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        deterministic_compute=DeterministicComputeIntent.REQUIRED,
        calculation=CalculatorRequest(
            operation=CalculatorOperation.MULTIPLY,
            left=Decimal("12"),
            right=Decimal("3"),
        ),
        clarification=ClarificationState.NOT_REQUIRED,
    )
    captured: dict[str, object] = {}

    def fake_generate(
        self: LLMClient,
        prompt: str,
        **kwargs: object,
    ) -> str:
        del self, prompt
        captured.update(kwargs)
        return planner_output_to_json(plan)

    monkeypatch.setattr(LLMClient, "generate", fake_generate)
    provider = AssessmentPlannerProvider(LLMAssessmentAdapter(LLMClient(max_tokens=4096)))

    result = SemanticPlannerAdapter([provider]).plan("What is 12 times 3?")

    assert result.plan.calculation == plan.calculation
    assert captured["max_tokens"] == PLANNER_MAX_OUTPUT_TOKENS
    assert isinstance(captured["response_schema"], dict)


def test_malformed_native_planner_response_remains_non_dispatchable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(LLMClient, "generate", lambda *_args, **_kwargs: "analysis")
    provider = AssessmentPlannerProvider(LLMAssessmentAdapter(LLMClient()))

    outcome = SemanticPlannerAdapter([provider]).plan_safely("What is 12 times 3?")

    assert outcome.reason.value == "malformed_output"


@pytest.mark.parametrize(
    "payload",
    [
        "Here is the plan: {\"v\":1}",
        "<think>plan</think>{\"v\":1}",
        "{\"v\":1,\"p\":{},\"a\":null} trailing prose",
    ],
)
def test_representative_provider_malformed_payloads_remain_non_dispatchable(
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
) -> None:
    monkeypatch.setattr(LLMClient, "generate", lambda *_args, **_kwargs: payload)
    provider = AssessmentPlannerProvider(LLMAssessmentAdapter(LLMClient()))

    outcome = SemanticPlannerAdapter([provider]).plan_safely("Write a Python function")

    assert outcome.reason.value == "malformed_output"


def test_non_llm_assessment_adapter_uses_bounded_wire_hint_fallback() -> None:
    from src.model.assessment_model_adapter import AssessmentModelAdapter
    from src.pipeline.assessment_request import AssessmentRequest

    class RawOnlyAdapter(AssessmentModelAdapter):
        def __init__(self) -> None:
            self.prompt: str | None = None

        def assess(self, request: AssessmentRequest) -> str:
            del request
            return "unused"

        def assess_raw(self, prompt: str) -> str:
            self.prompt = prompt
            return '{"v":1,"p":{},"a":null}'

    model = RawOnlyAdapter()
    provider = AssessmentPlannerProvider(model)
    request = PlannerProviderRequest(
        purpose=ModelCallPurpose.PLANNER,
        system_prompt="system",
        user_prompt='{"request":"hello"}',
        response_schema={"type": "object"},
        timeout_seconds=30,
    )

    provider.generate_structured(request)

    assert model.prompt is not None
    assert "JSON only. Envelope keys exactly v,p,a" in model.prompt


def test_unsupported_openai_compatible_client_uses_bounded_wire_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate(
        self: LLMClient,
        prompt: str,
        **kwargs: object,
    ) -> str:
        del self, prompt
        captured.update(kwargs)
        return "{}"

    monkeypatch.setattr(LLMClient, "generate", fake_generate)
    client = LLMClient(supports_structured_output=False)
    provider = AssessmentPlannerProvider(LLMAssessmentAdapter(client))
    request = PlannerProviderRequest(
        purpose=ModelCallPurpose.PLANNER,
        system_prompt="system",
        user_prompt='{"request":"hello"}',
        response_schema={"type": "object"},
        timeout_seconds=30,
    )

    provider.generate_structured(request)

    assert "response_schema" not in captured
    assert captured["json_object"] is True
    system_prompt = captured["system_prompt"]
    assert isinstance(system_prompt, str)
    assert system_prompt.startswith("system JSON only. Envelope keys exactly v,p,a")
