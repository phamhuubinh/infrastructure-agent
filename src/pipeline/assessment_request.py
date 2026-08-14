from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.evidence_package import EvidencePackage
    from src.pipeline.fact import Fact
    from src.pipeline.finding import Finding
    from src.pipeline.health_aggregator import HealthSummary


@dataclass(frozen=True, slots=True)
class AssessmentRequest:
    """Immutable input to the Assessment Model.

    Wraps all collected evidence and investigation context into a
    single object that the Assessment Model receives. The model
    never accesses InvestigationRequest, ExecutionGraph, or any
    runtime object directly.

    Attributes:
        raw_request: The original user request.
        intent: The resolved investigation intent.
        evidence: All collected evidence packages.
        evidence_complete: Whether all required evidence was collected.
        missing_evidence: Evidence names that could not be collected.
        request_frame: Safe, already-serialized summary of the resolved
            ``RequestFrame`` (concepts/operation/target/params). This is a
            plain mapping, never the runtime ``RequestFrame`` object, so the
            model boundary stays decoupled from pipeline internals.
        unknowns: Canonical metrics/facts that are required by the
            investigation but were not observed (missing, failed, or
            unsupported). Distinct from ``missing_evidence`` (legacy,
            evidence-name based) because this is fact/metric scoped.
        evidence_status: Canonical evidence status name (e.g.
            ``SUFFICIENT``/``PARTIAL``/``CONTRADICTORY``/``STALE``) describing
            the overall quality of the collected evidence for this request.
        allowed_claims: Opaque identifiers (fact ids and finding ids) that
            the model is permitted to ground numeric, target, or severity
            claims in. Anything not traceable to one of these ids is an
            ungrounded claim.
        raw_evidence_required: Explicit permission for the bounded model-context
            serializer to include fact-less provider payload. False by default.
    """

    raw_request: str
    intent: str = ""
    evidence: tuple[EvidencePackage, ...] = ()
    evidence_complete: bool = False
    missing_evidence: tuple[str, ...] = ()
    facts: tuple[Fact, ...] = ()
    collection_failures: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    health_summary: HealthSummary | None = None
    request_frame: Mapping[str, object] | None = None
    unknowns: tuple[str, ...] = ()
    evidence_status: str = ""
    allowed_claims: tuple[str, ...] = field(default_factory=tuple)
    raw_evidence_required: bool = False

    def __post_init__(self) -> None:
        if self.request_frame is not None and not isinstance(
            self.request_frame, MappingProxyType
        ):
            object.__setattr__(
                self, "request_frame", MappingProxyType(dict(self.request_frame))
            )

    @property
    def has_grounded_evidence(self) -> bool:
        """Whether the model has any fact or finding to ground claims in."""

        return bool(self.facts) or bool(self.findings) or bool(self.allowed_claims)
