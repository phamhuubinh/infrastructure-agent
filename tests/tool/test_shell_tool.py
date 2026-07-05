from __future__ import annotations

from src.shared.execution.tool_result import ToolResult
from src.tool.shell_tool import ShellTool


def test_execute_returns_stdout() -> None:
    tool = ShellTool()

    result = tool.execute(
        {
            "command": "printf hello",
        }
    )

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.data == "hello"
    assert result.error is None


def test_execute_returns_error() -> None:
    tool = ShellTool()

    result = tool.execute(
        {
            "command": "command_that_does_not_exist",
        }
    )

    assert result.success is False
    assert result.data is None
    assert result.error is not None


def test_missing_command_raises_value_error() -> None:
    tool = ShellTool()

    try:
        tool.execute({})
        assert False
    except ValueError:
        pass
