from __future__ import annotations

import pytest

from src.shared.execution.tool_result import ToolResult
from src.tool.execution_backend import LocalExecutionBackend, SSHExecutionBackend
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


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
            "source": "localhost",
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
            "source": "localhost",
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
    assert result.error == "Unknown source: 'windows'. Available sources: localhost."


def test_knowledge_tool_with_remote_target(monkeypatch) -> None:
    registry = TargetRegistry()
    registry.add("linux", LocalExecutionBackend())
    registry.add(
        "prod",
        SSHExecutionBackend(host="10.0.0.1", user="admin"),
    )
    tool = KnowledgeTool(target_registry=registry)

    captured: dict[str, object] = {}

    def fake_execute(self, arguments):
        captured["arguments"] = arguments
        return ToolResult(success=True, data={"hostname": "remote-host"})

    monkeypatch.setattr(
        "src.tool.linux_tool.LinuxTool.execute",
        fake_execute,
    )

    result = tool.execute(
        {
            "source": "prod",
            "resource": "get_system",
        }
    )

    assert captured["arguments"] == {"action": "get_system"}
    assert result.success is True
    assert result.data == {"hostname": "remote-host"}


def test_knowledge_tool_lists_all_target_sources() -> None:
    registry = TargetRegistry()
    registry.add("linux", LocalExecutionBackend())
    registry.add("staging", SSHExecutionBackend(host="10.0.0.2"))
    registry.add("lab", SSHExecutionBackend(host="10.0.0.3"))
    tool = KnowledgeTool(target_registry=registry)

    caps = tool.get_capabilities()

    assert "linux" in caps
    assert "staging" in caps
    assert "lab" in caps
    assert caps["linux"] == caps["staging"] == caps["lab"]


def test_execute_raises_on_missing_arguments() -> None:
    tool = KnowledgeTool()

    with pytest.raises(ValueError):
        tool.execute({"source": "localhost"})

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


def test_discovers_localhost_capabilities() -> None:
    tool = KnowledgeTool()
    caps = tool.get_capabilities()
    assert "localhost" in caps
    assert "get_system" in caps["localhost"]
    assert "get_memory" in caps["localhost"]
    assert len(caps["localhost"]) > 10


def test_discovers_registered_tool_capabilities() -> None:
    from src.tool.zabbix_tool import ZabbixTool

    registry = TargetRegistry()
    registry.add("localhost")
    registry.register_tool("zabbix", ZabbixTool(url="http://x", token="x"))
    tool = KnowledgeTool(target_registry=registry)

    caps = tool.get_capabilities()

    assert "localhost" in caps
    assert "zabbix" in caps
    assert "get_system" in caps["localhost"]
    assert "get_hosts" in caps["zabbix"]
    assert "get_problems" in caps["zabbix"]


def test_discovers_grafana_tool_capabilities() -> None:
    from src.tool.grafana_tool import GrafanaTool

    registry = TargetRegistry()
    registry.add("localhost")
    registry.register_tool("grafana", GrafanaTool(url="http://x", token="x"))
    tool = KnowledgeTool(target_registry=registry)

    caps = tool.get_capabilities()

    assert "localhost" in caps
    assert "grafana" in caps
    assert "health" in caps["grafana"]
    assert "dashboards" in caps["grafana"]
    assert "dashboard_summary" in caps["grafana"]


def test_empty_registry_returns_empty_dict() -> None:
    registry = TargetRegistry()
    tool = KnowledgeTool(target_registry=registry)
    assert tool.get_capabilities() == {}


def test_discovers_linux_and_zabbix_have_different_capabilities() -> None:
    from src.tool.zabbix_tool import ZabbixTool

    registry = TargetRegistry()
    registry.add("localhost")
    registry.register_tool("zabbix", ZabbixTool(url="http://x", token="x"))
    tool = KnowledgeTool(target_registry=registry)

    caps = tool.get_capabilities()

    assert caps["localhost"] != caps["zabbix"]
    assert "get_hosts" not in caps["localhost"]
    assert "get_ssh" not in caps["zabbix"]


def test_get_capability_metadata_structure() -> None:
    """get_capability_metadata returns structured capability metadata."""
    tool = KnowledgeTool()
    meta = tool.get_capability_metadata()

    assert "localhost" in meta
    localhost_caps = meta["localhost"]
    assert len(localhost_caps) > 10

    get_system = [c for c in localhost_caps if c["name"] == "get_system"]
    assert len(get_system) == 1
    sys_entry = get_system[0]
    assert "category" in sys_entry
    assert "intents" in sys_entry
    assert "related" in sys_entry
    assert "covers" in sys_entry
    assert "handler" not in sys_entry


def test_get_capability_metadata_registered_tools() -> None:
    """All registered tools should appear in metadata."""
    from src.tool.zabbix_tool import ZabbixTool

    registry = TargetRegistry()
    registry.add("localhost")
    registry.register_tool("zabbix", ZabbixTool(url="http://x", token="x"))
    tool = KnowledgeTool(target_registry=registry)

    meta = tool.get_capability_metadata()
    assert "localhost" in meta
    assert "zabbix" in meta
    assert len(meta["zabbix"]) > 0


def test_get_capability_metadata_empty_registry() -> None:
    registry = TargetRegistry()
    tool = KnowledgeTool(target_registry=registry)
    assert tool.get_capability_metadata() == {}


def test_execute_forwards_to_real_linux_tool_end_to_end() -> None:
    """
    End-to-end sanity check with the real LinuxTool (no monkeypatch):
    an unknown resource must surface LinuxTool's own error, proving the
    request actually reached LinuxTool rather than being swallowed.
    """
    tool = KnowledgeTool()

    result = tool.execute(
        {
            "source": "localhost",
            "resource": "this_capability_does_not_exist",
        }
    )

    assert result.success is False
    assert "Unknown action: 'this_capability_does_not_exist'" in result.error
    assert "get_system" in result.error
