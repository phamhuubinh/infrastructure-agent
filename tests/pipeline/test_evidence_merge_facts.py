from __future__ import annotations

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.investigation_request import InvestigationRequest
from src.shared.execution.command_result import CommandResult, CommandStatus
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


def test_feature_flags_can_hide_new_evidence_layers_without_schema_change() -> None:
    request = InvestigationRequest(raw_request="cpu", target="server-1")
    request.capability_references = [
        CapabilityReference("CPU Utilization", "CPU Usage")
    ]
    command = CommandResult(status=CommandStatus.SUCCESS, stdout="25")
    result = ToolResult(
        success=True,
        data={"usage_percent": 25.0, "collection_strategy": "fixture"},
        capability_status=CapabilityStatus.VALID,
        command_results=(command,),
        source="server-1",
        source_kind="linux",
        resource="get_cpu_usage",
    )

    EvidenceMerge(
        canonical_facts=False,
        structured_command_result=False,
    ).merge(request, {"CPU Utilization": result})

    package = request.evidence[0]
    assert package.data == {"usage_percent": 25.0, "collection_strategy": "fixture"}
    assert package.status is CapabilityStatus.VALID
    assert package.facts == ()
    assert package.command_results == ()
    assert set(package.to_dict()) == {
        "capability_name",
        "evidence_name",
        "success",
        "error",
        "source_tool",
        "source",
        "resource",
        "capability_status",
        "warnings",
        "collection_failures",
        "schema_version",
        "stale",
        "recovery_attempts",
        "recovered_by",
        "facts",
        "source_links",
    }
