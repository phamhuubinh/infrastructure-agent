from __future__ import annotations

import pytest

from src.tool.capability_result import CapabilityStatus
from src.tool.linux_tool import LinuxTool


def _assert_collection_failed_without_data(result) -> None:
    assert result.success is False
    assert result.capability_status is CapabilityStatus.COLLECTION_FAILED
    assert result.data is None
    assert result.command_results
    assert all(not command.success for command in result.command_results)


def test_execute_raises_on_missing_action() -> None:
    tool = LinuxTool()

    with pytest.raises(ValueError):
        tool.execute({})


def test_execute_reports_unknown_action_with_available_list() -> None:
    tool = LinuxTool()

    result = tool.execute({"action": "get_disk_temperature"})

    assert result.success is False
    assert result.error is not None
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

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

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

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_system"})

    assert result.success is True
    assert result.data["os"] == {
        "name": "Ubuntu",
        "version": "24.04",
        "id": "unknown",
    }


def test_get_system_does_not_fabricate_unknowns_when_all_sources_fail(
    monkeypatch,
) -> None:
    def fake_run(command, timeout=5):
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_system"})

    _assert_collection_failed_without_data(result)


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

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

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


def test_get_network_does_not_fabricate_empty_facts_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_network"})

    _assert_collection_failed_without_data(result)


def test_get_services_parses_systemctl_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "systemctl":
            return True, (
                "ssh.service     loaded active running OpenSSH server\n"
                "cron.service    loaded active running Regular background program\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_services"})

    assert result.success is True
    assert result.data["total"] == 2
    assert result.data["running"] == 2


def test_get_services_does_not_fabricate_zero_counts_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_services"})

    _assert_collection_failed_without_data(result)


def test_get_docker_reports_installed_version(monkeypatch) -> None:
    call_count = 0

    def fake_run(command, timeout=5):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (True, "Docker version 27.3.1, build ce12230")
        return (True, "abc123 nginx web-nginx Up 2 hours")

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_docker"})

    assert result.success is True
    assert result.data["installed"] is True
    assert "version" in result.data
    assert "containers" in result.data


def test_get_docker_does_not_report_not_installed_on_probe_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_docker"})

    _assert_collection_failed_without_data(result)


def test_execute_reports_unknown_action_includes_new_capabilities() -> None:
    tool = LinuxTool()

    result = tool.execute({"action": "get_disk_temperature"})

    assert result.success is False
    assert result.error is not None
    for name in [
        "get_cpu",
        "get_memory",
        "get_disk",
        "get_filesystem",
        "get_dns",
        "get_process",
        "get_user",
        "get_package",
    ]:
        assert name in result.error


def test_get_cpu_parses_model_and_cores(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["nproc"]:
            return True, "4"
        if command == ["cat", "/proc/cpuinfo"]:
            return True, (
                "processor\t: 0\n"
                "model name\t: Intel(R) Core(TM) i7-9700\n"
                "processor\t: 1\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_cpu"})

    assert result.success is True
    assert result.data["model"] == "Intel(R) Core(TM) i7-9700"
    assert result.data["cores"] == 4
    assert "threads" in result.data
    assert "usage" not in result.data
    assert "load" not in result.data


def test_get_cpu_does_not_fabricate_zero_values_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_cpu"})

    _assert_collection_failed_without_data(result)


def test_get_memory_parses_meminfo(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/proc/meminfo"]:
            return True, (
                "MemTotal:       16384000 kB\n"
                "MemFree:         2048000 kB\n"
                "MemAvailable:    8192000 kB\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_memory"})

    assert result.success is True
    assert result.data == {
        "total_kb": 16384000,
        "used_kb": 8192000,
        "free_kb": 2048000,
        "available_kb": 8192000,
        "usage_percent": 50.0,
        "total_bytes": 16777216000,
        "used_bytes": 8388608000,
        "free_bytes": 2097152000,
        "available_bytes": 8388608000,
    }


