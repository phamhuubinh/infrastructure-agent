"""Bounded per-request model-usage recorder for execution traces.

Aggregates counts/latency/tokens per call purpose while retaining a bounded
number of per-call entries. Never stores prompt text, credentials, or hidden
reasoning. Unknown fields stay explicitly ``None``, both per call and in the
aggregates.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.model.usage_metadata import (
    ModelCallUsage,
    normalize_usage_mapping,
)

MAX_RECORDED_CALLS = 16

_AGGREGATE_FIELDS = (
    "latency_ms",
    "input_tokens",
    "reasoning_tokens",
    "visible_output_tokens",
    "total_output_tokens",
    "estimated_input_tokens",
)


class ModelUsageRecorder:
    """Collect normalized usage for one request and emit a safe trace dict."""

    def __init__(self) -> None:
        self._calls: list[ModelCallUsage] = []

    @property
    def calls(self) -> tuple[ModelCallUsage, ...]:
        return tuple(self._calls)

    def reset(self) -> None:
        self._calls.clear()

    def record(self, usage: ModelCallUsage) -> None:
        """Record one normalized call; purpose stays as supplied."""

        if not isinstance(usage, ModelCallUsage):
            raise TypeError("usage must be a ModelCallUsage.")
        self._calls.append(usage)

    def record_mapping(
        self,
        raw_usage: object,
        *,
        purpose: str | None,
        provider: str | None = None,
        model: str | None = None,
        latency_ms: float | None = None,
        estimated_input_tokens: int | None = None,
        configured_effort: str | None = None,
        call_stage: str | None = None,
    ) -> None:
        """Normalize a provider-neutral raw-usage mapping and record it.

        ``estimated_input_tokens`` is recorded alongside — never instead of
        — the provider-reported input tokens from ``raw_usage``.
        """

        usage = normalize_usage_mapping(
            raw_usage,
            purpose=purpose,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            configured_effort=configured_effort,
        )
        if estimated_input_tokens is not None:
            usage = replace(usage, estimated_input_tokens=estimated_input_tokens)
        if call_stage is not None:
            usage = replace(usage, call_stage=call_stage)
        self.record(usage)

    def to_trace_dict(self) -> dict[str, Any]:
        """Emit counts, per-purpose aggregates, and bounded per-call entries.

        Aggregates use strict unknown propagation: a per-purpose field is
        only emitted as a numeric total when *every* call of that purpose
        reported it. One unknown call makes the aggregate unknown (None) —
        a partial sum is never presented as a complete exact total. The
        call count itself always stays exact.
        """

        by_purpose: dict[str, dict[str, Any]] = {}
        unknown_fields: dict[str, set[str]] = {}
        for call in self._calls:
            key = call.purpose or "unknown"
            bucket = by_purpose.setdefault(
                key,
                {"calls": 0, **{field: None for field in _AGGREGATE_FIELDS}},
            )
            bucket["calls"] = bucket["calls"] + 1
            for field in _AGGREGATE_FIELDS:
                value = getattr(call, field)
                if value is None:
                    unknown_fields.setdefault(key, set()).add(field)
                    continue
                current = bucket[field]
                if current is None:
                    bucket[field] = value
                elif isinstance(current, int) and isinstance(value, int):
                    bucket[field] = current + value
                else:
                    bucket[field] = float(current) + float(value)
        for key, fields in unknown_fields.items():
            for field in fields:
                by_purpose[key][field] = None
        recorded = self._calls[:MAX_RECORDED_CALLS]
        return {
            "calls": len(self._calls),
            "by_purpose": by_purpose,
            "per_call": [call.to_dict() for call in recorded],
            "dropped_calls": max(len(self._calls) - MAX_RECORDED_CALLS, 0),
        }


__all__ = [
    "MAX_RECORDED_CALLS",
    "ModelUsageRecorder",
]
