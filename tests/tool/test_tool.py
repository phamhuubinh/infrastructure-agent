from __future__ import annotations

from abc import ABC

from src.shared.execution.tool_result import ToolResult
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
