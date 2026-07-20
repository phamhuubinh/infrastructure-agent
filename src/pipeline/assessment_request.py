from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.evidence_package import EvidencePackage


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
    """

    raw_request: str
    intent: str = ""
    evidence: tuple[EvidencePackage, ...] = ()
    evidence_complete: bool = False
    missing_evidence: tuple[str, ...] = ()