def test_get_memory_does_not_fabricate_zero_values_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_memory"})

    _assert_collection_failed_without_data(result)


def test_get_disk_parses_df_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "df":
            return True, (
                "source         fstype     1B-blocks       used       avail use% target\n"
                "/dev/sda1      ext4      100000000   40000000   60000000  40% /\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_disk"})

    assert result.success is True
    assert result.data["disk_count"] == 1
    assert result.data["high_usage_count"] == 0
    assert result.data["disks"][0]["source"] == "/dev/sda1"


def test_get_disk_does_not_fabricate_empty_facts_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_disk"})

    _assert_collection_failed_without_data(result)


def test_get_filesystem_parses_proc_mounts(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/proc/mounts"]:
            return True, (
                "/dev/sda1 / ext4 rw,relatime 0 0\ntmpfs /tmp tmpfs rw,nosuid 0 0\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_filesystem"})

    assert result.success is True
    assert result.data == {
        "mounts": [
            {"device": "/dev/sda1", "mountpoint": "/", "fstype": "ext4"},
            {"device": "tmpfs", "mountpoint": "/tmp", "fstype": "tmpfs"},
        ]
    }


def test_get_filesystem_does_not_fabricate_empty_facts_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_filesystem"})

    _assert_collection_failed_without_data(result)


def test_get_dns_parses_resolv_conf(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/etc/resolv.conf"]:
            return True, "nameserver 8.8.8.8\nnameserver 1.1.1.1\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_dns"})

    assert result.success is True
    assert result.data == {"nameservers": ["8.8.8.8", "1.1.1.1"]}


def test_get_dns_does_not_fabricate_empty_facts_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_dns"})

    _assert_collection_failed_without_data(result)


def test_get_process_parses_ps_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "ps":
            return True, "1 S 0.0 0.1 /sbin/init\n42 S 0.1 0.2 /usr/sbin/sshd\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_process"})

    assert result.success is True
    assert result.data["total"] == 2
    assert "summary" in result.data
    assert "zombie_count" in result.data
    assert len(result.data["top_memory"]) == 2
    assert len(result.data["top_cpu"]) == 2


def test_get_process_does_not_fabricate_zero_counts_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_process"})

    _assert_collection_failed_without_data(result)


def test_get_user_parses_etc_passwd(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/etc/passwd"]:
            return True, (
                "root:x:0:0:root:/root:/bin/bash\n"
                "alice:x:1000:1000:Alice:/home/alice:/bin/bash\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_user"})

    assert result.success is True
    assert result.data == {
        "users": [
            {
                "name": "root",
                "uid": "0",
                "gid": "0",
                "home": "/root",
                "shell": "/bin/bash",
            },
            {
                "name": "alice",
                "uid": "1000",
                "gid": "1000",
                "home": "/home/alice",
                "shell": "/bin/bash",
            },
        ]
    }


def test_get_user_does_not_fabricate_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_user"})

    _assert_collection_failed_without_data(result)


def test_get_package_returns_count_summary(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "dpkg-query":
            return True, "bash 5.2.21-2\ncurl 8.5.0-2\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_package"})

    assert result.success is True
    assert result.data["package_count"] == 2
    assert "summary" in result.data


def test_get_package_falls_back_to_rpm(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "dpkg-query":
            return False, ""
        if command[0] == "rpm":
            return True, "bash 5.2.15\ncurl 8.4.0\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_package"})

    assert result.success is True
    assert result.data["package_count"] == 2


