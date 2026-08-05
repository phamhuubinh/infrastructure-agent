from __future__ import annotations

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.investigation_request import InvestigationRequest
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus


def test_merge_normalizes_runtime_result_into_investigation_fact_set() -> None:
    request = InvestigationRequest(raw_request="cpu", target="server-1")
    request.capability_references = [
        CapabilityReference("CPU Utilization", "CPU Usage")
    ]
    result = ToolResult(
        success=True,
        data={
            "usage_percent": 25.0,
            "idle_percent": 70.0,
            "collection_strategy": "fixture",
        },
        capability_status=CapabilityStatus.VALID,
        produced_fact_names=("cpu.usage",),
        source="server-1",
        source_kind="linux",
        resource="get_cpu_usage",
        schema_version="1",
    )

    EvidenceMerge().merge(request, {"CPU Utilization": result})

    assert request.fact_set.by_metric("cpu.usage")
    assert {fact.id for fact in request.evidence[0].facts} == {
        fact.id for fact in request.fact_set.facts
    }
    assert request.evidence[0].raw_data["usage_percent"] == 25.0
