from __future__ import annotations

import json

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.capability_result import CapabilityResult, CapabilityStatus

from .common import CommandRunner


def _smartctl_json_output(attempt: CommandResult) -> str | None:
    """Return trustworthy smartctl JSON, including health-bit exits.

    smartctl uses an exit-code bitmask: bits 3-7 describe disk health and may
    accompany a complete JSON document, while bits 0-2 mean invocation,
    device-open, or command failures. Legacy tuple backends cannot expose the
    bitmask and require status-aware handling.
    """

    if attempt.status in {CommandStatus.SUCCESS, CommandStatus.EMPTY_SUCCESS}:
        return attempt.stdout or None
    exit_code = attempt.exit_code
    if (
        attempt.status is CommandStatus.NON_ZERO_EXIT
        and exit_code is not None
        and exit_code & 0x07 == 0
        and attempt.stdout
    ):
        return attempt.stdout
    return None


def _get_disk(run: CommandRunner, path: str | None = None) -> dict[str, object]:
    """
    Subsystem: mounted filesystem usage (size/used/available per mount).
    """
    command = [
        "df",
        "-B1",
        "--output=source,fstype,size,used,avail,pcent,target",
    ]
    if path:
        command.extend(["--", path])
    result = run(command)

    disks: list[dict[str, object]] = []

    if not result.success:
        return {}

    lines = result.stdout.splitlines()[1:]

    for line in lines:
        parts = line.split(None, 6)

        if len(parts) < 7:
            continue

        source, fstype, size, used, avail, pcent, target = parts
        if not all(value.isdigit() for value in (size, used, avail)):
            continue

        usage_percent = float(pcent.strip("%")) if pcent.strip("%").isdigit() else None
        item: dict[str, object] = {
            "source": source,
            "fstype": fstype,
            "size_bytes": int(size),
            "used_bytes": int(used),
            "available_bytes": int(avail),
            "mountpoint": target,
            # Compatibility fields for existing API clients.
            "use_percent": pcent,
            "target": target,
        }
        if usage_percent is not None:
            item["usage_percent"] = usage_percent
        disks.append(item)

    high_usage = [
        d
        for d in disks
        if str(d.get("use_percent", "0%")).strip("%").isdigit()
        and int(str(d["use_percent"]).strip("%")) > 80
    ]
    return {
        "disks": disks,
        "filesystems": disks,
        "disk_count": len(disks),
        "high_usage_count": len(high_usage),
        "fact_type": "filesystem.capacity",
        "collection_strategy": "df",
    }


def _get_filesystem(run: CommandRunner, path: str | None = None) -> dict[str, object]:
    """
    Subsystem: mounted filesystems (device, mountpoint, type).
    """
    mounts_result = run(["cat", "/proc/mounts"])

    mounts: list[dict[str, object]] = []

    if not mounts_result.success:
        return {}

    for line in mounts_result.stdout.splitlines():
        parts = line.split()

        if len(parts) < 3:
            continue

        mounts.append(
            {
                "device": parts[0],
                "mountpoint": parts[1],
                "fstype": parts[2],
            }
        )

    if path:
        matches = [
            item
            for item in mounts
            if path == item["mountpoint"]
            or path.startswith(str(item["mountpoint"]).rstrip("/") + "/")
        ]
        if matches:
            longest = max(matches, key=lambda item: len(str(item["mountpoint"])))
            mounts = [longest]
    result: dict[str, object] = {"mounts": mounts}
    if path is not None:
        result["requested_path"] = path
    return result


