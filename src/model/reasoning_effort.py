"""Provider-neutral reasoning-effort policy for model calls.

The policy maps already-known call purpose and request complexity to a small
portable effort preference. Provider adapters decide whether they support an
effort option; unsupported providers keep their existing request shape.
"""

from __future__ import annotations

from enum import Enum


class ReasoningEffort(str, Enum):
    """Portable effort levels; provider adapters may translate or ignore them."""

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelRequestClass(str, Enum):
    """Coarse request complexity used only for model-effort selection."""

    TRIVIAL = "trivial"
    NORMAL = "normal"
    EVIDENCE_ASSISTED = "evidence_assisted"
    MULTI_SOURCE_DIAGNOSIS = "multi_source_diagnosis"


class ReasoningEffortPolicy:
    """Choose the smallest useful effort for a model call."""

    _LOW_EFFORT_PURPOSES = frozenset({"relevance", "repair"})

    @classmethod
    def for_call(
        cls,
        *,
        purpose: str,
        request_class: ModelRequestClass,
    ) -> ReasoningEffort:
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError("purpose must be non-empty text.")
        if not isinstance(request_class, ModelRequestClass):
            raise TypeError("request_class must be ModelRequestClass.")

        normalized_purpose = purpose.strip().casefold()
        if normalized_purpose == "controller.first_decision":
            return ReasoningEffort.MINIMAL
        if normalized_purpose.startswith("controller."):
            return ReasoningEffort.LOW
        if normalized_purpose == "planner":
            return ReasoningEffort.MINIMAL
        if normalized_purpose in cls._LOW_EFFORT_PURPOSES:
            return ReasoningEffort.LOW
        if request_class is ModelRequestClass.TRIVIAL:
            return ReasoningEffort.MINIMAL
        if request_class is ModelRequestClass.MULTI_SOURCE_DIAGNOSIS:
            return ReasoningEffort.HIGH
        if request_class is ModelRequestClass.EVIDENCE_ASSISTED:
            return ReasoningEffort.MEDIUM
        return ReasoningEffort.LOW


__all__ = [
    "ModelRequestClass",
    "ReasoningEffort",
    "ReasoningEffortPolicy",
]
