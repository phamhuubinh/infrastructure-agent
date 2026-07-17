from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.evidence_requirement import EvidenceRequirement

if TYPE_CHECKING:
    from src.pipeline.capability_reference import CapabilityReference
    from src.pipeline.execution_graph import ExecutionGraph
    from src.pipeline.execution_plan import ExecutionPlan
    from src.pipeline.intent_resolver import Confidence, Intent


@dataclass
class InvestigationRequest:
    """Primary data object flowing through the execution pipeline.

    Created by IntentResolver, enriched by each subsequent pipeline stage.
    No stage re-parses the original request — each stage reads from and
    writes to this single object.

    Attributes:
        raw_request: The original user request text.
        intent: Resolved investigation intent.
        confidence: Confidence in the resolved intent.
        matched_keywords: Keywords that triggered the intent classification.
        target: Resolved investigation target (set by TargetResolver).
        required_evidence: Evidence items that must be collected before
                           assessment begins (set by EvidencePlanner).
        optional_evidence: Evidence items collected only when additional
                           confidence or validation is needed.
        capability_references: Abstract capability identifiers mapped from
                               evidence requirements (set by CapabilityResolver).
        execution_plan: Ordered list of execution steps describing
                        investigation work (set by ExecutionPlanner).
        execution_graph: The execution graph (set by ExecutionGraphBuilder).
        evidence: Collected evidence (set by EvidenceMerge via ExecutionEngine).
        evidence_complete: True if all required evidence has been collected
                           (set by EvidenceCompleteness).
        missing_evidence: Evidence names that are required but not collected
                          (set by EvidenceCompleteness).
    """

    raw_request: str
    intent: Intent | None = None
    confidence: Confidence | None = None
    matched_keywords: tuple[str, ...] = ()
    target: str | None = None
    required_evidence: list[EvidenceRequirement] = field(default_factory=list)
    optional_evidence: list[EvidenceRequirement] = field(default_factory=list)
    capability_references: list[CapabilityReference] = field(default_factory=list)
    execution_plan: ExecutionPlan | None = None
    execution_graph: ExecutionGraph | None = None
    evidence: list[EvidencePackage] = field(default_factory=list)
    evidence_complete: bool = False
    missing_evidence: tuple[str, ...] = ()
    runtime_metrics: object = field(default_factory=lambda: None)
