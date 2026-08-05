from __future__ import annotations

from abc import ABC

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityResult, CapabilityStatus
from src.tool.tool import Tool


class DummyTool(Tool):
    def execute(self, arguments: dict[str, object]) -> ToolResult:
        return ToolResult(
            success=True,
            data=arguments,
        )


def test_tool_is_abstract() -> None:
    assert issubclass(Tool, ABC)


def test_tool_execute_returns_tool_result() -> None:
    tool = DummyTool()

    result = tool.execute(
        {
            "message": "hello",
        }
    )

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data == {"message": "hello"}
    assert result.error is None


def test_dispatch_accepts_capability_result_failure() -> None:
    def fail() -> CapabilityResult:
        return CapabilityResult(
            status=CapabilityStatus.COLLECTION_FAILED,
            error="collector failed",
        )

    result = DummyTool._dispatch(
        {"collect": Capability(name="collect", handler=fail)},
        {"action": "collect"},
        "DummyTool",
    )

    assert result.success is False
    assert result.capability_status is CapabilityStatus.COLLECTION_FAILED
    assert result.error == "collector failed"
