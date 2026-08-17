"""Normalized per-call model usage contract.

Providers report token usage in different payload shapes. This module
defines one internal representation so telemetry consumers never depend on
a provider-specific payload. Missing fields stay ``None`` (unknown) — they
are never coerced to zero — and hidden reasoning text is never stored:
only token counts are.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelCallUsage:
    """Normalized usage for exactly one model call.

    ``None`` means the provider did not report the value (unknown), not zero.
    ``visible_output_tokens`` is derived: the provider total output minus any
    reported reasoning tokens. When the provider reports no reasoning
    breakdown, the total is treated as visible best-effort.
    """

    input_tokens: int | None = None
    reasoning_tokens: int | None = None
    visible_output_tokens: int | None = None
    total_output_tokens: int | None = None
    model: str | None = None
    provider: str | None = None
    purpose: str | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize with explicit ``None`` so unknown stays unknown."""

        return {
            "input_tokens": self.input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "visible_output_tokens": self.visible_output_tokens,
            "total_output_tokens": self.total_output_tokens,
            "model": self.model,
            "provider": self.provider,
            "purpose": self.purpose,
            "latency_ms": self.latency_ms,
        }


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def normalize_openai_usage(
    usage: object,
    *,
    model: str | None = None,
    provider: str | None = None,
    purpose: str | None = None,
    latency_ms: float | None = None,
) -> ModelCallUsage:
    """Normalize an OpenAI-compatible chat-completions ``usage`` payload.

    Recognized keys: ``prompt_tokens``, ``completion_tokens``, and
    ``completion_tokens_details.reasoning_tokens``. Anything else is ignored.
    A missing or malformed ``usage`` value yields an all-unknown token set
    while keeping the supplied metadata.
    """

    metadata = ModelCallUsage(
        model=model,
        provider=provider,
        purpose=purpose,
        latency_ms=latency_ms,
    )
    if not isinstance(usage, dict):
        return metadata
    input_tokens = _to_int(usage.get("prompt_tokens"))
    total_output_tokens = _to_int(usage.get("completion_tokens"))
    details = usage.get("completion_tokens_details")
    reasoning_tokens = None
    if isinstance(details, dict):
        reasoning_tokens = _to_int(details.get("reasoning_tokens"))
    visible_output_tokens: int | None
    if reasoning_tokens is not None and total_output_tokens is not None:
        visible_output_tokens = max(total_output_tokens - reasoning_tokens, 0)
    else:
        visible_output_tokens = total_output_tokens
    return ModelCallUsage(
        input_tokens=input_tokens,
        reasoning_tokens=reasoning_tokens,
        visible_output_tokens=visible_output_tokens,
        total_output_tokens=total_output_tokens,
        model=model,
        provider=provider,
        purpose=purpose,
        latency_ms=latency_ms,
    )


def normalize_anthropic_usage(
    usage: object,
    *,
    has_hidden_reasoning: bool | None = None,
    model: str | None = None,
    provider: str | None = "anthropic",
    purpose: str | None = None,
    latency_ms: float | None = None,
) -> ModelCallUsage:
    """Normalize an Anthropic Messages API ``usage`` object.

    Anthropic reports ``input_tokens`` and ``output_tokens`` without a
    reasoning/visible split, so ``reasoning_tokens`` stays unknown. When
    ``has_hidden_reasoning`` is true (a ``thinking`` content block was
    present), the visible-output share cannot be derived and stays unknown;
    otherwise the total output is treated as visible.
    """

    input_tokens = _to_int(getattr(usage, "input_tokens", None))
    total_output_tokens = _to_int(getattr(usage, "output_tokens", None))
    visible_output_tokens = (
        total_output_tokens
        if has_hidden_reasoning is False
        else None
    )
    return ModelCallUsage(
        input_tokens=input_tokens,
        reasoning_tokens=None,
        visible_output_tokens=visible_output_tokens,
        total_output_tokens=total_output_tokens,
        model=model,
        provider=provider,
        purpose=purpose,
        latency_ms=latency_ms,
    )


def normalize_usage_mapping(
    raw_usage: object,
    *,
    purpose: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    latency_ms: float | None = None,
) -> ModelCallUsage:
    """Normalize a provider-neutral raw-usage mapping.

    Accepts either the OpenAI-compatible keys (``prompt_tokens``,
    ``completion_tokens``, optional ``completion_tokens_details`` /
    top-level ``reasoning_tokens``) or the Anthropic keys (``input_tokens``,
    ``output_tokens``). Non-mapping or unrecognized values yield an
    all-unknown token set while keeping the supplied metadata.
    """

    if not isinstance(raw_usage, Mapping):
        return ModelCallUsage(
            model=model,
            provider=provider,
            purpose=purpose,
            latency_ms=latency_ms,
        )
    if "prompt_tokens" in raw_usage or "completion_tokens" in raw_usage:
        usage_payload: dict[str, object] = {
            "prompt_tokens": raw_usage.get("prompt_tokens"),
            "completion_tokens": raw_usage.get("completion_tokens"),
        }
        details = raw_usage.get("completion_tokens_details")
        if isinstance(details, Mapping):
            usage_payload["completion_tokens_details"] = {
                "reasoning_tokens": details.get("reasoning_tokens")
            }
        elif "reasoning_tokens" in raw_usage:
            usage_payload["completion_tokens_details"] = {
                "reasoning_tokens": raw_usage.get("reasoning_tokens")
            }
        return normalize_openai_usage(
            usage_payload,
            model=model,
            provider=provider,
            purpose=purpose,
            latency_ms=latency_ms,
        )
    return normalize_anthropic_usage(
        _AnthropicUsageView(raw_usage),
        has_hidden_reasoning=False,
        model=model,
        provider=provider,
        purpose=purpose,
        latency_ms=latency_ms,
    )


class _AnthropicUsageView:
    """Mapping adapter exposing Anthropic attribute-style usage fields."""

    def __init__(self, mapping: Mapping[str, object]) -> None:
        self._mapping = mapping

    @property
    def input_tokens(self) -> object:
        return self._mapping.get("input_tokens")

    @property
    def output_tokens(self) -> object:
        return self._mapping.get("output_tokens")


__all__ = [
    "ModelCallUsage",
    "normalize_anthropic_usage",
    "normalize_openai_usage",
    "normalize_usage_mapping",
]
