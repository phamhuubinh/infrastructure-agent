from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.tool_result import ToolResult


def test_tool_result_stores_values() -> None:
    result = ToolResult(
        success=True,
        data="hello",
        error=None,
    )

    assert result.success is True
    assert result.data == "hello"
    assert result.error is None


def test_tool_result_is_immutable() -> None:
    result = ToolResult(
        success=False,
        data=None,
        error="boom",
    )

    with pytest.raises(FrozenInstanceError):
        result.success = True  # type: ignore[misc]
