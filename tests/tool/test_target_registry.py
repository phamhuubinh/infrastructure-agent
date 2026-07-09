from __future__ import annotations

import pytest

from src.tool.execution_backend import LocalExecutionBackend, SSHExecutionBackend
from src.tool.linux_tool import LinuxTool
from src.tool.target_registry import TargetRegistry


def test_add_local_target() -> None:
    registry = TargetRegistry()
    registry.add("linux")

    assert registry.target_names() == ["linux"]

    tool = registry.get_tool("linux")
    assert isinstance(tool, LinuxTool)


def test_add_remote_target() -> None:
    registry = TargetRegistry()
    registry.add("prod", SSHExecutionBackend(host="10.0.0.1"))

    tool = registry.get_tool("prod")
    assert isinstance(tool, LinuxTool)


def test_get_tool_raises_on_unknown() -> None:
    registry = TargetRegistry()

    with pytest.raises(KeyError):
        registry.get_tool("does_not_exist")


def test_duplicate_target_raises() -> None:
    registry = TargetRegistry()
    registry.add("linux")

    with pytest.raises(ValueError):
        registry.add("linux")


def test_multiple_targets_have_independent_tools() -> None:
    registry = TargetRegistry()
    registry.add("linux", LocalExecutionBackend())
    registry.add("staging", SSHExecutionBackend(host="10.0.0.2"))

    tool_a = registry.get_tool("linux")
    tool_b = registry.get_tool("staging")

    assert tool_a is not tool_b
    assert registry.target_names() == ["linux", "staging"]


def test_remove_target() -> None:
    registry = TargetRegistry()
    registry.add("linux")
    registry.add("prod", SSHExecutionBackend(host="10.0.0.1"))

    registry.remove("prod")
    assert registry.target_names() == ["linux"]

    with pytest.raises(KeyError):
        registry.get_tool("prod")


def test_remove_nonexistent_target_raises() -> None:
    registry = TargetRegistry()

    with pytest.raises(KeyError):
        registry.remove("does_not_exist")
