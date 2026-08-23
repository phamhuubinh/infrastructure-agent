"""Bridge configured assessment models to the canonical agent provider protocol."""

from __future__ import annotations

import json

from src.model.agent_adapter import (
    AgentProviderRequest,
    AgentProviderResponse,
)
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.llm_client import LLMClient
from src.model.usage_metadata import ModelCallUsage


MAX_AGENT_OUTPUT_TOKENS = 1024

_JSON_ONLY_HINT = (
    "Return only one JSON object matching the supplied response contract. "
    "Do not include markdown, prose outside the JSON object, hidden reasoning, "
    "credentials, commands, or executable code."
)


class AssessmentAgentProvider:
    """Expose one configured model as a canonical decision provider.

    This bridge performs model I/O only. It does not parse user intent,
    discover capabilities, grant authority, resolve references, or execute.
    """

    def __init__(self, model: AssessmentModelAdapter) -> None:
        if not isinstance(model, AssessmentModelAdapter):
            raise TypeError(
                "model must be an AssessmentModelAdapter."
            )
        self._model = model

    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ) -> AgentProviderResponse:
        if not isinstance(request, AgentProviderRequest):
            raise TypeError(
                "request must be AgentProviderRequest."
            )

        client = getattr(self._model, "_client", None)

        if isinstance(client, LLMClient):
            payload = self._generate_llm_client(
                client,
                request,
            )
            usage = client.last_usage
            fallback_provider = getattr(
                client,
                "_provider",
                "configured",
            )
            fallback_model = getattr(
                client,
                "_model",
                "configured",
            )
        else:
            payload = self._generate_generic(request)
            usage = getattr(
                self._model,
                "last_usage",
                None,
            )
            fallback_provider = (
                type(self._model).__name__
            )
            fallback_model = getattr(
                self._model,
                "_model",
                "configured",
            )

        normalized_usage = (
            usage
            if isinstance(usage, ModelCallUsage)
            else None
        )

        return AgentProviderResponse(
            payload=payload,
            provider=(
                normalized_usage.provider
                if (
                    normalized_usage is not None
                    and normalized_usage.provider
                )
                else str(fallback_provider)
            ),
            model=(
                normalized_usage.model
                if (
                    normalized_usage is not None
                    and normalized_usage.model
                )
                else str(fallback_model)
            ),
            raw_usage=(
                normalized_usage.to_dict()
                if normalized_usage is not None
                else None
            ),
        )

    @staticmethod
    def _generate_llm_client(
        client: LLMClient,
        request: AgentProviderRequest,
    ) -> str:
        max_tokens = min(
            MAX_AGENT_OUTPUT_TOKENS,
            client.max_tokens,
        )

        if client.supports_structured_output:
            return client.generate(
                request.user_prompt,
                request_id=request.request_id,
                purpose="agent_decision",
                system_prompt=request.system_prompt,
                response_schema=request.response_schema,
                max_tokens=max_tokens,
            )

        return client.generate(
            request.user_prompt,
            request_id=request.request_id,
            purpose="agent_decision",
            system_prompt=(
                request.system_prompt
                + "\n\n"
                + _JSON_ONLY_HINT
            ),
            json_object=(
                client.supports_json_object_output
            ),
            max_tokens=max_tokens,
        )

    def _generate_generic(
        self,
        request: AgentProviderRequest,
    ) -> str:
        # Provider adapters without LLMClient still receive the exact
        # canonical transport contract. The downstream canonical parser
        # remains authoritative.
        schema = json.dumps(
            request.response_schema,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

        prompt = (
            request.system_prompt
            + "\n\n"
            + _JSON_ONLY_HINT
            + "\nResponse JSON Schema:\n"
            + schema
            + "\n\nRequest:\n"
            + request.user_prompt
        )

        return self._model.assess_raw(prompt)


__all__ = [
    "AssessmentAgentProvider",
    "MAX_AGENT_OUTPUT_TOKENS",
]
