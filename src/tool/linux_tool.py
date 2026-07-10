from __future__ import annotations

import json
from collections.abc import Callable

from src.shared.execution.tool_result import ToolResult
from src.tool.execution_backend import ExecutionBackend, LocalExecutionBackend
from src.tool.tool import Tool


def _parse_colon_output(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _read_os_release(run: Callable[..., tuple[bool, str]]) -> dict[str, str]:
    ok, output = run(["cat", "/etc/os-release"])

    if ok:
        fields: dict[str, str] = {}

        for line in output.splitlines():
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

        return {
            "name": fields.get("NAME", "unknown"),
            "version": fields.get("VERSION_ID", "unknown"),
            "id": fields.get("ID", "unknown"),
        }

    ok, output = run(["lsb_release", "-a"])

    if ok:
        fields = {}

        for line in output.splitlines():
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()

        return {
            "name": fields.get("Distributor ID", "unknown"),
            "version": fields.get("Release", "unknown"),
            "id": "unknown",
        }

    return {
        "name": "unknown",
        "version": "unknown",
        "id": "unknown",
    }


def _get_system(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: machine identity (distro, hostname, kernel).
    """
    os_info = _read_os_release(run)

    hostname_ok, hostname = run(["hostname"])
    kernel_ok, kernel = run(["uname", "-r"])

    return {
        "os": os_info,
        "hostname": hostname if hostname_ok else "unknown",
        "kernel": kernel if kernel_ok else "unknown",
    }


def _get_network(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: networking (interfaces, addresses, routes).
    """
    interfaces: list[dict[str, object]] = []
    interface_names: set[str] = set()

    ok, output = run(["ip", "-o", "addr", "show"])

    if ok:
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            ifname = parts[1]
            interface_names.add(ifname)
            interfaces.append(
                {
                    "name": ifname,
                    "family": parts[2],
                    "address": parts[3],
                }
            )

    routes: list[str] = []
    ok, output = run(["ip", "route"])
    if ok:
        routes = [line.strip() for line in output.splitlines() if line.strip()]

    ok2, link_output = run(["ip", "-o", "link", "show"])
    active_interfaces = 0
    if ok2:
        for line in link_output.splitlines():
            if "state UP" in line or "state UNKNOWN" in line:
                ifname2 = line.split(":")[1].strip() if ":" in line else ""
                if ifname2:
                    active_interfaces += 1

    return {
        "interfaces": interfaces,
        "interface_count": len(interface_names),
        "active_interfaces": active_interfaces,
        "routes": routes,
    }


def _get_services(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: systemd services.
    """
    ok, output = run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--no-legend",
            "--no-pager",
        ]
    )

    services: list[dict[str, object]] = []
    running = 0
    exited = 0
    failed = 0

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 4)

            if len(parts) < 4:
                continue

            service = {
                "name": parts[0],
                "load": parts[1],
                "active": parts[2],
                "sub": parts[3],
            }
            services.append(service)
            if parts[2] == "active" and parts[3] == "running":
                running += 1
            elif parts[3] == "exited":
                exited += 1
            elif parts[3] == "failed":
                failed += 1

    return {
        "services": services,
        "total": len(services),
        "running": running,
        "exited": exited,
        "failed": failed,
    }


def _get_docker(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: Docker engine presence on this host (not the Docker API).
    """
    ok, output = run(["docker", "--version"])

    if not ok:
        return {"installed": False, "version": None}

    return {"installed": True, "version": output}


def _get_cpu(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: CPU identity and core count.
    """
    cores_ok, cores_output = run(["nproc"])
    cpuinfo_ok, cpuinfo_output = run(["cat", "/proc/cpuinfo"])

    model = "unknown"

    if cpuinfo_ok:
        for line in cpuinfo_output.splitlines():
            if line.lower().startswith("model name"):
                _, _, value = line.partition(":")
                model = value.strip()
                break

    cores = int(cores_output) if cores_ok and cores_output.isdigit() else 0

    return {
        "model": model,
        "cores": cores,
    }


def _to_int(value: str) -> int:
    try:
        return int(value.split()[0]) if value.split() else 0
    except ValueError:
        return 0


def _get_memory(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: system memory (from /proc/meminfo, values in kB).
    """
    ok, output = run(["cat", "/proc/meminfo"])

    raw = _parse_colon_output(output) if ok else {}

    total = _to_int(raw.get("MemTotal", "0"))
    available = _to_int(raw.get("MemAvailable", "0"))
    free = _to_int(raw.get("MemFree", "0"))
    usage_percent = round((1 - available / total) * 100, 1) if total > 0 else 0

    used = total - available if total > available else 0
    return {
        "total_kb": total,
        "used_kb": used,
        "free_kb": free,
        "available_kb": available,
        "usage_percent": usage_percent,
    }


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

    high_usage = [d for d in disks if d.get("use_percent", "0%").strip("%").isdigit() and int(d["use_percent"].strip("%")) > 80]
    return {"disks": disks, "disk_count": len(disks), "high_usage_count": len(high_usage)}


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


def _get_dns(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: DNS resolver configuration.
    """
    ok, output = run(["cat", "/etc/resolv.conf"])

    nameservers: list[str] = []

    if ok:
        for line in output.splitlines():
            line = line.strip()

            if not line.startswith("nameserver"):
                continue

            parts = line.split()

            if len(parts) >= 2:
                nameservers.append(parts[1])

    return {"nameservers": nameservers}


def _get_process(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: running processes.
    """
    ok, output = run(
        [
            "ps",
            "-eo",
            "pid,comm,pcpu,pmem",
            "--no-headers",
        ]
    )

    processes: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 3)

            if len(parts) < 4:
                continue

            pid, comm, pcpu, pmem = parts

            processes.append(
                {
                    "pid": int(pid) if pid.isdigit() else 0,
                    "command": comm,
                    "cpu_percent": pcpu,
                    "memory_percent": pmem,
                }
            )

    return {"processes": processes}


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


def _get_package(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: installed packages (dpkg on Debian/Ubuntu, rpm fallback).
    """
    packages: list[dict[str, object]] = []

    ok, output = run(
        [
            "dpkg-query",
            "-W",
            "-f=${Package} ${Version}\n",
        ]
    )

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 1)
            if len(parts) >= 2:
                packages.append({"name": parts[0], "version": parts[1]})
        return {"packages": packages, "package_count": len(packages)}

    ok, output = run(
        [
            "rpm",
            "-qa",
            "--qf",
            "%{NAME} %{VERSION}\n",
        ]
    )

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 1)
            if len(parts) >= 2:
                packages.append({"name": parts[0], "version": parts[1]})

    return {"packages": packages, "package_count": len(packages)}


def _get_ssh(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: SSH server configuration summary (no keys, no secrets).
    """
    port = "unknown"
    permit_root_login = "unknown"
    password_authentication = "unknown"

    ok, output = run(["cat", "/etc/ssh/sshd_config"])

    if ok:
        for line in output.splitlines():
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split(None, 1)

            if len(parts) < 2:
                continue

            key, value = parts[0].lower(), parts[1].strip()

            if key == "port":
                port = value
            elif key == "permitrootlogin":
                permit_root_login = value
            elif key == "passwordauthentication":
                password_authentication = value

    active = "unknown"

    for service_name in ("ssh", "sshd"):
        ok, status_output = run(["systemctl", "is-active", service_name])

        if ok:
            active = status_output.strip()
            break

    return {
        "port": port,
        "permit_root_login": permit_root_login,
        "password_authentication": password_authentication,
        "active": active,
    }


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


def _get_secureboot(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: Secure Boot state.
    """
    ok, output = run(["mokutil", "--sb-state"])

    if not ok:
        return {"enabled": "unknown"}
    return {"enabled": "enabled" in output.lower()}


def _get_apparmor(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: AppArmor enabled state.
    """
    ok, output = run(["cat", "/sys/module/apparmor/parameters/enabled"])

    if not ok:
        return {"enabled": "unknown"}
    return {"enabled": output.strip() == "Y"}


def _get_selinux(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: SELinux enforcement mode.
    """
    ok, output = run(["getenforce"])

    return {"status": output if ok else "unknown"}


def _get_firewall(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: firewall status (ufw preferred, iptables fallback).
    """
    ok, output = run(["ufw", "status"])

    if ok:
        words = output.lower().split()
        active = "active" in words
        return {"backend": "ufw", "active": active}

    ok, output = run(["iptables", "-L", "-n"])

    if ok:
        return {"backend": "iptables", "active": True}

    return {"backend": "unknown", "active": None}


def _get_certificate(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: installed CA certificate filenames (not their content).
    """
    ok, output = run(["ls", "/etc/ssl/certs"])

    certificates = [line for line in output.splitlines() if line.strip()] if ok else []

    return {"certificates": certificates}


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


def _get_uptime(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/uptime"])
    if ok and output:
        parts = output.split()
        uptime_seconds = float(parts[0]) if parts else 0
        return {
            "uptime_seconds": uptime_seconds,
            "uptime_hours": round(uptime_seconds / 3600, 1),
            "uptime_days": round(uptime_seconds / 86400, 1),
        }
    return {"uptime_seconds": 0, "uptime_hours": 0, "uptime_days": 0}


def _get_boot_time(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["who", "-b"])
    if ok and output:
        return {"boot_time": output.strip()}
    return {"boot_time": "unknown"}


def _get_cpu_usage(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["top", "-bn1"])
    if ok:
        for line in output.splitlines():
            if "Cpu(s)" in line or "%Cpu(s)" in line:
                parts = line.replace(",", " ").split()
                result: dict[str, object] = {"raw": line.strip()}
                for i, p in enumerate(parts):
                    p_clean = p.strip("%")
                    if p == "us," or p == "us":
                        result["user"] = float(parts[i - 1]) if i > 0 else 0
                    elif p == "sy," or p == "sy":
                        result["system"] = float(parts[i - 1]) if i > 0 else 0
                    elif p == "ni," or p == "ni":
                        result["nice"] = float(parts[i - 1]) if i > 0 else 0
                    elif p == "id," or p == "id":
                        result["idle"] = float(parts[i - 1]) if i > 0 else 0
                    elif p == "wa," or p == "wa":
                        result["iowait"] = float(parts[i - 1]) if i > 0 else 0
                    elif p == "hi," or p == "hi":
                        result["irq"] = float(parts[i - 1]) if i > 0 else 0
                    elif p == "si," or p == "si":
                        result["softirq"] = float(parts[i - 1]) if i > 0 else 0
                    elif p == "st," or p == "st":
                        result["steal"] = float(parts[i - 1]) if i > 0 else 0
                return result
    return {"raw": "unknown", "user": 0, "system": 0, "idle": 0}


def _get_swap(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/meminfo"])
    if ok:
        total = 0
        free = 0
        for line in output.splitlines():
            if line.startswith("SwapTotal:"):
                parts = line.split()
                total = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            elif line.startswith("SwapFree:"):
                parts = line.split()
                free = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        used = total - free
        usage_percent = round((used / total) * 100, 1) if total > 0 else 0
        return {"total_kb": total, "used_kb": used, "free_kb": free, "usage_percent": usage_percent}
    return {"total_kb": 0, "used_kb": 0, "free_kb": 0, "usage_percent": 0}


def _get_service(run: Callable[..., tuple[bool, str]], name: str = "") -> dict[str, object]:
    if not name:
        return {"error": "Missing service name."}
    ok, output = run(["systemctl", "is-active", name])
    active_status = output.strip() if ok else "unknown"
    ok2, output2 = run(["systemctl", "is-enabled", name])
    enabled_status = output2.strip() if ok2 else "unknown"
    return {
        "name": name,
        "active": active_status,
        "enabled": enabled_status,
    }


def _get_listening_ports(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["ss", "-tlnp"])
    if not ok:
        return {"ports": []}
    ports: list[dict[str, object]] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            addr = parts[3]
            if ":" in addr:
                port_str = addr.rsplit(":", 1)[-1]
                ports.append({"address": addr, "port": port_str, "protocol": "tcp"})
    return {"ports": ports, "port_count": len(ports)}


def _get_disk_usage(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    return _get_disk(run)


def _get_system_load(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/loadavg"])
    if ok:
        parts = output.split()
        return {
            "load_1min": float(parts[0]) if parts else 0,
            "load_5min": float(parts[1]) if len(parts) > 1 else 0,
            "load_15min": float(parts[2]) if len(parts) > 2 else 0,
            "raw": output.strip(),
        }
    return {"load_1min": 0, "load_5min": 0, "load_15min": 0}


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
            logins.append({
                "user": parts[0],
                "terminal": parts[1],
                "from": parts[2] if parts[2] != ":" else "",
                "time": " ".join(parts[3:7]) if len(parts) >= 7 else "",
            })
    return {"logins": logins, "total_logins": len(logins)}


def _get_filesystem_health(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/mounts"])
    mounts: list[dict[str, object]] = []
    if ok:
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                mounts.append({
                    "device": parts[0],
                    "mountpoint": parts[1],
                    "fstype": parts[2],
                    "options": parts[3] if len(parts) > 3 else "",
                })
    ro_mounts = [m for m in mounts if "ro" in m.get("options", "") and m.get("fstype") not in ("proc", "sysfs", "tmpfs")]
    return {"mounts": mounts, "total_mounts": len(mounts), "read_only_mounts": len(ro_mounts)}


def _get_time_sync(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["timedatectl"])
    fields = _parse_colon_output(output) if ok else {}
    return {
        "ntp_synchronized": fields.get("System clock synchronized", "unknown"),
        "ntp_service": fields.get("NTP service", "unknown"),
        "time_zone": fields.get("Time zone", "unknown"),
    }


def _get_process_by_name(run: Callable[..., tuple[bool, str]], name: str = "") -> dict[str, object]:
    if not name:
        return _get_process(run)
    ok, output = run(["pgrep", "-a", name])
    if not ok:
        return {"processes": [], "count": 0, "name": name}
    processes = []
    for line in output.splitlines():
        parts = line.split(None, 1)
        if parts:
            processes.append({"pid": parts[0], "command": parts[1] if len(parts) > 1 else ""})
    return {"processes": processes, "count": len(processes), "name": name}


def _get_lxd(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: LXD presence and containers, read directly from the LXD CLI.
    """
    ok, version = run(["lxd", "--version"])

    if not ok:
        return {"installed": False, "version": None, "containers": []}

    containers: list[object] = []

    ok, output = run(["lxc", "list", "--format", "json"])

    if ok:
        try:
            data = json.loads(output)
            containers = [item.get("name") for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, AttributeError, TypeError):
            containers = []

    return {
        "installed": True,
        "version": version,
        "containers": containers,
    }


_CAPABILITIES: dict[str, Callable[..., dict[str, object]]] = {
    "get_system": _get_system,
    "get_network": _get_network,
    "get_services": _get_services,
    "get_docker": _get_docker,
    "get_cpu": _get_cpu,
    "get_memory": _get_memory,
    "get_disk": _get_disk,
    "get_filesystem": _get_filesystem,
    "get_dns": _get_dns,
    "get_process": _get_process,
    "get_user": _get_user,
    "get_package": _get_package,
    "get_ssh": _get_ssh,
    "get_hardware": _get_hardware,
    "get_pci": _get_pci,
    "get_usb": _get_usb,
    "get_gpu": _get_gpu,
    "get_block_device": _get_block_device,
    "get_secureboot": _get_secureboot,
    "get_apparmor": _get_apparmor,
    "get_selinux": _get_selinux,
    "get_firewall": _get_firewall,
    "get_certificate": _get_certificate,
    "get_journal": _get_journal,
    "get_log": _get_log,
    "get_time": _get_time,
    "get_locale": _get_locale,
    "get_environment": _get_environment,
    "get_session": _get_session,
    "get_module": _get_module,
    "get_lxd": _get_lxd,
    "get_uptime": _get_uptime,
    "get_boot_time": _get_boot_time,
    "get_cpu_usage": _get_cpu_usage,
    "get_swap": _get_swap,
    "get_service": _get_service,
    "get_listening_ports": _get_listening_ports,
    "get_disk_usage": _get_disk_usage,
    "get_system_load": _get_system_load,
    "get_recent_logins": _get_recent_logins,
    "get_filesystem_health": _get_filesystem_health,
    "get_time_sync": _get_time_sync,
    "get_process_by_name": _get_process_by_name,
}


class LinuxTool(Tool):
    """
    Tool con của KnowledgeTool, chịu trách nhiệm cho domain Linux.

    KnowledgeTool gọi execute() với một capability đã đặt tên (vd.
    "get_system"); LinuxTool không biết Agent, không biết Model, và
    không route sang Tool con khác. Một capability có thể chạy nhiều
    command và tự áp dụng fallback logic bên trong nó.

    Nếu capability không tồn tại, execute() trả về ToolResult thất bại
    kèm danh sách capability hợp lệ.

    Để thêm capability: viết một hàm trả về structured data, sau đó
    thêm một entry vào _CAPABILITIES. Không cần sửa gì khác.
    """

    def __init__(
        self,
        backend: ExecutionBackend | None = None,
    ) -> None:
        self._backend = backend or LocalExecutionBackend()

    def _run(
        self,
        command: list[str],
        timeout: int = 15,
    ) -> tuple[bool, str]:
        return self._backend.run(command, timeout=timeout)

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        action = arguments.get("action")

        if not isinstance(action, str):
            raise ValueError("Missing action.")

        handler = _CAPABILITIES.get(action)

        if handler is None:
            available = ", ".join(sorted(_CAPABILITIES))

            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'. Available actions: {available}.",
            )

        extra = {k: v for k, v in arguments.items() if k != "action"}

        if extra:
            data = handler(self._run, **extra)
        else:
            data = handler(self._run)

        return ToolResult(
            success=True,
            data=data,
        )
