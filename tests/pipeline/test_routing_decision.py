from __future__ import annotations

from src.pipeline.answer_type import AnswerType
from src.pipeline.execution_trace import AnswerStrategy, ExecutionTrace, LLMUsageReason
from src.pipeline.normalizer import Normalizer
from src.pipeline.routing_decision import EvidenceStatus, RoutingStatus


def test_complete_request_and_response_taxonomy() -> None:
    assert {item.name for item in AnswerType} >= {
        "FACT",
        "LIST",
        "TABLE",
        "CHART",
        "ASSESSMENT",
        "COMPARISON",
        "FORECAST",
        "ACTION",
        "EXPLANATION",
    }
    assert {item.name for item in RoutingStatus} >= {
        "RESOLVED",
        "CLARIFICATION_REQUIRED",
        "FALLBACK",
        "UNSUPPORTED",
    }
    assert {item.name for item in EvidenceStatus} >= {
        "SUFFICIENT",
        "PARTIAL",
        "UNAVAILABLE",
        "STALE",
        "CONTRADICTORY",
    }
    assert AnswerStrategy.DETERMINISTIC_FACT
    assert AnswerStrategy.DETERMINISTIC_TEMPLATE


def test_trace_records_taxonomy_and_actual_frame() -> None:
    frame = Normalizer().normalize("check cpu")
    trace = ExecutionTrace(
        user_request=frame.raw_request,
        answer_strategy=AnswerStrategy.DETERMINISTIC_FACT,
        llm_usage_reason=LLMUsageReason.NONE,
        request_class=frame.answer_type,
        routing_status=RoutingStatus.RESOLVED,
        evidence_status=EvidenceStatus.SUFFICIENT,
        actual_request_frame=frame.to_dict(),
    ).to_dict()

    assert trace["request_class"] == "FACT"
    assert trace["routing_status"] == "RESOLVED"
    assert trace["evidence_status"] == "SUFFICIENT"
    assert trace["actual_request_frame"]["concepts"] == ["cpu"]
    assert trace["llm_usage_reason"] == "NONE"
