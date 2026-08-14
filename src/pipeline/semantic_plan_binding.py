"""Bind validated semantic plans to existing deterministic contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from src.pipeline.capability_planner import CapabilityPlanner
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.parameter_binder import (
    MissingParameterError,
    ParameterBinder,
    ParameterBindingError,
)
from src.pipeline.parameter_extractor import ExtractedParams
from src.pipeline.request_frame import RequestFrame
from src.pipeline.request_semantics import RequestDomain
from src.pipeline.semantic_plan import (
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_harness import SemanticPlanHarnessResult
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
    SemanticPlanValidationStatus,
    SemanticPlanValidationValue,
)
from src.pipeline.time_range_resolver import TimeRange
from src.tool.knowledge_tool import KnowledgeTool


@dataclass(frozen=True, slots=True)
class BoundSemanticCapability:
    reference: CapabilityReference
    source: str
    resource: str
    arguments: MappingProxyType

    def __post_init__(self) -> None:
        if not isinstance(self.arguments, MappingProxyType):
            object.__setattr__(
                self,
                "arguments",
                MappingProxyType(dict(self.arguments)),
            )

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "capability": self.reference.name,
            "evidence": self.reference.evidence_name,
            "source": self.source,
            "resource": self.resource,
            "parameters": sorted(
                key for key in self.arguments if key not in {"source", "resource"}
            ),
        }


@dataclass(frozen=True, slots=True)
class SemanticPlanBindingResult:
    validation: SemanticPlanValidationResult
    request: InvestigationRequest | None = None
    capabilities: tuple[BoundSemanticCapability, ...] = ()
    freshness: FreshnessRequirement = FreshnessRequirement.UNSPECIFIED
    timeframe: TimeRange | None = None

    @property
    def bound(self) -> bool:
        return (
            self.validation.status is SemanticPlanValidationStatus.VALID
            and self.request is not None
            and bool(self.capabilities)
        )

    def to_trace_dict(self) -> dict[str, object]:
        trace = self.validation.to_trace_dict()
        trace["bound"] = self.bound
        trace["target"] = self.request.target if self.request is not None else None
        trace["freshness"] = self.freshness.value
        trace["capabilities"] = [item.to_trace_dict() for item in self.capabilities]
        return trace


class SemanticPlanBinder:
    """Bridge typed semantics to reviewed evidence/capability metadata only."""

    def __init__(self, knowledge_tool: KnowledgeTool) -> None:
        if not isinstance(knowledge_tool, KnowledgeTool):
            raise TypeError("knowledge_tool must be a KnowledgeTool.")
        self._knowledge_tool = knowledge_tool
        self._evidence_planner = EvidencePlanner()
        self._capability_planner = CapabilityPlanner()
        self._capability_resolver = CapabilityResolver()
        self._parameter_binder = ParameterBinder()
        self._router = CapabilityRouter()
        self._router.build_routes(knowledge_tool)

    def bind(
        self,
        harness: SemanticPlanHarnessResult,
        *,
        raw_request: str,
        timeframe: TimeRange | None = None,
    ) -> SemanticPlanBindingResult:
        if not isinstance(harness, SemanticPlanHarnessResult):
            raise TypeError("harness must be a SemanticPlanHarnessResult.")
        plan = harness.validation.validated_plan
        if (
            harness.validation.status is not SemanticPlanValidationStatus.VALID
            or plan is None
        ):
            return SemanticPlanBindingResult(validation=harness.validation)
        if plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED:
            return SemanticPlanBindingResult(
                validation=SemanticPlanValidationResult.reject(
                    SemanticPlanValidationReason.CAPABILITY_UNKNOWN,
                    plan=plan,
                ),
                freshness=plan.freshness,
                timeframe=timeframe,
            )

        request_or_error = self._build_request(
            plan,
            raw_request=raw_request,
            target=harness.resolved_target,
            timeframe=timeframe,
        )
        if isinstance(request_or_error, SemanticPlanValidationResult):
            return SemanticPlanBindingResult(
                validation=request_or_error,
                freshness=plan.freshness,
                timeframe=timeframe,
            )
        request = request_or_error

        bound: list[BoundSemanticCapability] = []
        for reference in request.capability_references:
            routed = self._router.resolve_with_metadata(
                reference.name,
                request.extracted_params,
                allowed_sources=harness.allowed_sources,
            )
            if routed is None:
                if reference.required:
                    return _binding_failure(
                        plan,
                        SemanticPlanValidationReason.CAPABILITY_UNAVAILABLE,
                        "capability",
                        reference.name,
                        request=request,
                        timeframe=timeframe,
                    )
                continue
            (source, resource), metadata = routed
            if source == "localhost" and request.target not in {None, "localhost"}:
                source = request.target
            if (
                harness.allowed_sources is not None
                and source not in harness.allowed_sources
            ):
                return _binding_failure(
                    plan,
                    SemanticPlanValidationReason.CAPABILITY_SOURCE_MISMATCH,
                    "source",
                    source,
                    request=request,
                    timeframe=timeframe,
                )
            try:
                parameters = self._parameter_binder.bind(
                    source=source,
                    resource=resource,
                    metadata=metadata,
                    extracted_params=request.extracted_params,
                    timeframe=timeframe,
                )
            except MissingParameterError as exc:
                return _binding_failure(
                    plan,
                    SemanticPlanValidationReason.PARAMETER_MISSING,
                    "parameter",
                    exc.parameter,
                    request=request,
                    timeframe=timeframe,
                    clarify=True,
                )
            except ParameterBindingError as exc:
                return _binding_failure(
                    plan,
                    SemanticPlanValidationReason.PARAMETER_INVALID,
                    "parameter",
                    exc.parameter,
                    request=request,
                    timeframe=timeframe,
                )
            request.bound_params[reference.name] = dict(parameters.arguments)
            bound.append(
                BoundSemanticCapability(
                    reference=reference,
                    source=source,
                    resource=resource,
                    arguments=MappingProxyType(dict(parameters.arguments)),
                )
            )

        if not bound:
            return _binding_failure(
                plan,
                SemanticPlanValidationReason.CAPABILITY_UNAVAILABLE,
                "capability",
                None,
                request=request,
                timeframe=timeframe,
            )
        ExecutionPlanner().plan(request)
        return SemanticPlanBindingResult(
            validation=harness.validation,
            request=request,
            capabilities=tuple(bound),
            freshness=plan.freshness,
            timeframe=timeframe,
        )

    def _build_request(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        target: str | None,
        timeframe: TimeRange | None,
    ) -> InvestigationRequest | SemanticPlanValidationResult:
        if plan.domain is RequestDomain.EXTERNAL_INFORMATION:
            return self._external_request(
                plan,
                raw_request=raw_request,
                target=target,
                timeframe=timeframe,
            )

        intent = _intent_for_plan(plan)
        if intent is None:
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.CAPABILITY_UNKNOWN,
                plan=plan,
            )
        if intent is Intent.SERVICE_ASSESSMENT and not plan.service:
            return SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.PARAMETER_MISSING,
                values=(
                    SemanticPlanValidationValue.safe(
                        "parameter.service",
                        original=None,
                        normalized=None,
                    ),
                ),
            )
        params = ExtractedParams(service_name=plan.service, path=plan.path)
        frame = _request_frame(
            plan,
            raw_request=raw_request,
            target=target,
            params=params,
            timeframe=timeframe,
        )
        request = InvestigationRequest(
            raw_request=raw_request,
            intent=intent,
            target=target,
            request_frame=frame,
            extracted_params=params,
        )
        self._evidence_planner.plan(request)
        self._capability_resolver.resolve(request)
        selected = _primary_evidence_name(plan)
        primary_refs = [
            item
            for item in request.capability_references
            if item.evidence_name == selected
        ]
        if primary_refs:
            request.capability_references = [
                CapabilityReference(
                    name=item.name,
                    evidence_name=item.evidence_name,
                    required=True,
                    description=item.description,
                    supported_targets=item.supported_targets,
                    parameters=item.parameters,
                    estimated_cost=item.estimated_cost,
                )
                for item in primary_refs
            ]
            return request
        configured = set(self._capability_planner.plan(frame))
        configured_refs = [
            item
            for item in request.capability_references
            if item.evidence_name in configured
        ]
        if configured_refs:
            request.capability_references = configured_refs
        return request

    def _external_request(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        target: str | None,
        timeframe: TimeRange | None,
    ) -> InvestigationRequest:
        name = "URL Fetch" if plan.explicit_url else "Internet Resource Access"
        evidence_name = (
            "External URL" if plan.explicit_url else "Current External Information"
        )
        params: dict[str, object] = {
            "query": raw_request,
            "url": plan.explicit_url,
        }
        frame = _request_frame(
            plan,
            raw_request=raw_request,
            target=target,
            params=params,
            timeframe=timeframe,
        )
        request = InvestigationRequest(
            raw_request=raw_request,
            target=target,
            request_frame=frame,
            extracted_params=params,
        )
        request.capability_references = [
            CapabilityReference(name=name, evidence_name=evidence_name, required=True)
        ]
        return request


def _request_frame(
    plan: SemanticPlan,
    *,
    raw_request: str,
    target: str | None,
    params: object,
    timeframe: TimeRange | None,
) -> RequestFrame:
    return RequestFrame(
        raw_request=raw_request,
        concepts=((plan.concept,) if plan.concept else ()),
        operation="inspect",
        target_raw=plan.target.value,
        target_resolved=target,
        parameters=params,
        timeframe=timeframe,
        request_domain=plan.domain,
        source_constraints=plan.source_constraints,
        excluded_sources=plan.excluded_sources,
        explicit_url=plan.explicit_url,
        execution_intent=plan.execution_intent,
    )


def _intent_for_plan(plan: SemanticPlan) -> Intent | None:
    concept = (plan.concept or plan.metric or "").casefold()
    mappings: tuple[tuple[tuple[str, ...], Intent], ...] = (
        (("cpu",), Intent.CPU_ASSESSMENT),
        (("memory", "ram", "swap"), Intent.MEMORY_ASSESSMENT),
        (("disk", "storage"), Intent.DISK_ASSESSMENT),
        (("filesystem", "mount"), Intent.FILESYSTEM_ASSESSMENT),
        (("service",), Intent.SERVICE_ASSESSMENT),
        (("process",), Intent.PROCESS_ASSESSMENT),
        (("network", "latency"), Intent.NETWORK_ASSESSMENT_SINGLE),
        (("grafana", "zabbix", "monitoring", "alert"), Intent.MONITORING_ASSESSMENT),
        (
            ("security", "firewall", "ssh", "selinux", "apparmor"),
            Intent.SECURITY_ASSESSMENT,
        ),
        (
            ("machine", "system", "hostname", "kernel", "uptime"),
            Intent.MACHINE_ASSESSMENT,
        ),
    )
    for markers, intent in mappings:
        if any(marker in concept for marker in markers):
            return intent
    return None


def _primary_evidence_name(plan: SemanticPlan) -> str:
    concept = (plan.metric or plan.concept or "").casefold()
    mappings = (
        (("cpu.usage", "cpu utilization"), "CPU Usage"),
        (("cpu",), "CPU Hardware"),
        (("memory", "ram"), "Memory"),
        (("service",), "Service Status"),
        (("process",), "Processes"),
        (("filesystem", "mount"), "Filesystem"),
        (("disk", "storage"), "Storage"),
        (("network",), "Network"),
        (("alert", "monitoring", "grafana", "zabbix"), "Active Problems"),
    )
    for markers, evidence_name in mappings:
        if any(marker in concept for marker in markers):
            return evidence_name
    return ""


def _binding_failure(
    plan: SemanticPlan,
    reason: SemanticPlanValidationReason,
    field: str,
    value: str | None,
    *,
    request: InvestigationRequest,
    timeframe: TimeRange | None,
    clarify: bool = False,
) -> SemanticPlanBindingResult:
    values = (
        SemanticPlanValidationValue.safe(
            field,
            original=value,
            normalized=None,
        ),
    )
    validation = (
        SemanticPlanValidationResult.clarify(plan, reason, values=values)
        if clarify
        else SemanticPlanValidationResult.unavailable(plan, reason, values=values)
        if reason
        in {
            SemanticPlanValidationReason.CAPABILITY_UNAVAILABLE,
            SemanticPlanValidationReason.CAPABILITY_SOURCE_MISMATCH,
        }
        else SemanticPlanValidationResult.reject(
            plan=plan, reason=reason, values=values
        )
    )
    return SemanticPlanBindingResult(
        validation=validation,
        request=request,
        freshness=plan.freshness,
        timeframe=timeframe,
    )


__all__ = [
    "BoundSemanticCapability",
    "SemanticPlanBinder",
    "SemanticPlanBindingResult",
]
