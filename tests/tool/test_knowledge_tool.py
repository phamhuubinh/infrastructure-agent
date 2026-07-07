from __future__ import annotations

import pytest

from src.tool.knowledge_tool import KnowledgeTool
from src.shared.execution.tool_result import ToolResult


def test_execute_dispatches_linux_source_to_linux_tool(monkeypatch) -> None:
    tool = KnowledgeTool()

    captured: dict[str, object] = {}

    def fake_execute(self, arguments):
        captured["arguments"] = arguments
        return ToolResult(success=True, data={"hostname": "test-host"})

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fake_execute,
    )

    result = tool.execute(
        {
            "source": "linux",
            "resource": "get_system",
        }
    )

    assert captured["arguments"] == {"action": "get_system"}
    assert result.success is True
    assert result.data == {"hostname": "test-host"}


def test_execute_returns_child_tool_error_unchanged(monkeypatch) -> None:
    tool = KnowledgeTool()

    def fake_execute(self, arguments):
        return ToolResult(
            success=False,
            error="Unknown action: 'bogus'. Available actions: get_system.",
        )

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fake_execute,
    )

    result = tool.execute(
        {
            "source": "linux",
            "resource": "bogus",
        }
    )

    assert result.success is False
    assert result.error == "Unknown action: 'bogus'. Available actions: get_system."


def test_execute_reports_unknown_source(monkeypatch) -> None:
    tool = KnowledgeTool()

    def fail_if_called(self, arguments):
        raise AssertionError("LinuxTool.execute must not be called for an unknown source.")

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fail_if_called,
    )

    result = tool.execute(
        {
            "source": "windows",
            "resource": "os_version",
        }
    )

    assert result.success is False
    assert result.error == "Unknown source: 'windows'. Available sources: linux."


def test_execute_raises_on_missing_arguments() -> None:
    tool = KnowledgeTool()

    with pytest.raises(ValueError):
        tool.execute({"source": "linux"})

    with pytest.raises(ValueError):
        tool.execute({"resource": "get_system"})


def test_execute_does_not_access_environment_directly() -> None:
    """
    KnowledgeTool must not run commands or touch the filesystem itself --
    it only forwards to a child Tool. This is verified indirectly: with
    an unknown source, execute() must return before ever touching Linux.
    """
    tool = KnowledgeTool()

    result = tool.execute(
        {
            "source": "does-not-exist",
            "resource": "anything",
        }
    )

    assert result.success is False


def test_execute_forwards_to_real_linux_tool_end_to_end() -> None:
    """
    End-to-end sanity check with the real LinuxTool (no monkeypatch):
    an unknown resource must surface LinuxTool's own error, proving the
    request actually reached LinuxTool rather than being swallowed.
    """
    tool = KnowledgeTool()

    result = tool.execute(
        {
            "source": "linux",
            "resource": "this_capability_does_not_exist",
        }
    )

    assert result.success is False
    assert "Unknown action: 'this_capability_does_not_exist'" in result.error
    assert "get_system" in result.error
