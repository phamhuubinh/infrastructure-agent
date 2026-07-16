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


def test_get_system_returns_unknown_when_all_sources_fail(monkeypatch) -> None:
    def fake_run(command, timeout=5):
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


def test_get_network_returns_empty_lists_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_network"})

    assert result.success is True
    assert result.data == {"interfaces": [], "routes": [], "interface_count": 0, "active_interfaces": 0}


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


def test_get_services_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_services"})

    assert result.success is True
    assert result.data == {"total": 0, "running": 0, "exited": 0, "failed": 0, "failed_services": []}


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


def test_get_docker_reports_not_installed(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_docker"})

    assert result.success is True
    assert result.data["installed"] is False
    assert result.data["container_count"] == 0


def test_execute_reports_unknown_action_includes_new_capabilities() -> None:
    tool = LinuxTool()

    result = tool.execute({"action": "get_disk_temperature"})

    assert result.success is False
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
    assert "usage" in result.data
    assert "load" in result.data


def test_get_cpu_returns_defaults_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_cpu"})

    assert result.success is True
    assert result.data["model"] == "unknown"
    assert result.data["cores"] == 0
    assert "threads" in result.data
    assert "usage" in result.data
    assert "load" in result.data


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
    }


def test_get_memory_returns_zeros_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_memory"})

    assert result.success is True
    assert result.data == {"total_kb": 0, "used_kb": 0, "free_kb": 0, "available_kb": 0, "usage_percent": 0}


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


def test_get_disk_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_disk"})

    assert result.success is True
    assert result.data == {"disks": [], "disk_count": 0, "high_usage_count": 0}


def test_get_filesystem_parses_proc_mounts(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/proc/mounts"]:
            return True, (
                "/dev/sda1 / ext4 rw,relatime 0 0\n"
                "tmpfs /tmp tmpfs rw,nosuid 0 0\n"
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


def test_get_filesystem_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_filesystem"})

    assert result.success is True
    assert result.data == {"mounts": []}


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


def test_get_dns_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_dns"})

    assert result.success is True
    assert result.data == {"nameservers": []}


def test_get_process_parses_ps_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command[0] == "ps":
            return True, "1 0.0 0.1 /sbin/init\n42 0.1 0.2 /usr/sbin/sshd\n"
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


def test_get_process_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_process"})

    assert result.success is True
    assert result.data["total"] == 0
    assert result.data["top_memory"] == []
    assert result.data["top_cpu"] == []
    assert "summary" in result.data
    assert "zombie_count" in result.data


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
            {"name": "root", "uid": "0", "gid": "0", "home": "/root", "shell": "/bin/bash"},
            {
                "name": "alice",
                "uid": "1000",
                "gid": "1000",
                "home": "/home/alice",
                "shell": "/bin/bash",
            },
        ]
    }


def test_get_user_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_user"})

    assert result.success is True
    assert result.data == {"users": []}


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