def test_get_package_does_not_fabricate_zero_when_all_probes_fail(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_package"})

    _assert_collection_failed_without_data(result)


def test_get_ssh_uses_effective_config_when_available(monkeypatch) -> None:
    """GA2-G08: `sshd -T` provides the effective state (Includes/Match/defaults
    already applied) and must win over raw config parsing."""
    calls: list[list[str]] = []

    def fake_run(command, timeout=5):
        calls.append(command)
        if command == ["sshd", "-T"]:
            return (
                True,
                "port 2222\npermitrootlogin no\npasswordauthentication yes\n",
            )
        if command == ["systemctl", "is-active", "ssh"]:
            return True, "active"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_ssh"})

    assert result.success is True
    assert ["sshd", "-T"] in calls
    assert result.data["source"] == "effective_sshd_config"
    assert result.data == {
        "port": "2222",
        "permit_root_login": "no",
        "password_authentication": "yes",
        "active": "active",
        "source": "effective_sshd_config",
        "has_config": True,
    }


def test_get_ssh_absent_directive_in_effective_config_uses_default(monkeypatch) -> None:
    """An absent directive in the effective output is resolved by sshd -T
    (the effective value), not guessed."""

    def fake_run(command, timeout=5):
        if command == ["sshd", "-T"]:
            return True, "port 22\npasswordauthentication yes\n"
        if command == ["systemctl", "is-active", "ssh"]:
            return True, "active"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_ssh"})

    assert result.success is True
    assert result.data["source"] == "effective_sshd_config"
    assert result.data["permit_root_login"] == "prohibit-password"


def test_get_ssh_uses_context_specific_effective_config(monkeypatch) -> None:
    """A complete safe context must be passed as argv to ``sshd -T -C``."""
    calls: list[list[str]] = []

    def fake_run(command, timeout=5):
        calls.append(command)
        if command == [
            "sshd",
            "-T",
            "-C",
            "user=deploy,host=app.example,addr=203.0.113.10",
        ]:
            return True, "permitrootlogin no\nport 22\npasswordauthentication yes\n"
        if command == ["systemctl", "is-active", "ssh"]:
            return True, "active"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )
    result = LinuxTool().execute(
        {
            "action": "get_ssh",
            "user": "deploy",
            "host": "app.example",
            "addr": "203.0.113.10",
        }
    )

    assert result.success is True
    assert result.data["source"] == "effective_sshd_config_context"
    assert result.data["permit_root_login"] == "no"
    assert ["sshd", "-T"] not in calls


def test_get_ssh_rejects_incomplete_or_unsafe_context_without_execution(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: calls.append(command) or (False, ""),
    )
    tool = LinuxTool()
    for context in (
        {"user": "deploy"},
        {"user": "deploy;id", "host": "app.example", "addr": "203.0.113.10"},
        {"user": "deploy", "host": "app.example", "addr": "not-an-ip"},
    ):
        result = tool.execute({"action": "get_ssh", **context})
        assert result.success is False
        assert result.data is None
    assert calls == []


def test_get_ssh_normalizes_invalid_permit_root_login_to_unknown(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["sshd", "-T"]:
            return True, "permitrootlogin definitely\n"
        return True, "active"

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )
    result = LinuxTool().execute({"action": "get_ssh"})

    assert result.success is True
    assert result.data["permit_root_login"] == "UNKNOWN"


def test_get_ssh_match_without_context_is_context_specific_unknown(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["sshd", "-T"]:
            return True, "permitrootlogin no\nport 22\n"
        if command == ["cat", "/etc/ssh/sshd_config"]:
            return True, "PermitRootLogin no\nMatch User deploy\n  PermitRootLogin yes\n"
        if command == ["systemctl", "is-active", "ssh"]:
            return True, "active"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )
    result = LinuxTool().execute({"action": "get_ssh"})

    assert result.success is True
    assert result.data["permit_root_login"] == "UNKNOWN"
    assert result.data["source"] == "context_specific_unknown"


