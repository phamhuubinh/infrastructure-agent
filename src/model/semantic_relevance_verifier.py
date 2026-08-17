"""One-shot structured semantic relevance verification for final drafts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.model.protocol.semantic_relevance_prompt import (
    build_semantic_relevance_prompt,
)
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.semantic_plan import SemanticPlan

MAX_RELEVANCE_OUTPUT_CHARS = 256


class SemanticRelevanceDecision(str, Enum):
    ALIGNED = "aligned"
    NOT_ALIGNED = "not_aligned"


class SemanticRelevanceReason(str, Enum):
    ALIGNED = "aligned"
    CROSS_TASK = "cross_task"
    REQUEST_NOT_ANSWERED = "request_not_answered"
    PLAN_MISMATCH = "plan_mismatch"
    INVALID_OUTPUT = "invalid_output"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


@dataclass(frozen=True, slots=True)
class SemanticRelevanceResult:
    decision: SemanticRelevanceDecision
    reason: SemanticRelevanceReason

    @property
    def aligned(self) -> bool:
        return self.decision is SemanticRelevanceDecision.ALIGNED

    def to_trace_dict(self) -> dict[str, str]:
        return {
            "decision": self.decision.value,
            "reason": self.reason.value,
        }


@runtime_checkable
class RawRelevanceModel(Protocol):
    """Narrow model boundary; deliberately exposes no tool method."""

    def assess_raw(self, prompt: str) -> str: ...


@runtime_checkable
class SemanticRelevanceVerifierProtocol(Protocol):
    def verify(
        self,
        original_request: str,
        plan: SemanticPlan,
        draft: str,
    ) -> SemanticRelevanceResult: ...


class SemanticRelevanceVerifier:
    """Make at most one authority-free model call and parse its tiny result."""

    def __init__(self, model: RawRelevanceModel) -> None:
        if not isinstance(model, RawRelevanceModel):
            raise TypeError("model must implement assess_raw().")
        self._model = model

    @property
    def last_usage(self) -> ModelCallUsage | None:
        """Normalized usage of the most recent verify call, when reported."""

        usage = getattr(self._model, "last_usage", None)
        return usage if isinstance(usage, ModelCallUsage) else None

    def verify(
        self,
        original_request: str,
        plan: SemanticPlan,
        draft: str,
    ) -> SemanticRelevanceResult:
        prompt = build_semantic_relevance_prompt(original_request, plan, draft)
        try:
            raw = self._model.assess_raw(prompt.render())
        except Exception:
            return _not_aligned(SemanticRelevanceReason.PROVIDER_UNAVAILABLE)
        return _parse_result(raw)


def _parse_result(raw: object) -> SemanticRelevanceResult:
    if not isinstance(raw, str) or len(raw) > MAX_RELEVANCE_OUTPUT_CHARS:
        return _not_aligned(SemanticRelevanceReason.INVALID_OUTPUT)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _not_aligned(SemanticRelevanceReason.INVALID_OUTPUT)
    if not isinstance(payload, dict) or set(payload) != {"decision", "reason"}:
        return _not_aligned(SemanticRelevanceReason.INVALID_OUTPUT)
    try:
        decision = SemanticRelevanceDecision(payload["decision"])
        reason = SemanticRelevanceReason(payload["reason"])
    except (TypeError, ValueError):
        return _not_aligned(SemanticRelevanceReason.INVALID_OUTPUT)

    provider_reasons = {
        SemanticRelevanceReason.ALIGNED,
        SemanticRelevanceReason.CROSS_TASK,
        SemanticRelevanceReason.REQUEST_NOT_ANSWERED,
        SemanticRelevanceReason.PLAN_MISMATCH,
    }
    if reason not in provider_reasons:
        return _not_aligned(SemanticRelevanceReason.INVALID_OUTPUT)
    if (decision is SemanticRelevanceDecision.ALIGNED) != (
        reason is SemanticRelevanceReason.ALIGNED
    ):
        return _not_aligned(SemanticRelevanceReason.INVALID_OUTPUT)
    return SemanticRelevanceResult(decision, reason)


def _not_aligned(reason: SemanticRelevanceReason) -> SemanticRelevanceResult:
    return SemanticRelevanceResult(SemanticRelevanceDecision.NOT_ALIGNED, reason)


__all__ = [
    "MAX_RELEVANCE_OUTPUT_CHARS",
    "RawRelevanceModel",
    "SemanticRelevanceDecision",
    "SemanticRelevanceReason",
    "SemanticRelevanceResult",
    "SemanticRelevanceVerifier",
    "SemanticRelevanceVerifierProtocol",
]
