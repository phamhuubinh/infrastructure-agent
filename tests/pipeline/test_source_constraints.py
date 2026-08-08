from __future__ import annotations

from types import MappingProxyType

import pytest

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.execution_graph import ExecutionGraph, ExecutionNode
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.execution_runtime import ExecutionRuntime
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.source_constraints import (
    SourceConstraintUnavailableError,
    allowed_source_names,
)
from src.shared.execution.tool_result import ToolResult
from src.tool.grafana_tool import GrafanaTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.zabbix_tool import ZabbixTool


def _knowledge_tool() -> KnowledgeTool:
    registry = TargetRegistry()
    registry.add("localhost")
    registry.register_tool("grafana", GrafanaTool(url="http://grafana", token="t"))
    registry.register_tool("zabbix", ZabbixTool(url="http://zabbix", token="t"))
    return KnowledgeTool(target_registry=registry)


def test_single_source_constraint_becomes_exact_runtime_allow_set() -> None:
    knowledge_tool = _knowledge_tool()

    assert allowed_source_names(
        knowledge_tool,
        (SourceConstraint.GRAFANA,),
        target="localhost",
    ) == frozenset({"grafana"})
    assert allowed_source_names(
        knowledge_tool,
        (SourceConstraint.LINUX,),
        target="localhost",
    ) == frozenset({"localhost"})


def test_unavailable_ssh_constraint_fails_closed() -> None:
    with pytest.raises(SourceConstraintUnavailableError, match="SSH"):
        allowed_source_names(
            _knowledge_tool(),
            (SourceConstraint.SSH,),
            target="localhost",
        )


def test_router_never_broadens_a_grafana_only_request_to_linux() -> None:
    knowledge_tool = _knowledge_tool()
    router = CapabilityRouter()
    router.build_routes(knowledge_tool)

    assert router.resolve(
        "CPU Information", allowed_sources=frozenset({"grafana"})
    ) is None
    assert router.resolve(
        "CPU Information", allowed_sources=frozenset({"localhost"})
    ) == ("localhost", "get_cpu")
    assert router.resolve_all_with_metadata(
        "CPU Information", allowed_sources=frozenset({"grafana", "localhost"})
    )[0][0] == ("localhost", "get_cpu")


def test_evidence_provenance_uses_runtime_receipt_not_selector_hint() -> None:
    request = InvestigationRequest(raw_request="CPU", target="localhost")
    result = ToolResult(success=True, data={"usage_percent": 10}, source_kind="linux")

    EvidenceMerge(canonical_facts=False).merge(
        request,
        {"CPU Utilization": result},
        source_tool="grafana",
    )

    assert request.evidence[0].source_tool == "linux"


def test_hard_source_with_no_matching_capability_fails_closed() -> None:
    knowledge_tool = _knowledge_tool()
    router = CapabilityRouter()
    router.build_routes(knowledge_tool)
    engine = object.__new__(ExecutionEngine)
    engine._runtime = type("Runtime", (), {"router": router})()  # type: ignore[attr-defined]
    request = InvestigationRequest(raw_request="CPU")
    from src.pipeline.capability_reference import CapabilityReference

    request.capability_references = [
        CapabilityReference(name="CPU Information", evidence_name="CPU", required=True)
    ]

    with pytest.raises(SourceConstraintUnavailableError, match="cannot provide"):
        engine._validate_source_capability_coverage(
            request,
            frozenset({"grafana"}),
        )


def test_multi_source_graph_duplicates_and_pins_each_runtime_receipt() -> None:
    router = CapabilityRouter()
    router._route_candidates = {  # type: ignore[attr-defined]
        "CPU Information": [
            (("grafana", "query_cpu"), {}),
            (("zabbix", "get_cpu"), {}),
        ]
    }
    engine = object.__new__(ExecutionEngine)
    engine._runtime = type("Runtime", (), {"router": router})()  # type: ignore[attr-defined]
    request = InvestigationRequest(raw_request="compare")
    request.extracted_params = None
    graph = ExecutionGraph(
        nodes=(
            ExecutionNode(
                execution_step=ExecutionStep(
                    capability=CapabilityReference(
                        name="CPU Information", evidence_name="CPU", required=True
                    )
                )
            ),
        )
    )

    expanded = engine._expand_multi_source_graph(
        graph,
        request,
        allowed_sources=frozenset({"grafana", "zabbix"}),
    )

    assert [node.execution_step.capability.name for node in expanded.nodes] == [
        "CPU Information::grafana",
        "CPU Information::zabbix",
    ]

    class _ReceiptTool:
        def execute(self, arguments):
            return ToolResult(success=True, data={"source": arguments["source"]})

        def source_kind(self, source):
            return source

    runtime = ExecutionRuntime(knowledge_tool=_ReceiptTool())  # type: ignore[arg-type]
    runtime._router = router  # type: ignore[attr-defined]
    receipts = [
        runtime._execute_node(
            ExecutionNode(
                execution_step=ExecutionStep(
                    capability=CapabilityReference(
                        name=f"CPU Information::{source}", evidence_name="CPU"
                    ),
                    metadata=MappingProxyType(
                        {
                            "base_capability": "CPU Information",
                            "forced_source": source,
                        }
                    ),
                )
            ),
            allowed_sources=frozenset({"grafana", "zabbix"}),
        )
        for source in ("grafana", "zabbix")
    ]

    assert [receipt.source for receipt in receipts] == ["grafana", "zabbix"]
    assert [receipt.source_kind for receipt in receipts] == ["grafana", "zabbix"]


def test_comparison_receipts_keep_original_evidence_name_and_separate_sources() -> None:
    request = InvestigationRequest(raw_request="compare")
    request.capability_references = [
        CapabilityReference(name="CPU Information", evidence_name="CPU", required=True)
    ]

    EvidenceMerge(canonical_facts=False).merge(
        request,
        {
            "CPU Information::grafana": ToolResult(
                success=True, data={"usage": 10}, source_kind="grafana"
            ),
            "CPU Information::zabbix": ToolResult(
                success=True, data={"usage": 20}, source_kind="zabbix"
            ),
        },
    )

    assert [package.evidence_name for package in request.evidence] == ["CPU", "CPU"]
    assert [package.source_tool for package in request.evidence] == ["grafana", "zabbix"]
