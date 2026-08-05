"""Canonical semantic frame shared by deterministic routing stages.

The frame is intentionally small and contains only user-request semantics.  It
does not contain capability or evidence decisions.  Normalization creates it
once; intent and target resolution enrich it without parsing independent
copies of the raw request.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


def _enum_name(value: object) -> object:
    return value.name if isinstance(value, Enum) else value


@dataclass(frozen=True, slots=True)
class RequestFrame:
    """Canonical, auditable interpretation of one user request.

    ``concepts`` may contain more than one explicitly mentioned concept.  The
    compatibility properties ``concept``, ``action`` and ``target`` let older
    capability-planning code consume the same object while the canonical API
    uses ``concepts``, ``operation`` and ``target_resolved``.
    """

    raw_request: str
    concepts: tuple[str, ...] = ()
    operation: str = "inspect"
    target_raw: str | None = None
    target_resolved: str | None = None
    parameters: object | None = None
    answer_type: object | None = None
    timeframe: object | None = None
    confidence: float = 0.0
    ambiguity: tuple[str, ...] = ()
    lexical_tokens: tuple[str, ...] = ()
    matched_synonyms: tuple[str, ...] = ()
    concept_candidates: tuple[object, ...] = ()
    intent_candidates: tuple[object, ...] = ()
    target_candidates: tuple[object, ...] = ()
    routing_status: object | None = None

    @property
    def concept(self) -> str:
        """Backward-compatible primary concept."""
        return self.concepts[0] if self.concepts else "machine"

    @property
    def action(self) -> str:
        """Backward-compatible operation name."""
        return self.operation

    @property
    def target(self) -> str | None:
        """Backward-compatible resolved target."""
        return self.target_resolved

    def evolve(self, **changes: Any) -> RequestFrame:
        """Return an enriched frame while preserving immutable semantics."""
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        """Return a credential-free, JSON-safe representation for tracing."""

        def _candidate(candidate: object) -> dict[str, object]:
            to_dict = getattr(candidate, "to_dict", None)
            if callable(to_dict):
                result = to_dict()
                if isinstance(result, dict):
                    return {str(k): _enum_name(v) for k, v in result.items()}
            return {"label": str(candidate)}

        raw_params: dict[str, object] = {}
        if self.parameters is not None:
            to_dict = getattr(self.parameters, "to_dict", None)
            if callable(to_dict):
                value = to_dict()
                if isinstance(value, dict):
                    raw_params = {str(k): _enum_name(v) for k, v in value.items()}

        return {
            "raw_request": self.raw_request,
            "concepts": list(self.concepts),
            "operation": self.operation,
            "target_raw": self.target_raw,
            "target_resolved": self.target_resolved,
            "parameters": raw_params,
            "answer_type": _enum_name(self.answer_type),
            "timeframe": self.timeframe,
            "confidence": self.confidence,
            "ambiguity": list(self.ambiguity),
            "lexical_tokens": list(self.lexical_tokens),
            "matched_synonyms": list(self.matched_synonyms),
            "concept_candidates": [
                _candidate(candidate) for candidate in self.concept_candidates
            ],
            "intent_candidates": [
                _candidate(candidate) for candidate in self.intent_candidates
            ],
            "target_candidates": [
                _candidate(candidate) for candidate in self.target_candidates
            ],
            "routing_status": _enum_name(self.routing_status),
        }


@dataclass(slots=True)
class RequestFrameExpectation:
    """Optional expected frame used by stage-level QA traces."""

    concepts: tuple[str, ...] = ()
    operation: str | None = None
    target: str | None = None
    parameters: dict[str, str] = field(default_factory=dict)
    answer_type: object | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "concepts": list(self.concepts),
            "operation": self.operation,
            "target": self.target,
            "parameters": dict(self.parameters),
            "answer_type": _enum_name(self.answer_type),
        }
