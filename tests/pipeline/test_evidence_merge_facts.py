from __future__ import annotations

from src.pipeline.evidence_merge import (
    EvidenceMerge,
)
from src.shared.execution.tool_result import (
    ToolResult,
)
from src.tool.capability_result import (
    CapabilityStatus,
)


def test_package_conversion_builds_canonical_facts() -> None:
    result = ToolResult(
        success=True,
        data={
            "usage_percent": 25.0,
            "idle_percent": 70.0,
        },
        capability_status=(
            CapabilityStatus.VALID
        ),
        produced_fact_names=(
            "cpu.usage",
        ),
        source="server-1",
        source_kind="linux",
        resource="get_cpu_usage",
        schema_version="1",
    )

    package = (
        EvidenceMerge()
        .package_from_result(
            capability_name="CPU Utilization",
            evidence_name="CPU Usage",
            result=result,
            target="server-1",
        )
    )

    assert package.facts
    assert any(
        fact.metric == "cpu.usage"
        for fact in package.facts
    )


def test_fact_layer_can_be_disabled_without_raw_schema_change() -> None:
    result = ToolResult(
        success=True,
        data={"usage_percent": 25.0},
        capability_status=(
            CapabilityStatus.VALID
        ),
    )

    package = EvidenceMerge(
        canonical_facts=False,
    ).package_from_result(
        capability_name="CPU",
        evidence_name="CPU",
        result=result,
        target="server-1",
    )

    assert package.facts == ()
    assert package.data == {
        "usage_percent": 25.0
    }
