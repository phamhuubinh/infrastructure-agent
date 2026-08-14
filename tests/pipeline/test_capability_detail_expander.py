from __future__ import annotations

from src.pipeline.capability_detail_expander import (
    CapabilityExpansionReason,
    CapabilityExpansionStatus,
    LazyCapabilityDetailExpander,
)
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_summary_index import (
    CapabilityAvailability,
    CapabilityDataKind,
    CapabilitySourceFamily,
    CapabilitySummary,
    CapabilitySummaryIndex,
    CapabilityTargetKind,
)
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan import SemanticPlan, SemanticPlanRoute
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
)


def _summary(
    capability_id: str,
    family: CapabilitySourceFamily,
    availability: CapabilityAvailability = CapabilityAvailability.AVAILABLE,
) -> CapabilitySummary:
    return CapabilitySummary(
        capability_id=capability_id,
        purpose=f"Inspect {family.value} CPU",
        source_family=family,
        target_kind=CapabilityTargetKind.MONITORING,
        data_kind=CapabilityDataKind.METRIC,
        availability=availability,
    )


def _validated_plan(source: SourceConstraint) -> SemanticPlanValidationResult:
    return SemanticPlanValidationResult.valid(
        SemanticPlan(
            route=SemanticPlanRoute.CAPABILITY_ASSISTED,
            source_constraints=(source,),
        )
    )


def test_selected_id_expands_to_the_exact_existing_reference_contract() -> None:
    summary = _summary("grafana.cpu", CapabilitySourceFamily.GRAFANA)
    reference = CapabilityReference(
        name="CPU Utilization",
        evidence_name="CPU Usage",
        description="Current CPU metric",
        supported_targets=("grafana",),
        parameters=("target", "time_range"),
    )
    expander = LazyCapabilityDetailExpander(
        CapabilitySummaryIndex((summary,)),
        {"grafana.cpu": reference},
    )

    result = expander.expand("grafana.cpu", _validated_plan(SourceConstraint.GRAFANA))

    assert result.status is CapabilityExpansionStatus.EXPANDED
    assert result.capability is reference
    assert result.capability.parameters == ("target", "time_range")


def test_grafana_only_plan_cannot_expand_linux_detail() -> None:
    summary = _summary("linux.cpu", CapabilitySourceFamily.LINUX)
    reference = CapabilityReference("CPU Information", "CPU")
    expander = LazyCapabilityDetailExpander(
        CapabilitySummaryIndex((summary,)), {"linux.cpu": reference}
    )

    result = expander.expand("linux.cpu", _validated_plan(SourceConstraint.GRAFANA))

    assert result.status is CapabilityExpansionStatus.SOURCE_BLOCKED
    assert result.reason is CapabilityExpansionReason.SOURCE_NOT_ALLOWED
    assert result.capability is None


def test_unavailable_selection_does_not_fallback_to_another_capability() -> None:
    missing = _summary(
        "grafana.cpu",
        CapabilitySourceFamily.GRAFANA,
        CapabilityAvailability.UNAVAILABLE,
    )
    other = _summary("grafana.memory", CapabilitySourceFamily.GRAFANA)
    other_reference = CapabilityReference("Memory Utilization", "Memory Usage")
    expander = LazyCapabilityDetailExpander(
        CapabilitySummaryIndex((missing, other)),
        {"grafana.memory": other_reference},
    )

    result = expander.expand("grafana.cpu", _validated_plan(SourceConstraint.GRAFANA))

    assert result.status is CapabilityExpansionStatus.UNAVAILABLE
    assert result.reason is CapabilityExpansionReason.CAPABILITY_UNAVAILABLE
    assert result.capability is None
    assert result.selected_capability_id == "grafana.cpu"


def test_detail_requires_a_validated_capability_assisted_plan() -> None:
    summary = _summary("grafana.cpu", CapabilitySourceFamily.GRAFANA)
    expander = LazyCapabilityDetailExpander(
        CapabilitySummaryIndex((summary,)),
        {"grafana.cpu": CapabilityReference("CPU Utilization", "CPU Usage")},
    )
    invalid = SemanticPlanValidationResult.clarify(
        SemanticPlan(), SemanticPlanValidationReason.TARGET_MISSING
    )

    result = expander.expand("grafana.cpu", invalid)

    assert result.status is CapabilityExpansionStatus.PLAN_NOT_VALID
    assert result.reason is CapabilityExpansionReason.PLAN_NOT_VALIDATED
    assert result.capability is None
