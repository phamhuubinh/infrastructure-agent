from __future__ import annotations

from src.pipeline.capability_summary_index import (
    CapabilityAvailability,
    CapabilitySourceFamily,
    CapabilitySummaryIndex,
)
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    SemanticPlan,
    SemanticPlanRoute,
)


def _plan(
    route: SemanticPlanRoute,
    sources: tuple[SourceConstraint, ...] = (SourceConstraint.ANY,),
    *,
    compute: DeterministicComputeIntent = DeterministicComputeIntent.NOT_REQUIRED,
) -> SemanticPlan:
    return SemanticPlan(
        route=route,
        source_constraints=sources,
        deterministic_compute=compute,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def test_default_index_distinguishes_required_semantic_families() -> None:
    index = CapabilitySummaryIndex.default()

    assert {item.source_family for item in index.summaries} == {
        CapabilitySourceFamily.NONE,
        CapabilitySourceFamily.LINUX,
        CapabilitySourceFamily.GRAFANA,
        CapabilitySourceFamily.ZABBIX,
        CapabilitySourceFamily.INTERNET,
        CapabilitySourceFamily.COMPUTE,
    }
    assert all(
        set(item.to_prompt_dict())
        == {"id", "purpose", "source", "target", "data", "availability"}
        for item in index.summaries
    )


def test_direct_answer_receives_no_capability_index_payload() -> None:
    payload = CapabilitySummaryIndex.default().payload_for_plan(
        _plan(SemanticPlanRoute.DIRECT_ANSWER)
    )

    assert payload == ()


def test_grafana_only_plan_receives_only_grafana_summary() -> None:
    payload = CapabilitySummaryIndex.default().payload_for_plan(
        _plan(
            SemanticPlanRoute.CAPABILITY_ASSISTED,
            (SourceConstraint.GRAFANA,),
        )
    )

    assert [item["id"] for item in payload] == ["grafana.metrics"]


def test_availability_is_explicit_and_compute_is_opt_in() -> None:
    index = CapabilitySummaryIndex.default(
        availability={
            CapabilitySourceFamily.INTERNET: CapabilityAvailability.UNAVAILABLE
        }
    )
    payload = index.payload_for_plan(
        _plan(
            SemanticPlanRoute.CAPABILITY_ASSISTED,
            compute=DeterministicComputeIntent.REQUIRED,
        )
    )

    by_id = {item["id"]: item for item in payload}
    assert by_id["internet.current"]["availability"] == "unavailable"
    assert "compute.deterministic" in by_id
    assert "none.direct" not in by_id

    grafana_compute = index.payload_for_plan(
        _plan(
            SemanticPlanRoute.CAPABILITY_ASSISTED,
            (SourceConstraint.GRAFANA,),
            compute=DeterministicComputeIntent.REQUIRED,
        )
    )
    assert {item["id"] for item in grafana_compute} == {
        "grafana.metrics",
        "compute.deterministic",
    }
