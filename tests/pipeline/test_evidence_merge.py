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


def test_package_from_successful_result() -> None:
    result = ToolResult(
        success=True,
        data={"cores": 4},
        capability_status=(
            CapabilityStatus.VALID
        ),
        source="server-1",
        source_kind="linux",
        resource="get_cpu_info",
    )

    package = (
        EvidenceMerge()
        .package_from_result(
            capability_name="system.cpu.info",
            evidence_name="CPU",
            result=result,
            target="server-1",
        )
    )

    assert package.success is True
    assert package.data == {"cores": 4}
    assert package.source == "server-1"


def test_package_from_failed_result_is_fail_closed() -> None:
    result = ToolResult(
        success=False,
        error="timeout",
        capability_status=(
            CapabilityStatus
            .COLLECTION_FAILED
        ),
        source="server-1",
    )

    package = (
        EvidenceMerge()
        .package_from_result(
            capability_name="system.cpu",
            evidence_name="CPU",
            result=result,
            target="server-1",
        )
    )

    assert package.success is False
    assert package.data is None
    assert package.error == "timeout"


def test_partial_result_preserves_partial_payload() -> None:
    result = ToolResult(
        success=False,
        data={"available_kb": 1024},
        error="optional probe failed",
        capability_status=(
            CapabilityStatus.PARTIAL
        ),
    )

    package = (
        EvidenceMerge()
        .package_from_result(
            capability_name="system.memory",
            evidence_name="Memory",
            result=result,
            target="server-1",
        )
    )

    assert package.status is (
        CapabilityStatus.PARTIAL
    )
    assert package.data == {
        "available_kb": 1024
    }
