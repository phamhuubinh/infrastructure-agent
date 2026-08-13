"""Immutable contract for a model-proposed semantic plan.

The plan describes user intent only.  It deliberately contains no raw command,
tool schema, provider credential, or evidence payload, and it grants no
execution authority.  Later harness stages validate a plan before binding it
to an existing capability contract.

Serialization, parsing, provider integration, and execution are separate
boundaries and are intentionally absent from this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)


class SemanticPlanRoute(str, Enum):
    """The next semantic path proposed by the planner."""

    UNSPECIFIED = "unspecified"
    UNKNOWN = "unknown"
    DIRECT_ANSWER = "direct_answer"
    CAPABILITY_ASSISTED = "capability_assisted"
    REFUSE = "refuse"
    CLARIFY = "clarify"


class TargetReferenceKind(str, Enum):
    """How a target reference appeared in the request or session context."""

    UNSPECIFIED = "unspecified"
    UNKNOWN = "unknown"
    EXPLICIT = "explicit"
    INHERITED = "inherited"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class TargetReference:
    """Unvalidated target text and its semantic origin.

    ``value`` is a name or alias proposed from user/session semantics.  It is
    not a resolved registry target and must not be used for dispatch directly.
    """

    kind: TargetReferenceKind = TargetReferenceKind.UNSPECIFIED
    value: str | None = None


class FreshnessRequirement(str, Enum):
    """Normalized freshness semantics independent of source availability."""

    UNSPECIFIED = "unspecified"
    UNKNOWN = "unknown"
    STABLE = "stable"
    CURRENT = "current"
    LATEST = "latest"
    RECENT = "recent"
    REAL_TIME = "real_time"
    HISTORICAL = "historical"


class DeterministicComputeIntent(str, Enum):
    """Whether exact deterministic computation is part of the request."""

    UNSPECIFIED = "unspecified"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"


class ClarificationState(str, Enum):
    """Whether the proposed plan can proceed without user clarification."""

    UNSPECIFIED = "unspecified"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class SemanticPlan:
    """Compact, typed semantics proposed by a model planner.

    Defaults are intentionally non-executable.  In particular, an empty plan
    does not mean a general answer, a live infrastructure request, or an
    implicit ``localhost`` target.
    """

    route: SemanticPlanRoute = SemanticPlanRoute.UNSPECIFIED
    domain: RequestDomain = RequestDomain.UNSPECIFIED
    execution_intent: ExecutionIntent = ExecutionIntent.UNSPECIFIED
    target: TargetReference = field(default_factory=TargetReference)
    source_constraints: tuple[SourceConstraint, ...] = (SourceConstraint.UNSPECIFIED,)
    excluded_sources: tuple[SourceConstraint, ...] = ()
    freshness: FreshnessRequirement = FreshnessRequirement.UNSPECIFIED
    metric: str | None = None
    concept: str | None = None
    service: str | None = None
    path: str | None = None
    explicit_url: str | None = None
    deterministic_compute: DeterministicComputeIntent = (
        DeterministicComputeIntent.UNSPECIFIED
    )
    clarification: ClarificationState = ClarificationState.UNSPECIFIED
    clarification_field: str | None = None


__all__ = [
    "ClarificationState",
    "DeterministicComputeIntent",
    "FreshnessRequirement",
    "SemanticPlan",
    "SemanticPlanRoute",
    "TargetReference",
    "TargetReferenceKind",
]