def test_get_ssh_match_with_context_returns_context_specific_value(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == [
            "sshd",
            "-T",
            "-C",
            "user=deploy,host=app.example,addr=203.0.113.10",
        ]:
            return True, "permitrootlogin yes\nport 22\n"
        if command == ["systemctl", "is-active", "ssh"]:
            return True, "active"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )
    result = LinuxTool().execute(
        {
            "action": "get_ssh",
            "user": "deploy",
            "host": "app.example",
            "addr": "203.0.113.10",
        }
    )

    assert result.success is True
    assert result.data["permit_root_login"] == "yes"
    assert result.data["source"] == "effective_sshd_config_context"


def test_get_ssh_raw_config_fallback_reports_unknown_when_directive_absent(
    monkeypatch,
) -> None:
    """GA2-G08: when sshd -T is unavailable, an absent raw directive is
    UNKNOWN rather than a guessed default."""

    def fake_run(command, timeout=5):
        if command == ["sshd", "-T"]:
            return False, "sshd not found"
        if command == ["cat", "/etc/ssh/sshd_config"]:
            return True, "Port 2222\nPermitRootLogin no\n"
        if command == ["systemctl", "is-active", "ssh"]:
            return True, "active"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_ssh"})

    assert result.success is True
    assert result.data["source"] == "raw_config_fallback"
    assert result.data["permit_root_login"] == "no"
    # Absent directive in raw config -> UNKNOWN, never a default guess.
    assert result.data["password_authentication"] == "UNKNOWN"


def test_get_ssh_does_not_fabricate_defaults_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_ssh"})

    _assert_collection_failed_without_data(result)


def test_get_hardware_reads_dmidecode(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["dmidecode", "-s", "system-manufacturer"]:
            return True, "Dell Inc."
        if command == ["dmidecode", "-s", "system-product-name"]:
            return True, "PowerEdge R640"
        if command == ["dmidecode", "-s", "system-serial-number"]:
            return True, "ABC123"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_hardware"})

    assert result.success is True
    assert result.data == {
        "manufacturer": "Dell Inc.",
        "product": "PowerEdge R640",
        "serial": "ABC123",
    }


def test_get_hardware_does_not_fabricate_unknowns_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_hardware"})

    _assert_collection_failed_without_data(result)


def test_get_pci_parses_lspci_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["lspci"]:
            return True, "00:00.0 Host bridge: Intel Corporation Device 1234\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_pci"})

    assert result.success is True
    assert result.data == {
        "devices": [
            {
                "address": "00:00.0",
                "description": "Host bridge: Intel Corporation Device 1234",
            }
        ]
    }


def test_get_pci_does_not_fabricate_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_pci"})

    _assert_collection_failed_without_data(result)


def test_get_usb_parses_lsusb_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["lsusb"]:
            return True, "Bus 001 Device 002: ID 8087:0aaa Intel Corp. Hub\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_usb"})

    assert result.success is True
    assert result.data == {
        "devices": [
            {
                "bus": "001",
                "device": "002",
                "id": "8087:0aaa",
                "description": "Intel Corp. Hub",
            }
        ]
    }


def test_get_usb_does_not_fabricate_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_usb"})

    _assert_collection_failed_without_data(result)


def test_get_gpu_filters_vga_controllers(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["lspci"]:
            return True, (
                "00:00.0 Host bridge: Intel Corporation Device 1234\n"
                "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_gpu"})

    assert result.success is True
    assert result.data == {
        "gpus": [
            {
                "address": "00:02.0",
                "description": "VGA compatible controller: Intel Corporation UHD Graphics",
            }
        ]
    }


def test_get_gpu_does_not_fabricate_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_gpu"})

    _assert_collection_failed_without_data(result)


