"""OpenAI-compatible model I/O for the canonical Orion agent.

This adapter owns provider connectivity only. It does not build legacy
assessment prompts, resolve intents, inspect evidence semantics, select
capabilities, resolve references, or grant execution authority.
"""

from __future__ import annotations

from dataclasses import replace

from src.model.agent_backend import AgentModelBackend
from src.model.llm_client import LLMClient
from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT
from src.model.reasoning_effort import (
    ModelRequestClass,
    ReasoningEffortPolicy,
)
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.input_context_budget import InputContextBudget
from src.shared.logger import info as _info


class AgentLLMAdapter(AgentModelBackend):
    """Provider connectivity used by the canonical agent runtime."""

    def __init__(
        self,
        client: LLMClient,
    ) -> None:
        if not isinstance(client, LLMClient):
            raise TypeError(
                "client must be LLMClient."
            )

        self._client = client
        self._last_input_estimate: int | None = None

    @property
    def last_usage(
        self,
    ) -> ModelCallUsage | None:
        usage = self._client.last_usage

        if (
            usage is None
            or self._last_input_estimate is None
        ):
            return usage

        return replace(
            usage,
            estimated_input_tokens=(
                self._last_input_estimate
            ),
        )

    def complete(
        self,
        prompt: str,
    ) -> str:
        if not isinstance(prompt, str):
            raise TypeError(
                "prompt must be text."
            )

        self._last_input_estimate = (
            InputContextBudget
            .estimated_tokens(
                ORION_SYSTEM_PROMPT
                + prompt
            )
        )

        effort = (
            ReasoningEffortPolicy.for_call(
                purpose="response",
                request_class=(
                    ModelRequestClass.NORMAL
                ),
            )
        )

        try:
            response = self._client.generate(
                prompt,
                system_prompt=(
                    ORION_SYSTEM_PROMPT
                ),
                purpose="response",
                reasoning_effort=effort,
            )
        except Exception as exc:
            _info(
                "llm",
                status="error",
                mode="agent_raw",
                error=str(exc)[:80],
                message=(
                    "Canonical model raw "
                    "call failed"
                ),
            )
            raise

        usage = self.last_usage

        _info(
            "llm",
            status="success",
            mode="agent_raw",
            input_tokens=(
                usage.input_tokens
                if usage
                else "N/A"
            ),
            reasoning_tokens=(
                usage.reasoning_tokens
                if usage
                else "N/A"
            ),
            output_tokens=(
                usage.visible_output_tokens
                if usage
                else "N/A"
            ),
            message=(
                "Canonical model raw "
                "response received"
            ),
        )

        return response

    def health_check(
        self,
        timeout: float = 5.0,
    ) -> bool:
        try:
            return bool(
                self._client.health_check(
                    timeout=max(1, int(timeout))
                )
            )
        except Exception:
            return False


__all__ = ["AgentLLMAdapter"]
