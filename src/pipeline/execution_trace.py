"""ExecutionTrace schema for pipeline observability.

Every pipeline request produces exactly one execution trace. The trace
records stage-level status, confidence, target, plan, evidence and findings
so that failures can be attributed to a specific stage (``failure_stage``
and ``failure_reason``).

Rules (see docs/project/DETERMINISTIC_REASONING_BACKLOG.md DR1-002):
- a stage that never ran is recorded as ``None``/PENDING, never as
  confidence 0.0 — zero is an actual measurement, not "not executed".
- serialization never contains credentials or raw sensitive command output.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from src.pipeline.investigation_request import InvestigationRequest


class StageStatus(Enum):
    """Execution status of a single pipeline stage."""

    PENDING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    SKIPPED = auto()


class AnswerStrategy(Enum):
    """How the final response was produced."""

    DETERMINISTIC_FACT = auto()
    LLM_ASSESSMENT = auto()
    DETERMINISTIC_RESPONDER = auto()
    DETERMINISTIC_TEMPLATE = auto()
    CLARIFICATION = auto()
    REFUSAL = auto()
    CHAT = auto()


class LLMUsageReason(Enum):
    """Why (or why not) the LLM was invoked for this request.

    - EXPECTED_ASSESSMENT: routing was correct and the answer type genuinely
      required LLM analysis. This is NOT a routing failure.
    - ROUTING_FALLBACK: the pipeline could not resolve concept/intent/target/
      capability/parameter deterministically and fell back to the LLM.
    - INSUFFICIENT_EVIDENCE: the request was understood but tools could not
      collect enough evidence to conclude (LLM explanation of the gap).
    - NONE: no LLM call was made (deterministic fast path).
    """

    EXPECTED_ASSESSMENT = auto()
    ROUTING_FALLBACK = auto()
    INSUFFICIENT_EVIDENCE = auto()
    NONE = auto()


@dataclass(frozen=True, slots=True)
class StageTrace:
    """Observability record for one deterministic pipeline stage.

    ``confidence`` uses ``None`` when the stage did not produce a confidence
    score, never 0.0 — 0.0 is an actual score, not "not executed".

    Attributes:
        name: Pipeline stage name (e.g. "normalize", "target", "plan").
        status: Stage execution status.
        confidence: Resolved confidence for this stage, or None.
        target: Resolved target at this stage, or None.
        extracted_params: Safe copy of extracted parameters, or None.
        planned_capabilities: Capability plan at this stage, or None.
        evidence_names: Evidence package names collected at this stage, or None.
        findings: Deterministic findings produced at this stage, or None.
        message: Human-readable outcome / error message, or None.
        duration_ms: Stage wall-clock duration in milliseconds, or None.
    """

    name: str
    status: StageStatus = StageStatus.PENDING
    confidence: float | str | None = None
    target: str | None = None
    extracted_params: dict[str, str] | None = None
    planned_capabilities: list[str] | None = None
    evidence_names: list[str] | None = None
    findings: list[str] | None = None
    message: str | None = None
    duration_ms: float | None = None
    candidates: list[dict[str, Any]] | None = None
    ambiguity_margin: float | None = None


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    """Single immutable trace for one pipeline request.

    Every pipeline request produces exactly one ExecutionTrace. The trace is
    safe to serialize: it never contains credentials or raw sensitive command
    output.

    Attributes:
        trace_id: Unique id attached to the request/response metadata.
        user_request: The original user request (plain text, not a secret).
        stages: Stage name → StageTrace. A stage that never ran is absent.
        failure_stage: Name of the stage that failed, or None.
        failure_reason: Human-readable failure reason, or None.
        answer_strategy: How the final response was produced.
        llm_usage_reason: Why the LLM was (or was not) used.
        total_duration_ms: Total pipeline wall-clock duration in ms.
        runtime_metrics: Safe summary of runtime metrics, or None.
    """

    trace_id: str = field(default_factory=lambda: str(uuid4()))
    user_request: str = ""
    stages: dict[str, StageTrace] = field(default_factory=dict)
    failure_stage: str | None = None
    failure_reason: str | None = None
    answer_strategy: AnswerStrategy | None = None
    llm_usage_reason: LLMUsageReason = LLMUsageReason.NONE
    total_duration_ms: float | None = None
    runtime_metrics: dict[str, Any] | None = None
    request_class: object | None = None
    routing_status: object | None = None
    evidence_status: object | None = None
    expected_request_frame: dict[str, Any] | None = None
    actual_request_frame: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict.

        Never includes credentials, raw command output, or memory addresses.
        Only safe, bounded values are emitted.
        """
        def _name(value: object) -> object:
            return value.name if isinstance(value, Enum) else value

        return {
            "trace_id": self.trace_id,
            "user_request": self.user_request,
            "stages": {
                name: {
                    "name": stage.name,
                    "status": stage.status.name,
                    "confidence": stage.confidence,
                    "target": stage.target,
                    "extracted_params": stage.extracted_params,
                    "planned_capabilities": stage.planned_capabilities,
                    "evidence_names": stage.evidence_names,
                    "findings": stage.findings,
                    "message": stage.message,
                    "duration_ms": (
                        round(stage.duration_ms, 3)
                        if stage.duration_ms is not None
                        else None
                    ),
                    "candidates": stage.candidates,
                    "ambiguity_margin": stage.ambiguity_margin,
                }
                for name, stage in self.stages.items()
            },
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "answer_strategy": (
                self.answer_strategy.name if self.answer_strategy else None
            ),
            "llm_usage_reason": self.llm_usage_reason.name,
            "request_class": _name(self.request_class),
            "routing_status": _name(self.routing_status),
            "evidence_status": _name(self.evidence_status),
            "expected_request_frame": self.expected_request_frame,
            "actual_request_frame": self.actual_request_frame,
            "total_duration_ms": (
                round(self.total_duration_ms, 3)
                if self.total_duration_ms is not None
                else None
            ),
            "runtime_metrics": self.runtime_metrics,
        }

    # ------------------------------------------------------------------
    # Reconstructors
    # ------------------------------------------------------------------

    @classmethod
    def from_investigation(
        cls,
        request: InvestigationRequest,
        *,
        trace_id: str | None = None,
        answer_strategy: AnswerStrategy | None = None,
        llm_usage_reason: LLMUsageReason | None = None,
        total_duration_ms: float | None = None,
    ) -> ExecutionTrace:
        """Build a trace from an InvestigationRequest.

        The request object is enriched by each pipeline stage, so the trace
        reconstructs stage records from the accumulated fields.
        """

        def _params() -> dict[str, str] | None:
            params = getattr(request, "extracted_params", None)
            if params is None:
                return None
            to_dict = getattr(params, "to_dict", None)
            if callable(to_dict):
                raw: Any = to_dict()
                return {str(k): str(v) for k, v in raw.items()}
            return None

        def _plan() -> list[str] | None:
            plan = request.execution_plan
            if plan is None:
                return None
            return [step.capability.name for step in plan.steps]

        stages: dict[str, StageTrace] = {}

        frame = getattr(request, "request_frame", None)

        def _candidate_dict(candidate: object) -> dict[str, Any]:
            to_dict = getattr(candidate, "to_dict", None)
            if callable(to_dict):
                value = to_dict()
                if isinstance(value, dict):
                    return value
            return {"label": str(candidate)}

        stages["normalize"] = StageTrace(
            name="normalize",
            status=StageStatus.SUCCEEDED,
            confidence=getattr(frame, "confidence", None),
            message="normalized",
            candidates=[
                _candidate_dict(candidate)
                for candidate in getattr(frame, "concept_candidates", ())
            ]
            or None,
        )

        stages["intent"] = StageTrace(
            name="intent",
            status=StageStatus.SUCCEEDED,
            confidence=request.confidence.name if request.confidence else None,
            target=request.target,
            message=request.intent.name if request.intent else None,
            candidates=[
                _candidate_dict(candidate) for candidate in request.intent_candidates
            ]
            or None,
            ambiguity_margin=request.intent_margin,
        )

        stages["target"] = StageTrace(
            name="target",
            status=StageStatus.SUCCEEDED,
            target=request.target,
            message=request.target or "localhost",
            candidates=[
                _candidate_dict(candidate) for candidate in request.target_candidates
            ]
            or None,
            ambiguity_margin=request.target_margin,
        )

        stages["plan"] = StageTrace(
            name="plan",
            status=StageStatus.SUCCEEDED,
            extracted_params=_params(),
            planned_capabilities=_plan(),
            evidence_names=[req.name for req in request.required_evidence],
        )

        stages["execute"] = StageTrace(
            name="execute",
            status=StageStatus.SUCCEEDED,
            evidence_names=[pkg.evidence_name for pkg in request.evidence],
            message=(
                "evidence collected"
                if request.evidence_complete
                else "evidence incomplete"
            ),
        )

        stages["assess"] = StageTrace(
            name="assess",
            status=StageStatus.SUCCEEDED,
            message="assessment prepared",
        )

        metrics = getattr(request, "runtime_metrics", None)
        runtime_metrics: dict[str, Any] | None = None
        if metrics is not None:
            runtime_metrics = {
                "execution_duration": getattr(metrics, "execution_duration", None),
                "total_nodes": getattr(metrics, "total_nodes", None),
                "successful_nodes": getattr(metrics, "successful_nodes", None),
                "failed_nodes": getattr(metrics, "failed_nodes", None),
                "parallel_ratio": getattr(metrics, "parallel_ratio", None),
                "tool_calls": getattr(metrics, "tool_calls", None),
                "evidence_complete": getattr(metrics, "evidence_complete", None),
                "timed_out": getattr(metrics, "timed_out", None),
                "early_completed": getattr(metrics, "early_completed", None),
                "security_inspections_total": getattr(
                    metrics, "security_inspections_total", None
                ),
                "security_inspections_passed": getattr(
                    metrics, "security_inspections_passed", None
                ),
                "security_inspections_blocked": getattr(
                    metrics, "security_inspections_blocked", None
                ),
            }

        expected = getattr(request, "expected_request_frame", None)
        return cls(
            trace_id=trace_id or str(uuid4()),
            user_request=request.raw_request,
            stages=stages,
            answer_strategy=answer_strategy,
            llm_usage_reason=llm_usage_reason or LLMUsageReason.NONE,
            total_duration_ms=total_duration_ms,
            runtime_metrics=runtime_metrics,
            request_class=getattr(request, "answer_type", None),
            routing_status=getattr(request, "routing_status", None),
            evidence_status=getattr(request, "evidence_status", None),
            expected_request_frame=(
                expected.to_dict() if expected is not None else None
            ),
            actual_request_frame=(
                frame.to_dict() if frame is not None else None
            ),
        )


def now_ms() -> float:
    """Return monotonic wall-clock time in milliseconds."""
    return time.perf_counter() * 1000.0
