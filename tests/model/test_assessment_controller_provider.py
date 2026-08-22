from __future__ import annotations

from src.agent.controller_contracts import AgentRunState, ControllerCallStage
from src.model.assessment_planner_provider import (
    CONTROLLER_MAX_OUTPUT_TOKENS,
    AssessmentControllerProvider,
)
from src.model.controller_adapter import (
    ControllerCallPurpose,
    ControllerProviderRequest,
)
from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.model.protocol.controller_prompt import (
    ControllerContinuationInput,
    agent_decision_json_schema,
    build_controller_prompt,
)
from src.pipeline.hard_request_constraints import HardRequestConstraints


def _assert_no_open_ended_objects(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False
        for value in schema.values():
            _assert_no_open_ended_objects(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_no_open_ended_objects(value)


def test_controller_provider_uses_native_schema_when_supported(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate(self: LLMClient, prompt: str, **kwargs: object) -> str:
        del self, prompt
        captured.update(kwargs)
        return '{"v":1,"k":"final","g":"Answer.","c":null,"a":null,"f":"Hello.","q":null,"r":null}'

    monkeypatch.setattr(LLMClient, "generate", fake_generate)
    client = LLMClient(max_tokens=4096, supports_structured_output=True)
    provider = AssessmentControllerProvider(LLMAssessmentAdapter(client))
    request = ControllerProviderRequest(
        purpose=ControllerCallPurpose.CONTROLLER,
        system_prompt="controller system",
        user_prompt='{"request":"hello"}',
        response_schema=agent_decision_json_schema(),
        timeout_seconds=30,
    )

    response = provider.generate_controller(request)

    assert response.payload.startswith('{"v":1')
    assert captured["response_schema"] == request.response_schema
    _assert_no_open_ended_objects(captured["response_schema"])
    assert captured["max_tokens"] == CONTROLLER_MAX_OUTPUT_TOKENS
    assert captured["purpose"] == "controller"


def test_controller_provider_falls_back_to_json_object_without_native_schema(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate(self: LLMClient, prompt: str, **kwargs: object) -> str:
        del self, prompt
        captured.update(kwargs)
        return "{}"

    monkeypatch.setattr(LLMClient, "generate", fake_generate)
    provider = AssessmentControllerProvider(
        LLMAssessmentAdapter(LLMClient(supports_structured_output=False))
    )
    request = ControllerProviderRequest(
        purpose=ControllerCallPurpose.CONTROLLER,
        system_prompt="controller system",
        user_prompt='{"request":"hello"}',
        response_schema=agent_decision_json_schema(),
        timeout_seconds=30,
    )

    provider.generate_controller(request)

    assert "response_schema" not in captured
    assert captured["json_object"] is True
    assert "JSON only. Return exactly one AgentDecision" in captured["system_prompt"]


def test_native_controller_schema_projects_one_selected_capability(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate(self: LLMClient, prompt: str, **kwargs: object) -> str:
        del self, prompt
        captured.update(kwargs)
        return '{"v":1,"k":"action","g":"Inspect CPU.","c":null,"a":{"i":"host.cpu","a":{"target_id":"monitor"}},"f":null,"q":null,"r":null}'

    selected = {
        "capability_id": "host.cpu",
        "arguments_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["target_id"],
            "properties": {"target_id": {"type": "string"}},
        },
    }
    prompt = build_controller_prompt(
        "Check CPU.",
        hard_constraints=HardRequestConstraints(),
        continuation=ControllerContinuationInput(
            run_state=AgentRunState(raw_request="Check CPU."),
            selected_capability_schema=selected,
        ),
        call_stage=ControllerCallStage.ACTION_CONTINUATION,
    )
    monkeypatch.setattr(LLMClient, "generate", fake_generate)
    provider = AssessmentControllerProvider(
        LLMAssessmentAdapter(LLMClient(supports_structured_output=True))
    )
    provider.generate_controller(
        ControllerProviderRequest(
            purpose=ControllerCallPurpose.CONTROLLER,
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            response_schema=prompt.response_schema,
            timeout_seconds=30,
        )
    )

    schema = captured["response_schema"]
    _assert_no_open_ended_objects(schema)
    assert isinstance(schema, dict)
    action = schema["properties"]["a"]["anyOf"][0]
    arguments = action["properties"]["a"]
    assert set(arguments["properties"]) == {"target_id"}
    assert "undeclared" not in arguments["properties"]
