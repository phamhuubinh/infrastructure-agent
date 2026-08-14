from __future__ import annotations

from src.agent.semantic_session_context_selector import (
    SemanticSessionContextSelector,
    SessionContextSelectionStatus,
)
from src.agent.session_investigation_context import (
    EvidenceReceipt,
    SessionInvestigationContext,
)
from src.model.protocol.semantic_planner_prompt import build_semantic_planner_prompt
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.time_range_resolver import TemporalRequirement, TimeRange


def _context() -> SessionInvestigationContext:
    return SessionInvestigationContext(
        active_target="monitor",
        active_concept="cpu",
        active_service="nginx",
        active_path="/var/log/nginx",
        active_time_range=TimeRange(
            start=1,
            end=2,
            granularity="hour",
            timezone="UTC",
            source_phrase="1 giờ",
            requirement=TemporalRequirement.HISTORICAL,
        ),
        active_sources=(SourceConstraint.GRAFANA,),
        active_excluded_sources=(SourceConstraint.INTERNET,),
        requested_answer_shape="RAW",
        previous_evidence_receipts=(
            EvidenceReceipt(
                source="grafana",
                target="monitor",
                capability="secret-detail",
                fact_ids=("fact-1",),
                status="success",
                timestamp="now",
            ),
        ),
        last_evidence_status="success",
    )


def test_follow_up_inherits_only_minimal_valid_semantics() -> None:
    selection = SemanticSessionContextSelector().select("Còn RAM thì sao?", _context())

    assert selection.status is SessionContextSelectionStatus.INHERIT
    assert selection.context is not None
    assert selection.context.target == "monitor"
    assert selection.context.concept is None
    assert selection.context.service is None
    assert selection.context.path is None
    assert selection.context.time_range == "1 giờ"
    assert selection.context.sources == (SourceConstraint.GRAFANA,)
    prompt = build_semantic_planner_prompt(
        "Còn RAM thì sao?", context=selection.context
    )
    assert "fact-1" not in prompt.user_prompt
    assert "secret-detail" not in prompt.user_prompt
    assert "RAW" not in prompt.user_prompt


def test_gratitude_and_unrelated_new_request_clear_stale_context() -> None:
    selector = SemanticSessionContextSelector()

    gratitude = selector.select("Cảm ơn bạn nhé", _context())
    unrelated = selector.select("Thời tiết Hà Nội hôm nay thế nào?", _context())

    assert gratitude.status is SessionContextSelectionStatus.CLEAR
    assert gratitude.context is None
    assert unrelated.status is SessionContextSelectionStatus.CLEAR
    assert unrelated.context is None


def test_short_target_clarification_answer_does_not_reuse_old_target() -> None:
    context = _context().with_pending_clarification("target")

    selection = SemanticSessionContextSelector().select("database", context)

    assert selection.status is SessionContextSelectionStatus.INHERIT
    assert selection.context is not None
    assert selection.context.target is None
    assert selection.context.sources == (SourceConstraint.GRAFANA,)
    assert selection.context.pending_clarification_field == "target"


def test_empty_session_produces_no_planner_context() -> None:
    selection = SemanticSessionContextSelector().select(
        "Còn RAM?", SessionInvestigationContext()
    )

    assert selection.status is SessionContextSelectionStatus.EMPTY
    assert selection.context is None
