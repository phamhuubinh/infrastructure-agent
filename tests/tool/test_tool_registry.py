from __future__ import annotations

import pytest

from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool
from src.tool.tool_registry import ToolRegistry


class DummyTool(Tool):
    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        return ToolResult(success=True, data=arguments)


def test_register_and_get_tool() -> None:
    registry = ToolRegistry()
    tool = DummyTool()

    registry.register(
        tool_id="dummy",
        tool=tool,
    )

    assert registry.get("dummy") is tool


def test_duplicate_tool_registration_raises_value_error() -> None:
    registry = ToolRegistry()

    registry.register(
        tool_id="dummy",
        tool=DummyTool(),
    )

    with pytest.raises(ValueError):
        registry.register(
            tool_id="dummy",
            tool=DummyTool(),
        )


def test_unknown_tool_raises_key_error() -> None:
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        registry.get("missing")
