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

from src.pipeline.request_semantics import (
    ExecutionIntent,
    ExternalNeed,
    InformationScope,
    RequestDomain,
    SourceConstraint,
)


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
    context_applied: tuple[str, ...] = ()
    context_snapshot: dict[str, object] = field(default_factory=dict)
    subframes: tuple[RequestFrame, ...] = ()
    request_domain: RequestDomain = RequestDomain.GENERAL
    information_scope: InformationScope = InformationScope.STABLE_KNOWLEDGE
    external_need: ExternalNeed = ExternalNeed.NONE
    source_constraints: tuple[SourceConstraint, ...] = (SourceConstraint.ANY,)
    excluded_sources: tuple[SourceConstraint, ...] = ()
    explicit_url: str | None = None
    url_error: str | None = None
    url_literal: bool = False
    execution_intent: ExecutionIntent = ExecutionIntent.EXPLAIN
    freshness_phrase: str | None = None
    freshness_window: str | None = None

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

        timeframe: object = self.timeframe
        timeframe_to_dict = getattr(timeframe, "to_dict", None)
        if callable(timeframe_to_dict):
            timeframe = timeframe_to_dict()

        return {
            "raw_request": self.raw_request,
            "concepts": list(self.concepts),
            "operation": self.operation,
            "target_raw": self.target_raw,
            "target_resolved": self.target_resolved,
            "parameters": raw_params,
            "answer_type": _enum_name(self.answer_type),
            "timeframe": timeframe,
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
            "context_applied": list(self.context_applied),
            "context_snapshot": dict(self.context_snapshot),
            "request_domain": self.request_domain.name,
            "information_scope": self.information_scope.name,
            "external_need": self.external_need.name,
            "source_constraints": [source.name for source in self.source_constraints],
            "excluded_sources": [source.name for source in self.excluded_sources],
            "explicit_url": self.explicit_url,
            "url_error": self.url_error,
            "url_literal": self.url_literal,
            "execution_intent": self.execution_intent.name,
            "freshness_phrase": self.freshness_phrase,
            "freshness_window": self.freshness_window,
            "subframes": [
                {
                    "concepts": list(frame.concepts),
                    "operation": frame.operation,
                    "target_raw": frame.target_raw,
                }
                for frame in self.subframes
            ],
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
