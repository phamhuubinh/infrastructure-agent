from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from src.pipeline.fact_set import FactSet

if TYPE_CHECKING:
    pass

# A StateUpdate is a partial dict of fields that a stage contributes.
StateUpdate = dict[str, Any]


@dataclass(frozen=True)
class PipelineState:
    """Immutable pipeline state — accumulated through stages.

    Each stage returns a StateUpdate (partial dict).
    PipelineEngine merges updates, producing a new PipelineState.
    """

    user_request: str = ""
    request_frame: Any = None
    semantic_request: Any = None
    intent: Any = None
    confidence: Any = None
    target: str = ""
    matched_keywords: tuple[str, ...] = ()
    extracted_params: Any = None
    answer_type: Any = None
    selected_tool: Any = None
    required_evidence: tuple = ()
    optional_evidence: tuple = ()
    capability_references: tuple = ()
    execution_plan: Any = None
    execution_graph: Any = None
    evidence: tuple = ()
    evidence_complete: bool = False
    missing_evidence: tuple[str, ...] = ()
    runtime_metrics: Any = None
    intent_candidates: tuple = ()
    intent_score: float | None = None
    intent_margin: float | None = None
    target_candidates: tuple = ()
    target_score: float | None = None
    target_margin: float | None = None
    routing_status: Any = None
    evidence_status: Any = None
    answer_strategy: Any = None
    llm_usage_reason: Any = None
    fact_set: FactSet = FactSet()
    contradictions: tuple = ()
    evidence_completeness: Any = None

    def apply(self, update: StateUpdate) -> PipelineState:
        """Return a new PipelineState with update applied."""
        return replace(self, **update)

    @classmethod
    def initial(cls, user_request: str) -> PipelineState:
        return cls(user_request=user_request)

    def to_investigation_request(self) -> Any:
        """Convert back to InvestigationRequest for backward compatibility."""
        from src.pipeline.investigation_request import InvestigationRequest

        return InvestigationRequest(
            raw_request=self.user_request,
            intent=self.intent,
            confidence=self.confidence,
            matched_keywords=self.matched_keywords,
            target=self.target or None,
            request_frame=self.request_frame,
            semantic_request=self.request_frame or self.semantic_request,
            intent_candidates=self.intent_candidates,
            intent_score=self.intent_score,
            intent_margin=self.intent_margin,
            target_candidates=self.target_candidates,
            target_score=self.target_score,
            target_margin=self.target_margin,
            routing_status=self.routing_status,
            evidence_status=self.evidence_status,
            answer_strategy=self.answer_strategy,
            llm_usage_reason=self.llm_usage_reason,
            required_evidence=list(self.required_evidence),
            optional_evidence=list(self.optional_evidence),
            capability_references=list(self.capability_references),
            execution_plan=self.execution_plan,
            execution_graph=self.execution_graph,
            evidence=list(self.evidence),
            evidence_complete=self.evidence_complete,
            missing_evidence=self.missing_evidence,
            runtime_metrics=self.runtime_metrics,
            extracted_params=self.extracted_params,
            answer_type=self.answer_type,
            selected_tool=self.selected_tool,
            fact_set=self.fact_set,
            contradictions=self.contradictions,
            evidence_completeness=self.evidence_completeness,
        )