def test_get_block_device_parses_lsblk_json(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "lsblk":
            return True, (
                '{"blockdevices": [{"name": "sda", "size": 100, '
                '"type": "disk", "mountpoint": null, "fstype": null}]}'
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_block_device"})

    assert result.success is True
    assert result.data == {
        "devices": [
            {
                "name": "sda",
                "size": 100,
                "type": "disk",
                "mountpoint": None,
                "fstype": None,
            }
        ]
    }


def test_get_block_device_does_not_fabricate_empty_facts_on_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_block_device"})

    _assert_collection_failed_without_data(result)


def test_get_block_device_returns_empty_list_on_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (True, "not json"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_block_device"})

    assert result.success is True
    assert result.data == {}


def test_get_secureboot_reports_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (True, "SecureBoot enabled"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_secureboot"})

    assert result.success is True
    assert result.data == {"enabled": True}


def test_get_secureboot_does_not_fabricate_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_secureboot"})

    _assert_collection_failed_without_data(result)


def test_get_apparmor_reports_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (True, "Y"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_apparmor"})

    assert result.success is True
    assert result.data == {"enabled": True}


def test_get_apparmor_reports_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (True, "N"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_apparmor"})

    assert result.success is True
    assert result.data == {"enabled": False}


def test_get_apparmor_does_not_fabricate_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_apparmor"})

    _assert_collection_failed_without_data(result)


def test_get_selinux_reports_status(monkeypatch) -> None:
    """SELinux reports status via getenforce fallback (sestatus not available)."""

    def fake_run(command, timeout=5):
        if command == ["sestatus"]:
            return (False, "")
        if command == ["getenforce"]:
            return (True, "Enforcing")
        return (False, "")

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_selinux"})

    assert result.success is True
    assert result.data == {"status": "Enforcing", "installed": True}


def test_get_selinux_does_not_report_not_installed_on_probe_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_selinux"})

    _assert_collection_failed_without_data(result)


def test_get_firewall_prefers_ufw_active(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ufw", "status", "verbose"]:
            return True, (
                "Status: active\n"
                "Logging: on (low)\n"
                "Default: deny (incoming), allow (outgoing)\n"
                "---\n"
                "22/tcp    ALLOW IN    Anywhere\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data["backend"] == "ufw"
    assert result.data["active"] is True


def test_get_firewall_prefers_ufw_inactive(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ufw", "status", "verbose"]:
            return True, (
                "Status: inactive\n"
                "Logging: off\n"
                "Default: deny (incoming), allow (outgoing)\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data["backend"] == "ufw"
    assert result.data["active"] is False


def test_get_firewall_falls_back_to_iptables(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ufw", "status", "verbose"]:
            return False, ""
        if command == ["iptables", "-L", "-n", "-v", "--line-numbers"]:
            return True, "Chain INPUT (policy ACCEPT 0 packets, 0 bytes)"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data["backend"] == "iptables"
    assert result.data["active"] is True


def test_get_firewall_falls_back_to_nftables(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ufw", "status", "verbose"]:
            return False, ""
        if command == ["iptables", "-L", "-n", "-v", "--line-numbers"]:
            return False, ""
        if command == ["nft", "list", "ruleset"]:
            return (
                True,
                "table inet filter {\n  chain input { type filter hook input priority 0; }\n}",
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data["backend"] == "nftables"
    assert result.data["active"] is True


def test_get_firewall_does_not_report_inactive_when_all_probes_fail(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    _assert_collection_failed_without_data(result)


def test_get_certificate_lists_filenames(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ls", "/etc/ssl/certs"]:
            return True, "ca-certificates.crt\nDigiCert_Global_Root_CA.pem\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_certificate"})

    assert result.success is True
    assert result.data == {
        "certificates": ["ca-certificates.crt", "DigiCert_Global_Root_CA.pem"]
    }


def test_get_certificate_does_not_fabricate_empty_list_on_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_certificate"})

    _assert_collection_failed_without_data(result)


def test_get_journal_returns_entries(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "journalctl":
            return True, "Jul 07 10:00:00 host sshd[1]: started\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_journal"})

    assert result.success is True
    assert result.data == {"entries": ["Jul 07 10:00:00 host sshd[1]: started"]}


def test_get_journal_does_not_fabricate_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_journal"})

    _assert_collection_failed_without_data(result)


def test_get_log_prefers_syslog(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["tail", "-n", "50", "/var/log/syslog"]:
            return True, "line one\nline two\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_log"})

    assert result.success is True
    assert result.data == {
        "source": "/var/log/syslog",
        "lines": ["line one", "line two"],
    }


def test_get_log_falls_back_to_messages(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["tail", "-n", "50", "/var/log/syslog"]:
            return False, ""
        if command == ["tail", "-n", "50", "/var/log/messages"]:
            return True, "line one\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_log"})

    assert result.success is True
    assert result.data == {"source": "/var/log/messages", "lines": ["line one"]}


def test_get_log_does_not_fabricate_unknown_source_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_log"})

    _assert_collection_failed_without_data(result)


def test_get_time_parses_timedatectl(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["timedatectl"]:
            return True, (
                "Local time: Tue 2026-07-07 10:00:00 UTC\n"
                "Time zone: UTC (UTC, +0000)\n"
                "System clock synchronized: yes\n"
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_time"})

    assert result.success is True
    assert result.data == {
        "local_time": "Tue 2026-07-07 10:00:00 UTC",
        "time_zone": "UTC (UTC, +0000)",
        "ntp_synchronized": "yes",
    }


def test_get_time_does_not_fabricate_unknown_fields_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_time"})

    _assert_collection_failed_without_data(result)


def test_get_locale_parses_key_value_pairs(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["locale"]:
            return True, 'LANG=en_US.UTF-8\nLC_TIME="en_US.UTF-8"\n'
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_locale"})

    assert result.success is True
    assert result.data == {"locale": {"LANG": "en_US.UTF-8", "LC_TIME": "en_US.UTF-8"}}


def test_get_locale_does_not_fabricate_empty_dict_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_locale"})

    _assert_collection_failed_without_data(result)


def test_get_environment_returns_names_not_values(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["env"]:
            return True, "PATH=/usr/bin\nSECRET_TOKEN=<redacted>\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_environment"})

    assert result.success is True
    assert result.data == {"variables": ["PATH", "SECRET_TOKEN"]}
    assert "<redacted>" not in str(result.data)


def test_get_environment_does_not_fabricate_empty_list_on_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_environment"})

    _assert_collection_failed_without_data(result)


def test_get_session_parses_who_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["who"]:
            return True, "alice    pts/0        2026-07-07 10:00\n"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_session"})

    assert result.success is True
    assert result.data == {
        "sessions": [
            {
                "user": "alice",
                "terminal": "pts/0",
            }
        ]
    }


def test_get_session_does_not_fabricate_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_session"})

    _assert_collection_failed_without_data(result)


def test_get_module_parses_lsmod_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["lsmod"]:
            return (
                True,
                "Module                  Size  Used by\nnf_tables              200000  1\n",
            )
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_module"})

    assert result.success is True
    assert result.data == {"modules": [{"name": "nf_tables", "size": "200000"}]}


def test_get_module_does_not_fabricate_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_module"})

    _assert_collection_failed_without_data(result)


def test_get_lxd_does_not_report_not_installed_on_probe_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_lxd"})

    _assert_collection_failed_without_data(result)


def test_get_lxd_reports_installed_with_containers(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["lxd", "--version"]:
            return True, "5.21.2"
        if command == ["lxc", "list", "--format", "json"]:
            return True, '[{"name": "c1"}, {"name": "c2"}]'
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_lxd"})

    assert result.success is True
    assert result.data == {
        "installed": True,
        "version": "5.21.2",
        "containers": ["c1", "c2"],
    }


def test_get_lxd_returns_empty_containers_on_invalid_json(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["lxd", "--version"]:
            return True, "5.21.2"
        if command == ["lxc", "list", "--format", "json"]:
            return True, "not json"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_lxd"})

    assert result.success is True
    assert result.data == {
        "installed": True,
        "version": "5.21.2",
        "containers": [],
    }


def test_linux_tool_accepts_ssh_backend(monkeypatch) -> None:
    from src.tool.execution_backend import SSHExecutionBackend

    captured: list[tuple[list[str] | None, int]] = []

    def fake_subprocess_run(*, command=None, **kwargs):
        captured.append((command, 0))

        class Fake:
            returncode = 0
            stdout = "mocked output"

        return Fake()

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        lambda *args, **kwargs: fake_subprocess_run(
            command=args[0] if args else kwargs.get("command")
        ),
    )

    backend = SSHExecutionBackend(host="10.0.0.1", user="admin")
    tool = LinuxTool(backend=backend)
    result = tool.execute({"action": "get_system"})

    assert result.success is True


def test_ssh_backend_constructs_correct_command(monkeypatch) -> None:
    from src.tool.execution_backend import SSHExecutionBackend

    captured_commands: list[list[str]] = []

    def fake_run(popenargs, **kwargs):
        captured_commands.append(list(popenargs))

        class Fake:
            returncode = 0
            stdout = "mocked"

        return Fake()

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        fake_run,
    )

    backend = SSHExecutionBackend(
        host="10.0.0.1",
        user="admin",
        port=2222,
        identity_file="/root/.ssh/id_rsa",
    )
    backend.run(["uname", "-r"])

    assert len(captured_commands) == 1
    ssh_cmd = captured_commands[0]
    assert ssh_cmd[0] == "ssh"
    assert "-p" in ssh_cmd
    assert "2222" in ssh_cmd
    assert "-i" in ssh_cmd
    assert "/root/.ssh/id_rsa" in ssh_cmd
    assert "admin@10.0.0.1" in ssh_cmd


def test_ssh_backend_includes_batch_mode(monkeypatch) -> None:
    from src.tool.execution_backend import SSHExecutionBackend

    captured_commands = []

    def fake_run(popenargs, **kwargs):
        captured_commands.append(list(popenargs))

        class Fake:
            returncode = 0
            stdout = "mocked"

        return Fake()

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        fake_run,
    )

    backend = SSHExecutionBackend(host="10.0.0.1")
    backend.run(["uname", "-r"])

    assert "-o" in captured_commands[0]
    assert "BatchMode=yes" in captured_commands[0]


def test_ssh_backend_reports_password_prompt(monkeypatch) -> None:
    from src.tool.execution_backend import SSHExecutionBackend

    def fake_fail(popenargs, **kwargs):
        class Fake:
            returncode = 1
            stdout = ""
            stderr = "root@10.0.0.1's password:"

        return Fake()

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        fake_fail,
    )

    backend = SSHExecutionBackend(host="10.0.0.1")
    result = backend.run(["uname", "-r"])

    assert result.success is False
    assert "SSH authentication failed" in result.stderr


def test_ssh_backend_returns_false_on_failure(monkeypatch) -> None:
    from src.tool.execution_backend import SSHExecutionBackend

    def fake_fail(popenargs, **kwargs):
        class Fake:
            returncode = 1
            stdout = ""
            stderr = "permission denied"

        return Fake()

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        fake_fail,
    )

    backend = SSHExecutionBackend(host="10.0.0.1")
    result = backend.run(["uname", "-r"])

    assert result.success is False
    assert "permission denied" in result.stderr


def test_ssh_backend_returns_false_on_os_error(monkeypatch) -> None:
    from src.tool.execution_backend import SSHExecutionBackend

    def fake_os_error(popenargs, **kwargs):
        msg = "ssh not found"
        raise OSError(msg)

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        fake_os_error,
    )

    backend = SSHExecutionBackend(host="10.0.0.1")
    result = backend.run(["uname", "-r"])

    assert result.success is False
    assert result.stdout == ""


def test_local_backend_returns_false_on_missing_binary() -> None:
    from src.tool.execution_backend import LocalExecutionBackend

    backend = LocalExecutionBackend()
    result = backend.run(["this_binary_does_not_exist_xyz"])

    assert result.success is False
    assert result.stdout == ""


def test_local_backend_returns_false_on_timeout() -> None:
    from src.tool.execution_backend import LocalExecutionBackend

    backend = LocalExecutionBackend()
    result = backend.run(["sleep", "5"], timeout=1)

    assert result.success is False
    assert result.stdout == ""


def test_get_uptime_parses_proc_uptime(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (True, "12345.67 89012.34"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_uptime"})

    assert result.success is True
    assert result.data["uptime_seconds"] == 12345.67
    assert result.data["uptime_hours"] == 3.4
    assert result.data["uptime_days"] == 0.1


def test_get_uptime_does_not_fabricate_zero_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_uptime"})

    _assert_collection_failed_without_data(result)


def test_get_boot_time_parses_who_b(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (
            True,
            "         system boot  2024-01-15 10:00",
        ),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_boot_time"})

    assert result.success is True
    assert result.data == {"boot_time": "system boot  2024-01-15 10:00"}


def test_get_boot_time_does_not_fabricate_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_boot_time"})

    _assert_collection_failed_without_data(result)


def test_get_cpu_usage_parses_top_output(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (
            True,
            "%Cpu(s):  5.3 us,  2.1 sy,  0.0 ni, 92.6 id",
        ),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_cpu_usage"})

    assert result.success is True
    assert result.data["user"] == 5.3
    assert result.data["system"] == 2.1
    assert result.data["idle"] == 92.6


def test_get_cpu_usage_does_not_fabricate_zero_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_cpu_usage"})

    _assert_collection_failed_without_data(result)


def test_get_swap_parses_meminfo(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (
            True,
            "SwapTotal:       2097152 kB\nSwapFree:        1048576 kB\n",
        ),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_swap"})

    assert result.success is True
    assert result.data == {
        "total_kb": 2097152,
        "used_kb": 1048576,
        "free_kb": 1048576,
        "usage_percent": 50.0,
        "total_bytes": 2147483648,
        "used_bytes": 1073741824,
        "free_bytes": 1073741824,
    }


def test_get_swap_does_not_fabricate_zero_values_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_swap"})

    _assert_collection_failed_without_data(result)


def test_get_service_checks_specific_service(monkeypatch) -> None:
    def fake_run(command, timeout=15):
        if command == ["systemctl", "is-active", "ssh"]:
            return True, "active"
        if command == ["systemctl", "is-enabled", "ssh"]:
            return True, "enabled"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_service", "name": "ssh"})

    assert result.success is True
    assert result.data == {"name": "ssh", "active": "active", "enabled": "enabled"}


def test_get_service_does_not_fabricate_unknown_status_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_service", "name": "nonexistent"})

    _assert_collection_failed_without_data(result)


def test_get_listening_ports_parses_ss_output(monkeypatch) -> None:
    def fake_ss(command, timeout=15):
        if "ss" in command[0]:
            proto_flag = command[1]
            if "t" in proto_flag:
                return (
                    True,
                    "State  Recv-Q  Send-Q  Local Address:Port   Peer Address:Port  Process\nLISTEN 0       128         0.0.0.0:22         0.0.0.0:*      users:(())\nLISTEN 0       128         0.0.0.0:443        0.0.0.0:*      users:(())\n",
                )
            return (True, "")
        return (False, "")

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: fake_ss(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_listening_ports"})

    assert result.success is True
    ports = result.data["ports"]
    tcp_ports = [p for p in ports if p["protocol"] == "tcp"]
    assert any(p["port"] == "22" for p in tcp_ports)
    assert any(p["port"] == "443" for p in tcp_ports)


def test_get_listening_ports_does_not_fabricate_zero_count_on_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_listening_ports"})

    _assert_collection_failed_without_data(result)
