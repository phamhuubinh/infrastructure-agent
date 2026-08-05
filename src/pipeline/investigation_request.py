from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.fact_set import FactSet
from src.pipeline.request_frame import RequestFrame, RequestFrameExpectation
from src.pipeline.routing_decision import EvidenceStatus, RoutingStatus

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
    request_frame: RequestFrame | None = None
    # Deprecated compatibility alias. Production pipeline code keeps this
    # reference identical to ``request_frame``.
    semantic_request: object | None = None
    expected_request_frame: RequestFrameExpectation | None = None
    intent_candidates: tuple[object, ...] = ()
    intent_score: float | None = None
    intent_margin: float | None = None
    target_candidates: tuple[object, ...] = ()
    target_score: float | None = None
    target_margin: float | None = None
    routing_status: RoutingStatus | None = None
    evidence_status: EvidenceStatus | None = None
    answer_strategy: object | None = None
    llm_usage_reason: object | None = None
    required_evidence: list[EvidenceRequirement] = field(default_factory=list)
    optional_evidence: list[EvidenceRequirement] = field(default_factory=list)
    capability_references: list[CapabilityReference] = field(default_factory=list)
    execution_plan: ExecutionPlan | None = None
    execution_graph: ExecutionGraph | None = None
    evidence: list[EvidencePackage] = field(default_factory=list)
    evidence_complete: bool = False
    missing_evidence: tuple[str, ...] = ()
    extracted_params: object = field(default_factory=lambda: None)
    answer_type: object = field(default_factory=lambda: None)
    selected_tool: object = field(default_factory=lambda: None)
    runtime_metrics: object = field(default_factory=lambda: None)
    subrequests: tuple[RequestFrame, ...] = ()
    bound_params: dict[str, dict[str, object]] = field(default_factory=dict)
    temporal_evidence_failures: tuple[str, ...] = ()
    fact_set: FactSet = field(default_factory=FactSet)
    contradictions: tuple[object, ...] = ()
    evidence_completeness: object | None = None

    def __post_init__(self) -> None:
        if self.request_frame is None and isinstance(
            self.semantic_request, RequestFrame
        ):
            self.request_frame = self.semantic_request
        elif self.semantic_request is None and self.request_frame is not None:
            self.semantic_request = self.request_frame

    def set_request_frame(self, frame: RequestFrame) -> None:
        """Set the single canonical frame and its compatibility alias."""
        self.request_frame = frame
        self.semantic_request = frame
