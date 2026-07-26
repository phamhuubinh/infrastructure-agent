from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

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
        )