def _get_block_device(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: block devices (disks, partitions).
    """
    result = run(
        [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE",
        ]
    )

    devices: list[object] = []

    if not result.success:
        return {}
    try:
        data = json.loads(result.stdout)
        devices = data.get("blockdevices", [])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}

    return {"devices": devices}


def _get_disk_usage(run: CommandRunner, path: str | None = None) -> dict[str, object]:
    return _get_disk(run, path=path)


def _get_filesystem_inode(run: CommandRunner) -> dict[str, object]:
    result = run(
        ["df", "-iP", "--output=source,fstype,itotal,iused,iavail,ipcent,target"]
    )
    if not result.success:
        return {}
    filesystems: list[dict[str, object]] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split(None, 6)
        if len(parts) < 7:
            continue
        source, fstype, total, used, available, percent, mountpoint = parts
        if not all(value.isdigit() for value in (total, used, available)):
            continue
        percentage = percent.strip("%")
        if not percentage.isdigit():
            continue
        filesystems.append(
            {
                "source": source,
                "fstype": fstype,
                "inode_total": int(total),
                "inode_used": int(used),
                "inode_available": int(available),
                "inode_usage_percent": float(percentage),
                "mountpoint": mountpoint,
            }
        )
    return {
        "filesystems": filesystems,
        "filesystem_count": len(filesystems),
        "fact_type": "filesystem.inode",
        "collection_strategy": "df_inode",
    }


def _get_disk_io(run: CommandRunner) -> dict[str, object]:
    result = run(["cat", "/proc/diskstats"])
    if not result.success:
        return {}
    devices: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            devices.append(
                {
                    "major": int(parts[0]),
                    "minor": int(parts[1]),
                    "device": parts[2],
                    "reads_completed": int(parts[3]),
                    "read_bytes": int(parts[5]) * 512,
                    "read_time_seconds": int(parts[6]) / 1000.0,
                    "writes_completed": int(parts[7]),
                    "written_bytes": int(parts[9]) * 512,
                    "write_time_seconds": int(parts[10]) / 1000.0,
                    "io_in_progress": int(parts[11]),
                    "io_time_seconds": int(parts[12]) / 1000.0,
                }
            )
        except ValueError:
            continue
    return {
        "devices": devices,
        "device_count": len(devices),
        "fact_type": "disk.io",
        "counter_semantics": "cumulative_since_boot",
        "collection_strategy": "proc_diskstats",
    }


def _get_disk_device_health(
    run: CommandRunner,
) -> dict[str, object] | CapabilityResult:
    scan_result = run(["smartctl", "--scan-open"])
    if scan_result.success:
        devices: list[dict[str, object]] = []
        paths = [
            line.split()[0]
            for line in scan_result.stdout.splitlines()
            if line.strip().startswith("/dev/")
        ][:8]
        for path in paths:
            health_attempt = run(["smartctl", "-H", "-j", path])
            health_output = _smartctl_json_output(health_attempt)
            if health_output is None:
                devices.append(
                    {
                        "device": path,
                        "health_status": "not_collected",
                    }
                )
                continue
            try:
                parsed = json.loads(health_output)
            except json.JSONDecodeError:
                devices.append(
                    {"device": path, "health_status": "parse_failed"}
                )
                continue
            passed = parsed.get("smart_status", {}).get("passed")
            devices.append(
                {
                    "device": path,
                    "health_status": (
                        "passed" if passed is True else "failed" if passed is False else "unknown"
                    ),
                }
            )
        if not devices:
            return CapabilityResult(
                status=CapabilityStatus.VALID_EMPTY,
                data={
                    "devices": [],
                    "fact_type": "disk.device_health",
                    "collection_strategy": "smartctl",
                },
                warnings=("smartctl found no supported devices.",),
            )
        if any(item["health_status"] in {"not_collected", "parse_failed"} for item in devices):
            return CapabilityResult(
                status=CapabilityStatus.PARTIAL,
                data={
                    "devices": devices,
                    "fact_type": "disk.device_health",
                    "collection_strategy": "smartctl",
                },
                error="Health was not collected for every discovered device.",
            )
        # A smartctl health bit may make the command exit non-zero while its
        # JSON is complete. Declare that semantic outcome explicitly so the
        # generic command-failure adapter does not discard valid health facts.
        return CapabilityResult(
            status=CapabilityStatus.VALID,
            data={
                "devices": devices,
                "fact_type": "disk.device_health",
                "collection_strategy": "smartctl",
            },
        )

    nvme_result = run(["nvme", "list", "-o", "json"])
    if nvme_result.success:
        try:
            parsed = json.loads(nvme_result.stdout)
            paths = [
                str(item.get("DevicePath"))
                for item in parsed.get("Devices", [])
                if isinstance(item, dict) and item.get("DevicePath")
            ][:8]
        except (json.JSONDecodeError, AttributeError):
            return CapabilityResult(
                status=CapabilityStatus.PARSE_FAILED,
                error="nvme list output could not be parsed.",
            )
        devices = []
        for path in paths:
            health_result = run(["nvme", "smart-log", "-o", "json", path])
            if not health_result.success:
                devices.append({"device": path, "health_status": "not_collected"})
                continue
            try:
                health = json.loads(health_result.stdout)
                critical = int(health.get("critical_warning", 0))
            except (json.JSONDecodeError, TypeError, ValueError):
                devices.append({"device": path, "health_status": "parse_failed"})
                continue
            devices.append(
                {
                    "device": path,
                    "health_status": "passed" if critical == 0 else "warning",
                    "critical_warning": critical,
                }
            )
        return {
            "devices": devices,
            "fact_type": "disk.device_health",
            "collection_strategy": "nvme_cli",
        }

    return CapabilityResult(
        status=CapabilityStatus.UNSUPPORTED,
        error="Disk device health requires smartmontools or nvme-cli.",
    )


def _get_filesystem_health(run: CommandRunner) -> dict[str, object]:
    result = run(["cat", "/proc/mounts"])
    mounts: list[dict[str, object]] = []
    if not result.success:
        return {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            mounts.append(
                {
                    "device": parts[0],
                    "mountpoint": parts[1],
                    "fstype": parts[2],
                    "options": parts[3] if len(parts) > 3 else "",
                }
            )
    ro_mounts = [
        m
        for m in mounts
        if "ro" in str(m.get("options", "")).split(",")
        and str(m.get("fstype", "")) not in ("proc", "sysfs", "tmpfs")
    ]
    return {
        "mounts": mounts,
        "total_mounts": len(mounts),
        "read_only_mounts": len(ro_mounts),
        "fact_type": "filesystem.mount_state",
        "health_scope": "mount_flags_only",
    }
