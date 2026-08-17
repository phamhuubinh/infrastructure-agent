"""Deterministic fake model adapters for agent-loop tests (#51).

No network, tokenizer, or real model is involved. Scripts drive typed
semantic plans and response drafts, inject malformed planner outputs and
provider failures, and expose call counts, purposes, input shapes, and
normalized usage metadata for assertions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.semantic_planner_adapter import (
    PlannerProviderRequest,
    PlannerProviderResponse,
)
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_frame import RequestFrame
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
    TargetReference,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_wire import semantic_plan_to_wire

ALIGNED = '{"decision":"aligned","reason":"aligned"}'
NOT_ALIGNED_CROSS_TASK = '{"decision":"not_aligned","reason":"cross_task"}'


@dataclass(frozen=True, slots=True)
class ScriptedModelCall:
    """One recorded fake-model call: purpose plus prompt and usage shape."""

    kind: str
    prompt: str
    usage: ModelCallUsage | None


@dataclass
class ScriptedAssessmentModel(AssessmentModelAdapter):
    """Scripted drafts, verifier verdicts, and repair results with usage."""

    draft: str = "Hello."
    verifier_responses: list[str] = field(default_factory=lambda: [ALIGNED])
    repair_response: str | None = None
    repair_error: Exception | None = None
    assess_error: Exception | None = None
    usages: dict[str, ModelCallUsage] = field(default_factory=dict)
    calls: list[ScriptedModelCall] = field(default_factory=list)
    _last_usage: ModelCallUsage | None = None

    @property
    def last_usage(self) -> ModelCallUsage | None:
        return self._last_usage

    def _record(self, kind: str, prompt: str) -> None:
        self._last_usage = self.usages.get(kind)
        self.calls.append(ScriptedModelCall(kind, prompt, self._last_usage))

    def assess(self, request) -> str:
        if self.assess_error is not None:
            raise self.assess_error
        self._record("response", str(getattr(request, "raw_request", "")))
        return self.draft

    def assess_raw(self, prompt: str) -> str:
        if "compact final-answer relevance verifier" in prompt:
            self._record("verifier", prompt)
            if len(self.verifier_responses) > 1:
                return self.verifier_responses.pop(0)
            return self.verifier_responses[0]
        if "final-response repairer" in prompt:
            if self.repair_error is not None:
                self._record("repair", prompt)
                raise self.repair_error
            self._record("repair", prompt)
            return self.repair_response if self.repair_response is not None else self.draft
        self._record("response", prompt)
        return self.draft


@dataclass
class ScriptedPlannerProvider:
    """Queued planner responses; raises scripted errors or runs dry."""

    responses: list[PlannerProviderResponse | Exception]
    requests: list[PlannerProviderRequest] = field(default_factory=list)

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        self.requests.append(request)
        if not self.responses:
            raise RuntimeError("planner script exhausted")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def plan_response(
    plan: SemanticPlan | dict | None,
    *,
    provider: str = "test",
    model: str = "semantic-test",
    raw_usage: dict | None = None,
) -> PlannerProviderResponse:
    """Build a valid PlannerProviderResponse from a plan or raw payload."""

    payload: object
    if isinstance(plan, SemanticPlan):
        payload = semantic_plan_to_wire(plan)
    else:
        payload = plan if plan is not None else {}
    return PlannerProviderResponse(
        payload=payload,
        provider=provider,
        model=model,
        raw_usage=raw_usage,
    )


class RecordingEngine:
    """Engine double recording dispatched frames with optional failure."""

    def __init__(self, environment, *, fail: Exception | None = None) -> None:
        self.knowledge_tool = environment.knowledge_tool
        self.target_resolver = environment.target_resolver
        self.execution_budget_config = None
        self.fail = fail
        self.frames: list[RequestFrame] = []
        self.execute_calls = 0

    def execute(self, frame: RequestFrame) -> InvestigationRequest:
        self.execute_calls += 1
        self.frames.append(frame)
        if self.fail is not None:
            raise self.fail
        return InvestigationRequest(
            raw_request=frame.raw_request,
            target=frame.target_resolved,
            request_frame=frame,
            runtime_metrics=RuntimeMetrics(tool_calls=1),
            evidence_complete=True,
        )


def direct_answer_plan(
    *,
    concept: str = "general answer",
    domain: RequestDomain = RequestDomain.GENERAL,
    freshness: FreshnessRequirement = FreshnessRequirement.STABLE,
    calculation=None,
) -> SemanticPlan:
    """Build a DIRECT_ANSWER semantic plan."""

    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=domain,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=freshness,
        concept=concept,
        deterministic_compute=(
            DeterministicComputeIntent.REQUIRED
            if calculation is not None
            else DeterministicComputeIntent.NOT_REQUIRED
        ),
        calculation=calculation,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def capability_plan(
    *,
    concept: str,
    target: str | None = None,
    domain: RequestDomain = RequestDomain.ENVIRONMENT,
    sources: tuple[SourceConstraint, ...] = (SourceConstraint.ANY,),
    excluded_sources: tuple[SourceConstraint, ...] = (),
    freshness: FreshnessRequirement = FreshnessRequirement.STABLE,
    explicit_url: str | None = None,
    execution_intent: ExecutionIntent = ExecutionIntent.INSPECT_READ_ONLY,
    target_kind: TargetReferenceKind | None = None,
) -> SemanticPlan:
    """Build a CAPABILITY_ASSISTED semantic plan.

    A plan without an explicit target value uses an UNSPECIFIED reference
    (implicit localhost for environment plans, no target for external
    information plans); pass ``target_kind`` to override.
    """

    return SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=domain,
        execution_intent=execution_intent,
        target=TargetReference(
            target_kind
            or (
                TargetReferenceKind.EXPLICIT
                if target is not None
                else TargetReferenceKind.UNSPECIFIED
            ),
            target,
        ),
        source_constraints=sources,
        excluded_sources=excluded_sources,
        freshness=freshness,
        concept=concept,
        explicit_url=explicit_url,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


__all__ = [
    "ALIGNED",
    "NOT_ALIGNED_CROSS_TASK",
    "RecordingEngine",
    "ScriptedAssessmentModel",
    "ScriptedModelCall",
    "ScriptedPlannerProvider",
    "capability_plan",
    "direct_answer_plan",
    "plan_response",
]
