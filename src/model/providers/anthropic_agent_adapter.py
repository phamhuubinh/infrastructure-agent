"""Anthropic model I/O for the canonical Orion agent."""

from __future__ import annotations

import time
from dataclasses import replace

from src.model.agent_backend import AgentModelBackend
from src.model.output_sanitizer import sanitize_model_output
from src.model.usage_metadata import (
    ModelCallUsage,
    normalize_anthropic_usage,
)
from src.pipeline.input_context_budget import InputContextBudget
from src.shared.logger import info as _info
from src.shared.logger import warning as _warning


class AnthropicAgentAdapter(
    AgentModelBackend
):
    """Anthropic provider connectivity without legacy semantic planning."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: int = 180,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._last_usage: (
            ModelCallUsage | None
        ) = None

    @property
    def last_usage(
        self,
    ) -> ModelCallUsage | None:
        return self._last_usage

    def _get_client(self):
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "anthropic package is required "
                "for the Anthropic provider."
            ) from None

        return anthropic.Anthropic(
            api_key=self._api_key,
            timeout=self._timeout,
        )

    @staticmethod
    def _normalize_usage(
        response: object,
        latency_ms: float,
    ) -> ModelCallUsage:
        content = getattr(
            response,
            "content",
            None,
        )

        has_hidden_reasoning = (
            any(
                "thinking"
                in str(
                    getattr(
                        block,
                        "type",
                        "",
                    )
                ).lower()
                for block in content
            )
            if isinstance(
                content,
                (list, tuple),
            )
            else None
        )

        return normalize_anthropic_usage(
            getattr(
                response,
                "usage",
                None,
            ),
            has_hidden_reasoning=(
                has_hidden_reasoning
            ),
            model=(
                getattr(
                    response,
                    "model",
                    None,
                )
                or None
            ),
            provider="anthropic",
            purpose="agent_decision",
            latency_ms=latency_ms,
        )

    def complete(
        self,
        prompt: str,
    ) -> str:
        if not isinstance(prompt, str):
            raise TypeError(
                "prompt must be text."
            )

        self._last_usage = None
        started = time.perf_counter()

        try:
            client = self._get_client()

            response = (
                client.messages.create(
                    model=self._model,
                    max_tokens=(
                        self._max_tokens
                    ),
                    temperature=(
                        self._temperature
                    ),
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                )
            )

            latency_ms = round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000,
                1,
            )

            content = sanitize_model_output(
                (
                    response
                    .content[0]
                    .text
                )
                if response.content
                else ""
            )

            self._last_usage = replace(
                self._normalize_usage(
                    response,
                    latency_ms,
                ),
                estimated_input_tokens=(
                    InputContextBudget
                    .estimated_tokens(
                        prompt
                    )
                ),
            )

            _info(
                "llm",
                status="success",
                mode="agent_raw",
                provider="anthropic",
                model=self._model,
                duration_ms=latency_ms,
                input_tokens=(
                    self._last_usage
                    .input_tokens
                ),
                reasoning_tokens=(
                    self._last_usage
                    .reasoning_tokens
                ),
                output_tokens=(
                    self._last_usage
                    .visible_output_tokens
                ),
                message=(
                    "Canonical Anthropic "
                    "response received"
                ),
            )

            return content

        except Exception as exc:
            latency_ms = round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000,
                1,
            )

            _warning(
                "llm",
                status="error",
                mode="agent_raw",
                provider="anthropic",
                model=self._model,
                duration_ms=latency_ms,
                error=str(exc)[:80],
                message=(
                    "Canonical Anthropic "
                    "call failed"
                ),
            )

            raise

    def health_check(
        self,
        timeout: float = 5.0,
    ) -> bool:
        try:
            client = self._get_client()

            client.messages.create(
                model=self._model,
                max_tokens=1,
                messages=[
                    {
                        "role": "user",
                        "content": "ok",
                    }
                ],
                timeout=timeout,
            )

            return True

        except Exception:
            return False


__all__ = ["AnthropicAgentAdapter"]
