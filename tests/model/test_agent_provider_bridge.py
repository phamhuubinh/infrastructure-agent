from __future__ import annotations

import json

from src.model.agent_adapter import (
    AgentProviderRequest,
    StructuredAgentProvider,
)
from src.model.agent_provider_bridge import (
    AssessmentAgentProvider,
    MAX_AGENT_OUTPUT_TOKENS,
)
from src.model.llm_assessment_adapter import (
    LLMAssessmentAdapter,
)
from src.model.llm_client import LLMClient
from src.model.usage_metadata import ModelCallUsage


def _request() -> AgentProviderRequest:
    return AgentProviderRequest(
        system_prompt="canonical system",
        user_prompt='{"stage":"first"}',
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "kind": {"type": "string"},
            },
            "required": ["kind"],
        },
        timeout_seconds=30.0,
        request_id="req-1",
    )


def test_bridge_implements_canonical_provider_protocol() -> None:
    client = LLMClient()
    provider = AssessmentAgentProvider(
        LLMAssessmentAdapter(client)
    )

    assert isinstance(
        provider,
        StructuredAgentProvider,
    )


def test_native_structured_client_receives_exact_schema(
    monkeypatch,
) -> None:
    client = LLMClient(
        model="test-model",
        supports_structured_output=True,
    )
    adapter = LLMAssessmentAdapter(client)
    provider = AssessmentAgentProvider(adapter)

    calls: list[dict[str, object]] = []

    def generate(prompt: str, **kwargs):
        calls.append(
            {"prompt": prompt, **kwargs}
        )
        return '{"kind":"final"}'

    monkeypatch.setattr(
        client,
        "generate",
        generate,
    )

    request = _request()
    response = provider.generate_agent_decision(
        request
    )

    assert response.payload == '{"kind":"final"}'
    assert len(calls) == 1
    assert (
        calls[0]["response_schema"]
        == request.response_schema
    )
    assert (
        calls[0]["system_prompt"]
        == request.system_prompt
    )
    assert calls[0]["purpose"] == "agent_decision"
    assert calls[0]["request_id"] == "req-1"
    assert calls[0]["max_tokens"] <= (
        MAX_AGENT_OUTPUT_TOKENS
    )


def test_json_object_fallback_does_not_change_authority_schema(
    monkeypatch,
) -> None:
    client = LLMClient(
        supports_structured_output=False,
        supports_json_object_output=True,
    )
    provider = AssessmentAgentProvider(
        LLMAssessmentAdapter(client)
    )

    calls: list[dict[str, object]] = []

    def generate(prompt: str, **kwargs):
        calls.append(
            {"prompt": prompt, **kwargs}
        )
        return '{"kind":"final"}'

    monkeypatch.setattr(
        client,
        "generate",
        generate,
    )

    provider.generate_agent_decision(
        _request()
    )

    assert len(calls) == 1
    assert calls[0]["json_object"] is True
    assert "response_schema" not in calls[0]
    assert "semantic" not in str(calls[0]).lower()
    assert "target resolver" not in str(
        calls[0]
    ).lower()


def test_usage_is_provider_neutral(
    monkeypatch,
) -> None:
    client = LLMClient(
        model="model-x",
        supports_structured_output=True,
    )
    provider = AssessmentAgentProvider(
        LLMAssessmentAdapter(client)
    )

    def generate(prompt: str, **kwargs):
        client._last_usage = ModelCallUsage(
            input_tokens=10,
            visible_output_tokens=5,
            total_output_tokens=5,
            provider="openai",
            model="model-x",
            purpose="agent_decision",
        )
        return '{"kind":"final"}'

    monkeypatch.setattr(
        client,
        "generate",
        generate,
    )

    response = provider.generate_agent_decision(
        _request()
    )

    assert response.provider == "openai"
    assert response.model == "model-x"
    assert response.raw_usage is not None
    assert response.raw_usage["input_tokens"] == 10


def test_generic_adapter_gets_transport_schema() -> None:
    from src.model.assessment_model_adapter import (
        AssessmentModelAdapter,
    )

    class GenericAdapter(AssessmentModelAdapter):
        def __init__(self) -> None:
            self.prompt = ""

        def assess(self, assessment_request):
            raise AssertionError("not used")

        def assess_raw(self, prompt: str) -> str:
            self.prompt = prompt
            return '{"kind":"final"}'

    adapter = GenericAdapter()
    provider = AssessmentAgentProvider(adapter)

    response = provider.generate_agent_decision(
        _request()
    )

    assert response.payload == '{"kind":"final"}'
    assert "Response JSON Schema:" in adapter.prompt

    schema_text = adapter.prompt.split(
        "Response JSON Schema:\n",
        1,
    )[1].split("\n\nRequest:\n", 1)[0]

    assert json.loads(schema_text) == (
        _request().response_schema
    )
