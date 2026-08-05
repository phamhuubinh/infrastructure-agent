from __future__ import annotations

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.capability_result import CapabilityStatus
from src.tool.linux import LinuxTool


def test_capacity_is_a_filesystem_fact_not_device_health() -> None:
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: (
        True,
        "source fstype size used avail pcent target\n"
        "/dev/sda1 ext4 1000 370 630 37% /",
    )

    result = tool.execute({"action": "get_disk"})

    assert result.success is True
    assert result.data["fact_type"] == "filesystem.capacity"
    assert result.data["filesystems"][0]["usage_percent"] == 37.0
    assert "health" not in result.data


def test_inode_capacity_has_separate_schema() -> None:
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: (
        True,
        "source fstype itotal iused iavail ipcent target\n"
        "/dev/sda1 ext4 100 25 75 25% /",
    )

    result = tool.execute({"action": "get_filesystem_inode"})

    assert result.success is True
    assert result.data["fact_type"] == "filesystem.inode"
    assert result.data["filesystems"][0]["inode_usage_percent"] == 25.0


def test_diskstats_are_cumulative_io_not_health() -> None:
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: (
        True,
        "8 0 sda 10 0 20 30 40 0 50 60 0 70 80",
    )

    result = tool.execute({"action": "get_disk_io"})

    assert result.success is True
    assert result.data["fact_type"] == "disk.io"
    assert result.data["counter_semantics"] == "cumulative_since_boot"
    assert result.data["devices"][0]["read_bytes"] == 20 * 512


def test_missing_smart_tools_is_unsupported_not_healthy() -> None:
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: (False, "")

    result = tool.execute({"action": "get_disk_device_health"})

    assert result.capability_status is CapabilityStatus.UNSUPPORTED
    assert result.data is None
    assert "requires" in (result.error or "")


def test_smartctl_health_bit_exit_keeps_valid_json_health_fact() -> None:
    responses = iter(
        [
            CommandResult(
                status=CommandStatus.SUCCESS,
                stdout="/dev/sda -d scsi # /dev/sda",
            ),
            CommandResult(
                status=CommandStatus.NON_ZERO_EXIT,
                exit_code=8,
                stdout='{"smart_status":{"passed":false}}',
            ),
        ]
    )
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: next(responses)

    result = tool.execute({"action": "get_disk_device_health"})

    assert result.success is True
    assert result.data["devices"] == [
        {"device": "/dev/sda", "health_status": "failed"}
    ]


def test_smartctl_invocation_error_is_not_treated_as_health_fact() -> None:
    responses = iter(
        [
            CommandResult(
                status=CommandStatus.SUCCESS,
                stdout="/dev/sda -d scsi # /dev/sda",
            ),
            CommandResult(
                status=CommandStatus.NON_ZERO_EXIT,
                exit_code=2,
                stdout='{"smart_status":{"passed":false}}',
            ),
        ]
    )
    tool = LinuxTool()
    tool._run = lambda command, timeout=15: next(responses)

    result = tool.execute({"action": "get_disk_device_health"})

    assert result.capability_status is CapabilityStatus.PARTIAL
    assert result.data["devices"][0]["health_status"] == "not_collected"
