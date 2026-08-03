from __future__ import annotations

import json

from src.pipeline.answer_type import AnswerType
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.execution_plan import ExecutionPlan, ExecutionStep
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.execution_trace import (
    AnswerStrategy,
    ExecutionTrace,
    LLMUsageReason,
    StageStatus,
    StageTrace,
)
from src.pipeline.intent_resolver import Confidence, Intent
from src.pipeline.investigation_request import InvestigationRequest


def _make_investigation(
    *,
    complete: bool = True,
    evidence: list[EvidencePackage] | None = None,
) -> InvestigationRequest:
    """Build an InvestigationRequest with representative pipeline data."""
    pkg = evidence or [
        EvidencePackage(
            capability_name="CPU Information",
            evidence_name="CPU Information",
            data=[{"idle_pct": 5}],
            success=True,
        )
    ]
    req = InvestigationRequest(
        raw_request="check cpu",
        intent=Intent.CPU_ASSESSMENT,
        confidence=Confidence.HIGH,
        matched_keywords=("cpu",),
        target="localhost",
        semantic_request=None,
        required_evidence=[],
        optional_evidence=[],
        capability_references=[],
        execution_plan=None,
        execution_graph=None,
        evidence=pkg,
        evidence_complete=complete,
        missing_evidence=("CPU Information",) if not complete else (),
        extracted_params=None,
        answer_type=AnswerType.FACT,
        selected_tool=None,
        runtime_metrics=RuntimeMetrics(
            execution_duration=0.5,
            total_nodes=1,
            successful_nodes=1,
            failed_nodes=0,
            parallel_ratio=0.0,
            tool_calls=1,
            evidence_complete=complete,
        ),
    )
    return req


def test_trace_from_investigation_produces_single_trace() -> None:
    """Every pipeline request produces exactly one ExecutionTrace."""
    req = _make_investigation()
    trace = ExecutionTrace.from_investigation(req)
    # A unique trace id is always generated.
    assert trace.trace_id
    assert trace.user_request == "check cpu"
    assert len(trace.stages) >= 5  # normalize/intent/target/plan/execute/assess


def test_trace_ids_are_unique_per_request() -> None:
    """Two investigations produce two distinct traces."""
    req1 = _make_investigation()
    req2 = _make_investigation(complete=False)
    t1 = ExecutionTrace.from_investigation(req1)
    t2 = ExecutionTrace.from_investigation(req2)
    assert t1.trace_id != t2.trace_id


def test_trace_stage_confidence_uses_none_for_not_executed() -> None:
    """A stage that never produced a confidence score is None, never 0.0."""
    req = _make_investigation()
    trace = ExecutionTrace.from_investigation(req)
    normalize = trace.stages["normalize"]
    assert normalize.confidence is None
    # Serialization keeps None, not converting to 0.0.
    dumped = trace.to_dict()
    stage = dumped["stages"]["normalize"]
    assert stage["confidence"] is None


def test_trace_failure_stage_and_reason() -> None:
    """The trace can carry failure_stage and failure_reason."""
    trace = ExecutionTrace(
        user_request="check cpu",
        failure_stage="target",
        failure_reason="UnknownTargetError: serverabcxyz",
        llm_usage_reason=LLMUsageReason.NONE,
    )
    assert trace.failure_stage == "target"
    assert trace.failure_reason is not None and "serverabcxyz" in trace.failure_reason
    dumped = trace.to_dict()
    assert dumped["failure_stage"] == "target"
    assert dumped["failure_reason"] == "UnknownTargetError: serverabcxyz"


def test_trace_serialization_is_json_safe_and_credential_free() -> None:
    """Serialization never includes credentials or raw command output."""
    req = _make_investigation()
    trace = ExecutionTrace.from_investigation(req)
    dumped = trace.to_dict()
    # Must be JSON-serializable.
    json.dumps(dumped)
    assert dumped["llm_usage_reason"] == LLMUsageReason.NONE.name
    assert dumped["answer_strategy"] is None
    # Stage records are bounded and safe.
    assert "token" not in json.dumps(dumped)
    assert "password" not in json.dumps(dumped)
    assert "api_key" not in json.dumps(dumped)


def test_trace_serialization_never_contains_raw_sensitive_fields() -> None:
    """Evidence data is referenced by name only, raw data is not embedded."""
    req = _make_investigation()
    trace = ExecutionTrace.from_investigation(req)
    dumped = trace.to_dict()
    for stage in dumped["stages"].values():
        assert "evidence" not in stage or stage["evidence"] is None
        assert "data" not in stage
    # Evidence names appear (safe), raw dict data does not.
    raw = json.dumps(dumped)
    assert "CPU Information" in raw


def test_trace_from_investigation_records_strategy_and_llm_reason() -> None:
    """AnswerStrategy and LLMUsageReason propagate into the trace."""
    req = _make_investigation(complete=False)
    trace = ExecutionTrace.from_investigation(
        req,
        answer_strategy=AnswerStrategy.LLM_ASSESSMENT,
        llm_usage_reason=LLMUsageReason.INSUFFICIENT_EVIDENCE,
    )
    dumped = trace.to_dict()
    assert dumped["answer_strategy"] == "LLM_ASSESSMENT"
    assert dumped["llm_usage_reason"] == "INSUFFICIENT_EVIDENCE"


def test_trace_from_investigation_records_runtime_metrics() -> None:
    """Runtime metrics summary is captured in the trace."""
    req = _make_investigation()
    trace = ExecutionTrace.from_investigation(req)
    assert trace.runtime_metrics is not None
    assert trace.runtime_metrics["tool_calls"] == 1
    assert trace.runtime_metrics["total_nodes"] == 1
    dumped = trace.to_dict()
    assert dumped["runtime_metrics"]["tool_calls"] == 1


def test_stage_trace_default_status_is_pending() -> None:
    """A freshly created StageTrace defaults to PENDING, not fake success."""
    stage = StageTrace(name="findings")
    assert stage.status == StageStatus.PENDING
    assert stage.confidence is None


def test_trace_reads_execution_plan_capabilities() -> None:
    """Planned capabilities are captured from the execution plan."""
    plan = ExecutionPlan(
        steps=(
            ExecutionStep(
                capability=CapabilityReference(
                    name="cpu", evidence_name="CPU Information"
                ),
            ),
        )
    )
    req = _make_investigation()
    req.execution_plan = plan
    trace = ExecutionTrace.from_investigation(req)
    assert trace.stages["plan"].planned_capabilities == ["cpu"]
