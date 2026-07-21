from __future__ import annotations

from collections.abc import Callable

from .common import _parse_colon_output


def _get_user(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: local user accounts (from /etc/passwd).
    """
    ok, output = run(["cat", "/etc/passwd"])

    users: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split(":")

            if len(parts) < 7:
                continue

            name, _, uid, gid, _comment, home, shell = parts[:7]

            users.append(
                {
                    "name": name,
                    "uid": uid,
                    "gid": gid,
                    "home": home,
                    "shell": shell,
                }
            )

    return {"users": users}


def _get_hardware(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: system hardware identity (vendor, product, serial).
    """
    manufacturer_ok, manufacturer = run(["dmidecode", "-s", "system-manufacturer"])
    product_ok, product = run(["dmidecode", "-s", "system-product-name"])
    serial_ok, serial = run(["dmidecode", "-s", "system-serial-number"])

    return {
        "manufacturer": manufacturer if manufacturer_ok else "unknown",
        "product": product if product_ok else "unknown",
        "serial": serial if serial_ok else "unknown",
    }


def _get_pci(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: PCI devices.
    """
    ok, output = run(["lspci"])

    devices: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 1)

            if len(parts) < 2:
                continue

            address, description = parts
            devices.append({"address": address, "description": description})

    return {"devices": devices}


def _get_usb(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: USB devices.
    """
    ok, output = run(["lsusb"])

    devices: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split()

            if len(parts) < 6 or parts[0] != "Bus" or parts[2] != "Device":
                continue

            bus = parts[1]
            device = parts[3].rstrip(":")
            device_id = parts[5]
            description = " ".join(parts[6:])

            devices.append(
                {
                    "bus": bus,
                    "device": device,
                    "id": device_id,
                    "description": description,
                }
            )

    return {"devices": devices}


def _get_gpu(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: GPU/display controllers (filtered from PCI devices).
    """
    ok, output = run(["lspci"])

    gpus: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            lowered = line.lower()

            is_gpu = (
                "vga compatible controller" in lowered
                or "3d controller" in lowered
                or "display controller" in lowered
            )

            if not is_gpu:
                continue

            parts = line.split(None, 1)

            if len(parts) < 2:
                continue

            address, description = parts
            gpus.append({"address": address, "description": description})

    return {"gpus": gpus}


def _get_journal(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: recent systemd journal entries.
    """
    ok, output = run(
        [
            "journalctl",
            "-n",
            "50",
            "--no-pager",
            "-o",
            "short",
        ]
    )

    entries = output.splitlines() if ok else []

    return {"entries": entries}


def _get_log(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: recent system log lines (syslog or messages, whichever exists).
    """
    for path in ("/var/log/syslog", "/var/log/messages"):
        ok, output = run(["tail", "-n", "50", path])

        if ok:
            return {"source": path, "lines": output.splitlines()}

    return {"source": "unknown", "lines": []}


def _get_time(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: system time and timezone configuration.
    """
    ok, output = run(["timedatectl"])

    fields = _parse_colon_output(output) if ok else {}

    return {
        "local_time": fields.get("Local time", "unknown"),
        "time_zone": fields.get("Time zone", "unknown"),
        "ntp_synchronized": fields.get("System clock synchronized", "unknown"),
    }


def _get_locale(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: locale configuration.
    """
    ok, output = run(["locale"])

    fields: dict[str, str] = {}

    if ok:
        for line in output.splitlines():
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

    return {"locale": fields}


def _get_environment(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: environment variable names.

    Only variable names are returned, never values, since values commonly
    carry secrets (tokens, passwords, connection strings).
    """
    ok, output = run(["env"])

    names: list[str] = []

    if ok:
        for line in output.splitlines():
            if "=" not in line:
                continue

            key, _, _value = line.partition("=")
            names.append(key)

    return {"variables": sorted(names)}


def _get_session(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: currently logged in sessions.
    """
    ok, output = run(["who"])

    sessions: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split()

            if len(parts) < 2:
                continue

            sessions.append(
                {
                    "user": parts[0],
                    "terminal": parts[1],
                }
            )

    return {"sessions": sessions}


def _get_module(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: loaded kernel modules.
    """
    ok, output = run(["lsmod"])

    modules: list[dict[str, object]] = []

    if ok:
        lines = output.splitlines()[1:]

        for line in lines:
            parts = line.split(None, 2)

            if len(parts) < 2:
                continue

            modules.append({"name": parts[0], "size": parts[1]})

    return {"modules": modules}


def _get_recent_logins(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["last", "-5"])
    if not ok:
        return {"logins": []}
    logins: list[dict[str, object]] = []
    for line in output.splitlines():
        if not line.strip() or "wtmp" in line or "reboot" in line:
            continue
        parts = line.split()
        if len(parts) >= 5:
            logins.append(
                {
                    "user": parts[0],
                    "terminal": parts[1],
                    "from": parts[2] if parts[2] != ":" else "",
                    "time": " ".join(parts[3:7]) if len(parts) >= 7 else "",
                }
            )
    return {"logins": logins, "total_logins": len(logins)}


def _get_time_sync(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["timedatectl"])
    fields = _parse_colon_output(output) if ok else {}
    return {
        "ntp_synchronized": fields.get("System clock synchronized", "unknown"),
        "ntp_service": fields.get("NTP service", "unknown"),
        "time_zone": fields.get("Time zone", "unknown"),
    }
