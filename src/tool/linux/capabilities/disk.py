from __future__ import annotations

import json
from collections.abc import Callable


def _get_disk(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: mounted filesystem usage (size/used/available per mount).
    """
    ok, output = run(
        [
            "df",
            "-B1",
            "--output=source,fstype,size,used,avail,pcent,target",
        ]
    )

    disks: list[dict[str, object]] = []

    if ok:
        lines = output.splitlines()[1:]

        for line in lines:
            parts = line.split(None, 6)

            if len(parts) < 7:
                continue

            source, fstype, size, used, avail, pcent, target = parts

            disks.append(
                {
                    "source": source,
                    "fstype": fstype,
                    "size_bytes": int(size) if size.isdigit() else 0,
                    "used_bytes": int(used) if used.isdigit() else 0,
                    "available_bytes": int(avail) if avail.isdigit() else 0,
                    "use_percent": pcent,
                    "target": target,
                }
            )

    high_usage = [
        d
        for d in disks
        if d.get("use_percent", "0%").strip("%").isdigit()
        and int(d["use_percent"].strip("%")) > 80
    ]
    return {
        "disks": disks,
        "disk_count": len(disks),
        "high_usage_count": len(high_usage),
    }


def _get_filesystem(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: mounted filesystems (device, mountpoint, type).
    """
    ok, output = run(["cat", "/proc/mounts"])

    mounts: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
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

    return {"mounts": mounts}


def _get_block_device(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: block devices (disks, partitions).
    """
    ok, output = run(
        [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE",
        ]
    )

    devices: list[object] = []

    if ok:
        try:
            data = json.loads(output)
            devices = data.get("blockdevices", [])
        except (json.JSONDecodeError, AttributeError, TypeError):
            devices = []

    return {"devices": devices}


def _get_disk_usage(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    return _get_disk(run)


def _get_filesystem_health(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/mounts"])
    mounts: list[dict[str, object]] = []
    if ok:
        for line in output.splitlines():
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
        if "ro" in m.get("options", "")
        and m.get("fstype") not in ("proc", "sysfs", "tmpfs")
    ]
    return {
        "mounts": mounts,
        "total_mounts": len(mounts),
        "read_only_mounts": len(ro_mounts),
    }