def test_get_package_returns_empty_count_when_no_package_manager(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_package"})

    assert result.success is True
    assert result.data["package_count"] == 0


def test_get_ssh_parses_sshd_config(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["cat", "/etc/ssh/sshd_config"]:
            return True, "Port 2222\nPermitRootLogin no\nPasswordAuthentication yes\n"
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
    assert result.data == {
        "port": "2222",
        "permit_root_login": "no",
        "password_authentication": "yes",
        "active": "active",
    }


def test_get_ssh_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_ssh"})

    assert result.success is True
    assert result.data == {
        "port": "unknown",
        "permit_root_login": "unknown",
        "password_authentication": "unknown",
        "active": "unknown",
    }


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


def test_get_hardware_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_hardware"})

    assert result.success is True
    assert result.data == {
        "manufacturer": "unknown",
        "product": "unknown",
        "serial": "unknown",
    }


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


def test_get_pci_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_pci"})

    assert result.success is True
    assert result.data == {"devices": []}


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


def test_get_usb_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_usb"})

    assert result.success is True
    assert result.data == {"devices": []}


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


def test_get_gpu_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_gpu"})

    assert result.success is True
    assert result.data == {"gpus": []}


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


def test_get_block_device_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_block_device"})

    assert result.success is True
    assert result.data == {"devices": []}


def test_get_block_device_returns_empty_list_on_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (True, "not json"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_block_device"})

    assert result.success is True
    assert result.data == {"devices": []}


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


def test_get_secureboot_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_secureboot"})

    assert result.success is True
    assert result.data == {"enabled": "unknown"}


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


def test_get_apparmor_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_apparmor"})

    assert result.success is True
    assert result.data == {"enabled": "unknown"}


def test_get_selinux_reports_status(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (True, "Enforcing"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_selinux"})

    assert result.success is True
    assert result.data == {"status": "Enforcing"}


def test_get_selinux_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_selinux"})

    assert result.success is True
    assert result.data == {"status": "unknown"}


def test_get_firewall_prefers_ufw_active(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ufw", "status"]:
            return True, "Status: active"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data == {"backend": "ufw", "active": True}


def test_get_firewall_prefers_ufw_inactive(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ufw", "status"]:
            return True, "Status: inactive"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data == {"backend": "ufw", "active": False}


def test_get_firewall_falls_back_to_iptables(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["ufw", "status"]:
            return False, ""
        if command == ["iptables", "-L", "-n"]:
            return True, "Chain INPUT (policy ACCEPT)"
        return False, ""

    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: fake_run(command, timeout),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data == {"backend": "iptables", "active": True}


def test_get_firewall_returns_unknown_when_no_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_firewall"})

    assert result.success is True
    assert result.data == {"backend": "unknown", "active": None}


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


def test_get_certificate_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_certificate"})

    assert result.success is True
    assert result.data == {"certificates": []}


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


def test_get_journal_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_journal"})

    assert result.success is True
    assert result.data == {"entries": []}


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
    assert result.data == {"source": "/var/log/syslog", "lines": ["line one", "line two"]}


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


def test_get_log_returns_unknown_when_no_log_file(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_log"})

    assert result.success is True
    assert result.data == {"source": "unknown", "lines": []}


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


def test_get_time_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_time"})

    assert result.success is True
    assert result.data == {
        "local_time": "unknown",
        "time_zone": "unknown",
        "ntp_synchronized": "unknown",
    }


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
    assert result.data == {
        "locale": {"LANG": "en_US.UTF-8", "LC_TIME": "en_US.UTF-8"}
    }


def test_get_locale_returns_empty_dict_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_locale"})

    assert result.success is True
    assert result.data == {"locale": {}}


def test_get_environment_returns_names_not_values(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["env"]:
            return True, "PATH=/usr/bin\nSECRET_TOKEN=super-secret-value\n"
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
    assert "super-secret-value" not in str(result.data)


def test_get_environment_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_environment"})

    assert result.success is True
    assert result.data == {"variables": []}


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


def test_get_session_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_session"})

    assert result.success is True
    assert result.data == {"sessions": []}


def test_get_module_parses_lsmod_output(monkeypatch) -> None:
    def fake_run(command, timeout=5):
        if command == ["lsmod"]:
            return True, "Module                  Size  Used by\nnf_tables              200000  1\n"
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


def test_get_module_returns_empty_list_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_module"})

    assert result.success is True
    assert result.data == {"modules": []}


def test_get_lxd_reports_not_installed(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=5: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_lxd"})

    assert result.success is True
    assert result.data == {"installed": False, "version": None, "containers": []}


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
    from src.tool.execution_backend import LocalExecutionBackend, SSHExecutionBackend

    captured: list[tuple[list[str], int]] = []

    def fake_subprocess_run(*, command=None, **kwargs):
        captured.append((command, 0))
        class Fake:
            returncode = 0
            stdout = "mocked output"
        return Fake()

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        lambda *args, **kwargs: fake_subprocess_run(command=args[0] if args else kwargs.get("command")),
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
    ok, output = backend.run(["uname", "-r"])

    assert ok is False
    assert "SSH authentication failed" in output


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
    ok, output = backend.run(["uname", "-r"])

    assert ok is False
    assert "permission denied" in output


def test_ssh_backend_returns_false_on_os_error(monkeypatch) -> None:
    from src.tool.execution_backend import SSHExecutionBackend

    def fake_os_error(popenargs, **kwargs):
        raise OSError("ssh not found")

    monkeypatch.setattr(
        "src.tool.execution_backend.subprocess.run",
        fake_os_error,
    )

    backend = SSHExecutionBackend(host="10.0.0.1")
    ok, output = backend.run(["uname", "-r"])

    assert ok is False
    assert output == ""


def test_local_backend_returns_false_on_missing_binary() -> None:
    from src.tool.execution_backend import LocalExecutionBackend

    backend = LocalExecutionBackend()
    ok, output = backend.run(["this_binary_does_not_exist_xyz"])

    assert ok is False
    assert output == ""


def test_local_backend_returns_false_on_timeout() -> None:
    from src.tool.execution_backend import LocalExecutionBackend

    backend = LocalExecutionBackend()
    ok, output = backend.run(["sleep", "5"], timeout=0.01)

    assert ok is False
    assert output == ""


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


def test_get_uptime_returns_zero_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_uptime"})

    assert result.success is True
    assert result.data == {"uptime_seconds": 0, "uptime_hours": 0, "uptime_days": 0}


def test_get_boot_time_parses_who_b(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (True, "         system boot  2024-01-15 10:00"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_boot_time"})

    assert result.success is True
    assert result.data == {"boot_time": "system boot  2024-01-15 10:00"}


def test_get_boot_time_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_boot_time"})

    assert result.success is True
    assert result.data == {"boot_time": "unknown"}


def test_get_cpu_usage_parses_top_output(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (True, "%Cpu(s):  5.3 us,  2.1 sy,  0.0 ni, 92.6 id"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_cpu_usage"})

    assert result.success is True
    assert result.data["user"] == 5.3
    assert result.data["system"] == 2.1
    assert result.data["idle"] == 92.6


def test_get_cpu_usage_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_cpu_usage"})

    assert result.success is True
    assert result.data == {"raw": "unknown", "user": 0, "system": 0, "idle": 0}


def test_get_swap_parses_meminfo(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (True, "SwapTotal:       2097152 kB\nSwapFree:        1048576 kB\n"),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_swap"})

    assert result.success is True
    assert result.data == {"total_kb": 2097152, "used_kb": 1048576, "free_kb": 1048576, "usage_percent": 50.0}


def test_get_swap_returns_zeros_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_swap"})

    assert result.success is True
    assert result.data == {"total_kb": 0, "used_kb": 0, "free_kb": 0, "usage_percent": 0}


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


def test_get_service_returns_unknown_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_service", "name": "nonexistent"})

    assert result.success is True
    assert result.data == {"name": "nonexistent", "active": "unknown", "enabled": "unknown"}


def test_get_listening_ports_parses_ss_output(monkeypatch) -> None:
    def fake_ss(command, timeout=15):
        if "ss" in command[0]:
            proto_flag = command[1]
            if "t" in proto_flag:
                return (True, "State  Recv-Q  Send-Q  Local Address:Port   Peer Address:Port  Process\nLISTEN 0       128         0.0.0.0:22         0.0.0.0:*      users:(())\nLISTEN 0       128         0.0.0.0:443        0.0.0.0:*      users:(())\n")
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


def test_get_listening_ports_returns_empty_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        LinuxTool,
        "_run",
        lambda self, command, timeout=15: (False, ""),
    )

    tool = LinuxTool()
    result = tool.execute({"action": "get_listening_ports"})

    assert result.success is True
    assert result.data["port_count"] == 0
    assert result.data["ports"] == []
