"""Canonical deterministic routing and response taxonomies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from src.pipeline.request_frame import RequestFrame


class RoutingStatus(Enum):
    RESOLVED = auto()
    CLARIFICATION_REQUIRED = auto()
    FALLBACK = auto()
    UNSUPPORTED = auto()
    GENERAL_CHAT = auto()
    EXTERNAL_VERIFICATION = auto()
    SOURCE_UNAVAILABLE = auto()


class EvidenceStatus(Enum):
    NOT_APPLICABLE = auto()
    SUFFICIENT = auto()
    PARTIAL = auto()
    UNAVAILABLE = auto()
    STALE = auto()
    CONTRADICTORY = auto()


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    status: RoutingStatus
    request_frame: RequestFrame
    reason: str | None = None
    missing_field: str | None = None
    candidates: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status is RoutingStatus.RESOLVED


class RoutingClarificationError(ValueError):
    """Raised before execution when required routing semantics are ambiguous."""

    def __init__(self, decision: RoutingDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason or "Request clarification is required")
