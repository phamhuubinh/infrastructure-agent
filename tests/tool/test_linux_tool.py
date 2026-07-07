from __future__ import annotations

import pytest

from src.tool.linux_tool import LinuxTool


def test_execute_raises_on_missing_action() -> None:
    tool = LinuxTool()

    with pytest.raises(ValueError):
        tool.execute({})


def test_execute_reports_unknown_action_with_available_list() -> None:
    tool = LinuxTool()

    result = tool.execute({"action": "get_disk_temperature"})

    assert result.success is False
    assert "Unknown action: 'get_disk_temperature'" in result.error
    assert "get_system" in result.error
    assert "get_network" in result.error
    assert "get_services" in result.error
    assert "get_docker" in result.error


def test_get_system_reads_os_release(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/etc/os-release"]:
            return True, 'NAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n'
        if command == ["hostname"]:
            return True, "myhost"
        if command == ["uname", "-r"]:
            return True, "6.8.0-generic"
        return False, ""

    monkeypatch.setattr("src.tool.linux_tool._run", fake_run)

    tool = LinuxTool()
    result = tool.execute({"action": "get_system"})

    assert result.success is True
    assert result.data == {
        "os": {
            "name": "Ubuntu",
            "version": "24.04",
            "id": "ubuntu",
        },
        "hostname": "myhost",
        "kernel": "6.8.0-generic",
    }


def test_get_system_falls_back_to_lsb_release(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/etc/os-release"]:
            return False, ""
        if command == ["lsb_release", "-a"]:
            return True, "Distributor ID:\tUbuntu\nRelease:\t24.04\n"
        if command == ["hostname"]:
            return True, "myhost"
        if command == ["uname", "-r"]:
            return True, "6.8.0-generic"
        return False, ""

    monkeypatch.setattr("src.tool.linux_tool._run", fake_run)

    tool = LinuxTool()
    result = tool.execute({"action": "get_system"})

    assert result.success is True
    assert result.data["os"] == {
        "name": "Ubuntu",
        "version": "24.04",
        "id": "unknown",
    }


def test_get_system_returns_unknown_when_all_sources_fail(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        return False, ""

    monkeypatch.setattr("src.tool.linux_tool._run", fake_run)

    tool = LinuxTool()
    result = tool.execute({"action": "get_system"})

    assert result.success is True
    assert result.data == {
        "os": {"name": "unknown", "version": "unknown", "id": "unknown"},
        "hostname": "unknown",
        "kernel": "unknown",
    }


def test_get_network_parses_interfaces_and_routes(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ip", "-o", "addr", "show"]:
            return True, (
                "1: lo    inet 127.0.0.1/8 scope host lo\n"
                "2: eth0    inet 192.168.1.10/24 brd 192.168.1.255 scope global eth0\n"
            )
        if command == ["ip", "route"]:
            return True, "default via 192.168.1.1 dev eth0\n192.168.1.0/24 dev eth0\n"
        return False, ""

    monkeypatch.setattr("src.tool.linux_tool._run", fake_run)

    tool = LinuxTool()
    result = tool.execute({"action": "get_network"})

    assert result.success is True
    assert result.data["interfaces"] == [
        {"name": "lo", "family": "inet", "address": "127.0.0.1/8"},
        {"name": "eth0", "family": "inet", "address": "192.168.1.10/24"},
    ]
    assert result.data["routes"] == [
        "default via 192.168.1.1 dev eth0",
        "192.168.1.0/24 dev eth0",
    ]


def test_get_network_returns_empty_lists_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.tool.linux_tool._run",
        lambda command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_network"})

    assert result.success is True
    assert result.data == {"interfaces": [], "routes": []}


def test_get_services_parses_systemctl_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "systemctl":
            return True, (
                "ssh.service     loaded active running OpenSSH server\n"
                "cron.service    loaded active running Regular background program\n"
            )
        return False, ""

    monkeypatch.setattr("src.tool.linux_tool._run", fake_run)

    tool = LinuxTool()
    result = tool.execute({"action": "get_services"})

    assert result.success is True
    assert result.data["services"] == [
        {
            "name": "ssh.service",
            "load": "loaded",
            "active": "active",
            "sub": "running",
        },
        {
            "name": "cron.service",
            "load": "loaded",
            "active": "active",
            "sub": "running",
        },
    ]


def test_get_services_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.tool.linux_tool._run",
        lambda command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_services"})

    assert result.success is True
    assert result.data == {"services": []}


def test_get_docker_reports_installed_version(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.tool.linux_tool._run",
        lambda command, timeout=5: (True, "Docker version 27.3.1, build ce12230"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_docker"})

    assert result.success is True
    assert result.data == {
        "installed": True,
        "version": "Docker version 27.3.1, build ce12230",
    }


def test_get_docker_reports_not_installed(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.tool.linux_tool._run",
        lambda command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_docker"})

    assert result.success is True
    assert result.data == {"installed": False, "version": None}


def test_run_returns_false_on_missing_binary() -> None:
    from src.tool.linux_tool import _run

    ok, output = _run(["this_binary_does_not_exist_xyz"])

    assert ok is False
    assert output == ""


def test_run_returns_false_on_timeout() -> None:
    from src.tool.linux_tool import _run

    ok, output = _run(["sleep", "5"], timeout=0.01)

    assert ok is False
    assert output == ""
