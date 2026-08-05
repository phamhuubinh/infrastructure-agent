from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.pipeline.provenance import ClaimSourceLink


class FindingDecision(str, Enum):
    """Deterministic outcome of evaluating one rule."""

    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class Finding:
    """Serializable, source-linked output of deterministic reasoning.

    Scores are kept in the rule's native weight scale.  ``coverage`` and
    ``confidence`` are always normalized to 0..1, so callers never need to
    infer whether absent evidence was silently re-weighted.
    """

    id: str
    type: str
    score: float
    decision: FindingDecision
    severity: str
    supporting_fact_ids: tuple[str, ...] = ()
    contradicting_fact_ids: tuple[str, ...] = ()
    missing_facts: tuple[str, ...] = ()
    confidence: float = 0.0
    rule_version: str = "1.0.0"
    rule_id: str = ""
    coverage: float = 0.0
    maximum_observable_score: float = 0.0
    maximum_possible_score: float = 0.0
    source_links: tuple[ClaimSourceLink, ...] = ()
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.type:
            raise ValueError("finding id and type are required")
        if not isinstance(self.decision, FindingDecision):
            object.__setattr__(self, "decision", FindingDecision(self.decision))
        for name in ("coverage", "confidence"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"finding {name} must be between 0.0 and 1.0")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "score", float(self.score))
        object.__setattr__(
            self, "maximum_observable_score", float(self.maximum_observable_score)
        )
        object.__setattr__(
            self, "maximum_possible_score", float(self.maximum_possible_score)
        )

    @property
    def supporting_facts(self) -> tuple[str, ...]:
        """Compatibility/readability alias for supporting fact identifiers."""

        return self.supporting_fact_ids

    @property
    def contradicting_facts(self) -> tuple[str, ...]:
        return self.contradicting_fact_ids

    @property
    def missing_fact_ids(self) -> tuple[str, ...]:
        """Missing observations have no fact id; return their canonical metrics."""

        return self.missing_facts

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "score": self.score,
            "decision": self.decision.value,
            "severity": self.severity,
            "supporting_fact_ids": list(self.supporting_fact_ids),
            "contradicting_fact_ids": list(self.contradicting_fact_ids),
            "missing_facts": list(self.missing_facts),
            "confidence": self.confidence,
            "coverage": self.coverage,
            "maximum_observable_score": self.maximum_observable_score,
            "maximum_possible_score": self.maximum_possible_score,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "source_links": [link.to_dict() for link in self.source_links],
            "explanation": self.explanation,
        }
