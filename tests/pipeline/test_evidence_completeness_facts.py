from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.evidence_completeness import (
    EvidenceCompleteness,
    RequirementStatus,
)
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.provenance import Provenance

NOW = datetime.now(timezone.utc)


def _fact(
    metric: str,
    *,
    validity: FactValidity = FactValidity.VALID,
    target: str = "server-1",
    value: object = 42,
    dimensions: dict[str, object] | None = None,
) -> Fact:
    return Fact(
        "system",
        metric,
        value if validity is FactValidity.VALID else None,
        "percent",
        NOW,
        NOW,
        "linux",
        target,
        validity,
        FactFreshness.FRESH,
        1.0,
        Provenance("linux", "collector", target, NOW),
        dimensions=dimensions or {},
    )


def test_complete_requires_matching_metric_and_target() -> None:
    request = InvestigationRequest(
        raw_request="cpu",
        target="server-1",
        required_evidence=[EvidenceRequirement("CPU", metric="cpu.usage")],
        fact_set=FactSet((_fact("cpu.usage", target="server-2"),)),
    )

    result = EvidenceCompleteness().check(request)

    assert result.complete is False
    assert result.evaluations[0].status is RequirementStatus.MISSING
    assert request.missing_evidence == ("CPU",)


def test_service_inventory_cannot_satisfy_specific_service_status() -> None:
    request = InvestigationRequest(
        raw_request="nginx status",
        target="server-1",
        required_evidence=[
            EvidenceRequirement(
                "Service Status",
                metric="service.status",
                parameter_scope={"service_name": "nginx"},
            )
        ],
        fact_set=FactSet(
            (
                _fact(
                    "service.inventory",
                    value=("nginx",),
                    dimensions={"service_name": "nginx"},
                ),
            )
        ),
    )

    result = EvidenceCompleteness().check(request)

    assert result.complete is False
    assert result.evaluations[0].metric == "service.status"


def test_failed_stale_and_contradictory_are_explained() -> None:
    for validity, expected in (
        (FactValidity.COMMAND_FAILED, RequirementStatus.FAILED),
        (FactValidity.STALE, RequirementStatus.STALE),
        (FactValidity.CONTRADICTORY, RequirementStatus.CONTRADICTORY),
    ):
        request = InvestigationRequest(
            raw_request="cpu",
            target="server-1",
            required_evidence=[EvidenceRequirement("CPU", metric="cpu.usage")],
            fact_set=FactSet((_fact("cpu.usage", validity=validity),)),
        )

        result = EvidenceCompleteness().check(request)

        assert result.evaluations[0].status is expected
        assert result.evaluations[0].explanation


def test_stale_fact_only_satisfies_explicit_opt_in() -> None:
    request = InvestigationRequest(
        raw_request="historical cpu is acceptable",
        target="server-1",
        required_evidence=[
            EvidenceRequirement("CPU", metric="cpu.usage", allow_stale=True)
        ],
        fact_set=FactSet((_fact("cpu.usage", validity=FactValidity.STALE),)),
    )

    result = EvidenceCompleteness().check(request)

    assert result.complete is True
    assert result.evaluations[0].status is RequirementStatus.SATISFIED
