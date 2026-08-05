from __future__ import annotations

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.normalizer import Normalizer
from src.pipeline.request_decomposer import RequestDecomposer


def test_decomposes_coordinated_concepts_with_shared_semantics() -> None:
    frame = Normalizer().normalize("Kiểm tra CPU, RAM và Disk trên server01")

    result = RequestDecomposer().decompose(frame)

    assert [subframe.concept for subframe in result.subframes] == [
        "cpu",
        "memory",
        "disk",
    ]
    assert {subframe.target_raw for subframe in result.subframes} == {"server01"}
    assert {subframe.timeframe for subframe in result.subframes} == {None}


def test_too_many_subrequests_requires_scope() -> None:
    frame = Normalizer().normalize("CPU RAM disk network firewall")

    result = RequestDecomposer(max_subrequests=4).decompose(frame)

    assert result.too_broad is True
    assert result.subframes == ()


def test_execution_plan_deduplicates_merged_capabilities() -> None:
    request = InvestigationRequest(raw_request="CPU and load")
    request.capability_references = [
        CapabilityReference("CPU Information", "CPU"),
        CapabilityReference("CPU Information", "CPU Hardware"),
    ]

    ExecutionPlanner().plan(request)

    assert request.execution_plan is not None
    assert len(request.execution_plan.steps) == 1
