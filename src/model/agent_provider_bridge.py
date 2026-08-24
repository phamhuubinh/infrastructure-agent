"""Bridge configured assessment models to the canonical agent provider protocol."""

from __future__ import annotations

import json

from src.model.agent_adapter import (
    AgentProviderRequest,
    AgentProviderResponse,
)
from src.model.agent_backend import AgentModelBackend
from src.model.llm_client import LLMClient
from src.model.usage_metadata import ModelCallUsage

_JSON_ONLY_HINT = (
    "Return only one JSON object matching the supplied response contract. "
    "Do not include markdown, prose outside the JSON object, hidden reasoning, "
    "credentials, commands, or executable code."
)


class AgentBackendProvider:
    """Expose one configured model as a canonical decision provider.

    This bridge performs model I/O only. It does not parse user intent,
    discover capabilities, grant authority, resolve references, or execute.
    """

    def __init__(self, backend: AgentModelBackend) -> None:
        if not isinstance(backend, AgentModelBackend):
            raise TypeError(
                "backend must implement AgentModelBackend."
            )
        self._backend = backend

    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ) -> AgentProviderResponse:
        if not isinstance(request, AgentProviderRequest):
            raise TypeError(
                "request must be AgentProviderRequest."
            )

        client = getattr(self._backend, "_client", None)

        if isinstance(client, LLMClient):
            payload = self._generate_llm_client(
                client,
                request,
            )
            usage = client.last_usage
            generation_diagnostics = client.last_generation_diagnostics
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
                self._backend,
                "last_usage",
                None,
            )
            generation_diagnostics = None
            fallback_provider = (
                type(self._backend).__name__
            )
            fallback_model = getattr(
                self._backend,
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
            generation_diagnostics=generation_diagnostics,
        )

    @staticmethod
    def _generate_llm_client(
        client: LLMClient,
        request: AgentProviderRequest,
    ) -> str:
        if client.supports_structured_output:
            return client.generate(
                request.user_prompt,
                request_id=request.request_id,
                purpose="agent_decision",
                system_prompt=request.system_prompt,
                response_schema=request.response_schema,
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

        return self._backend.complete(prompt)


__all__ = [
    "AgentBackendProvider",
]
