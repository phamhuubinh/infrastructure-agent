from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool


def _run(
    command: list[str],
    timeout: int = 5,
) -> tuple[bool, str]:
    """
    Execute one local command and return (success, stdout).

    This is the single execution boundary for the Linux Tool. Every
    capability below reaches the OS only through this function. Adding
    SSH or container execution later means changing only this function --
    no capability logic needs to change.
    """
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""

    if completed.returncode != 0:
        return False, ""

    return True, completed.stdout.strip()


def _read_os_release() -> dict[str, str]:
    ok, output = _run(["cat", "/etc/os-release"])

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

    ok, output = _run(["lsb_release", "-a"])

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


def _get_system() -> dict[str, object]:
    """
    Subsystem: machine identity (distro, hostname, kernel).
    """
    os_info = _read_os_release()

    hostname_ok, hostname = _run(["hostname"])
    kernel_ok, kernel = _run(["uname", "-r"])

    return {
        "os": os_info,
        "hostname": hostname if hostname_ok else "unknown",
        "kernel": kernel if kernel_ok else "unknown",
    }


def _get_network() -> dict[str, object]:
    """
    Subsystem: networking (interfaces, addresses, routes).
    """
    interfaces: list[dict[str, object]] = []

    ok, output = _run(["ip", "-o", "addr", "show"])

    if ok:
        for line in output.splitlines():
            parts = line.split()

            if len(parts) < 4:
                continue

            interfaces.append(
                {
                    "name": parts[1],
                    "family": parts[2],
                    "address": parts[3],
                }
            )

    routes: list[str] = []

    ok, output = _run(["ip", "route"])

    if ok:
        routes = [line.strip() for line in output.splitlines() if line.strip()]

    return {
        "interfaces": interfaces,
        "routes": routes,
    }


def _get_services() -> dict[str, object]:
    """
    Subsystem: systemd services.
    """
    ok, output = _run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--no-legend",
            "--no-pager",
        ]
    )

    services: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 4)

            if len(parts) < 4:
                continue

            services.append(
                {
                    "name": parts[0],
                    "load": parts[1],
                    "active": parts[2],
                    "sub": parts[3],
                }
            )

    return {"services": services}


def _get_docker() -> dict[str, object]:
    """
    Subsystem: Docker engine presence on this host (not the Docker API).
    """
    ok, output = _run(["docker", "--version"])

    if not ok:
        return {"installed": False, "version": None}

    return {"installed": True, "version": output}


def _get_cpu() -> dict[str, object]:
    """
    Subsystem: CPU identity and core count.
    """
    cores_ok, cores_output = _run(["nproc"])
    cpuinfo_ok, cpuinfo_output = _run(["cat", "/proc/cpuinfo"])

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


def _get_memory() -> dict[str, object]:
    """
    Subsystem: system memory (from /proc/meminfo, values in kB).
    """
    ok, output = _run(["cat", "/proc/meminfo"])

    fields: dict[str, str] = {}

    if ok:
        for line in output.splitlines():
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            value_parts = value.strip().split()
            fields[key.strip()] = value_parts[0] if value_parts else "0"

    def to_int(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    return {
        "total_kb": to_int(fields.get("MemTotal", "0")),
        "free_kb": to_int(fields.get("MemFree", "0")),
        "available_kb": to_int(fields.get("MemAvailable", "0")),
    }


def _get_disk() -> dict[str, object]:
    """
    Subsystem: mounted filesystem usage (size/used/available per mount).
    """
    ok, output = _run(
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

    return {"disks": disks}


def _get_filesystem() -> dict[str, object]:
    """
    Subsystem: mounted filesystems (device, mountpoint, type).
    """
    ok, output = _run(["cat", "/proc/mounts"])

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


def _get_dns() -> dict[str, object]:
    """
    Subsystem: DNS resolver configuration.
    """
    ok, output = _run(["cat", "/etc/resolv.conf"])

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


def _get_process() -> dict[str, object]:
    """
    Subsystem: running processes.
    """
    ok, output = _run(
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


def _get_user() -> dict[str, object]:
    """
    Subsystem: local user accounts (from /etc/passwd).
    """
    ok, output = _run(["cat", "/etc/passwd"])

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


def _get_package() -> dict[str, object]:
    """
    Subsystem: installed packages (dpkg on Debian/Ubuntu, rpm fallback).
    """
    packages: list[dict[str, object]] = []

    ok, output = _run(
        [
            "dpkg-query",
            "-W",
            "-f=${Package} ${Version}\n",
        ]
    )

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 1)

            if len(parts) < 2:
                continue

            name, version = parts
            packages.append({"name": name, "version": version})

        return {"packages": packages}

    ok, output = _run(
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

            if len(parts) < 2:
                continue

            name, version = parts
            packages.append({"name": name, "version": version})

    return {"packages": packages}


def _get_ssh() -> dict[str, object]:
    """
    Subsystem: SSH server configuration summary (no keys, no secrets).
    """
    port = "unknown"
    permit_root_login = "unknown"
    password_authentication = "unknown"

    ok, output = _run(["cat", "/etc/ssh/sshd_config"])

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
        ok, status_output = _run(["systemctl", "is-active", service_name])

        if ok:
            active = status_output.strip()
            break

    return {
        "port": port,
        "permit_root_login": permit_root_login,
        "password_authentication": password_authentication,
        "active": active,
    }


def _get_hardware() -> dict[str, object]:
    """
    Subsystem: system hardware identity (vendor, product, serial).
    """
    manufacturer_ok, manufacturer = _run(["dmidecode", "-s", "system-manufacturer"])
    product_ok, product = _run(["dmidecode", "-s", "system-product-name"])
    serial_ok, serial = _run(["dmidecode", "-s", "system-serial-number"])

    return {
        "manufacturer": manufacturer if manufacturer_ok else "unknown",
        "product": product if product_ok else "unknown",
        "serial": serial if serial_ok else "unknown",
    }


def _get_pci() -> dict[str, object]:
    """
    Subsystem: PCI devices.
    """
    ok, output = _run(["lspci"])

    devices: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 1)

            if len(parts) < 2:
                continue

            address, description = parts
            devices.append({"address": address, "description": description})

    return {"devices": devices}


def _get_usb() -> dict[str, object]:
    """
    Subsystem: USB devices.
    """
    ok, output = _run(["lsusb"])

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


def _get_gpu() -> dict[str, object]:
    """
    Subsystem: GPU/display controllers (filtered from PCI devices).
    """
    ok, output = _run(["lspci"])

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


def _get_block_device() -> dict[str, object]:
    """
    Subsystem: block devices (disks, partitions).
    """
    ok, output = _run(
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


def _get_secureboot() -> dict[str, object]:
    """
    Subsystem: Secure Boot state.
    """
    ok, output = _run(["mokutil", "--sb-state"])

    return {"state": output if ok else "unknown"}


def _get_apparmor() -> dict[str, object]:
    """
    Subsystem: AppArmor enabled state.
    """
    ok, output = _run(["cat", "/sys/module/apparmor/parameters/enabled"])

    return {"enabled": output.strip() if ok else "unknown"}


def _get_selinux() -> dict[str, object]:
    """
    Subsystem: SELinux enforcement mode.
    """
    ok, output = _run(["getenforce"])

    return {"status": output if ok else "unknown"}


def _get_firewall() -> dict[str, object]:
    """
    Subsystem: firewall status (ufw preferred, iptables fallback).
    """
    ok, output = _run(["ufw", "status"])

    if ok:
        return {"backend": "ufw", "status": output}

    ok, output = _run(["iptables", "-L", "-n"])

    if ok:
        return {"backend": "iptables", "status": output}

    return {"backend": "unknown", "status": "unknown"}


def _get_certificate() -> dict[str, object]:
    """
    Subsystem: installed CA certificate filenames (not their content).
    """
    ok, output = _run(["ls", "/etc/ssl/certs"])

    certificates = [line for line in output.splitlines() if line.strip()] if ok else []

    return {"certificates": certificates}


def _get_journal() -> dict[str, object]:
    """
    Subsystem: recent systemd journal entries.
    """
    ok, output = _run(
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


def _get_log() -> dict[str, object]:
    """
    Subsystem: recent system log lines (syslog or messages, whichever exists).
    """
    for path in ("/var/log/syslog", "/var/log/messages"):
        ok, output = _run(["tail", "-n", "50", path])

        if ok:
            return {"source": path, "lines": output.splitlines()}

    return {"source": "unknown", "lines": []}


def _get_time() -> dict[str, object]:
    """
    Subsystem: system time and timezone configuration.
    """
    ok, output = _run(["timedatectl"])

    fields: dict[str, str] = {}

    if ok:
        for line in output.splitlines():
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()

    return {
        "local_time": fields.get("Local time", "unknown"),
        "time_zone": fields.get("Time zone", "unknown"),
        "ntp_synchronized": fields.get("System clock synchronized", "unknown"),
    }


def _get_locale() -> dict[str, object]:
    """
    Subsystem: locale configuration.
    """
    ok, output = _run(["locale"])

    fields: dict[str, str] = {}

    if ok:
        for line in output.splitlines():
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

    return {"locale": fields}


def _get_environment() -> dict[str, object]:
    """
    Subsystem: environment variable names.

    Only variable names are returned, never values, since values commonly
    carry secrets (tokens, passwords, connection strings).
    """
    ok, output = _run(["env"])

    names: list[str] = []

    if ok:
        for line in output.splitlines():
            if "=" not in line:
                continue

            key, _, _value = line.partition("=")
            names.append(key)

    return {"variables": sorted(names)}


def _get_session() -> dict[str, object]:
    """
    Subsystem: currently logged in sessions.
    """
    ok, output = _run(["who"])

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
                    "raw": line,
                }
            )

    return {"sessions": sessions}


def _get_module() -> dict[str, object]:
    """
    Subsystem: loaded kernel modules.
    """
    ok, output = _run(["lsmod"])

    modules: list[dict[str, object]] = []

    if ok:
        lines = output.splitlines()[1:]

        for line in lines:
            parts = line.split(None, 2)

            if len(parts) < 2:
                continue

            modules.append({"name": parts[0], "size": parts[1]})

    return {"modules": modules}


def _get_lxd() -> dict[str, object]:
    """
    Subsystem: LXD presence and containers, read directly from the LXD CLI.
    """
    ok, version = _run(["lxd", "--version"])

    if not ok:
        return {"installed": False, "version": None, "containers": []}

    containers: list[object] = []

    ok, output = _run(["lxc", "list", "--format", "json"])

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


_CAPABILITIES: dict[str, Callable[[], dict[str, object]]] = {
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

        return ToolResult(
            success=True,
            data=handler(),
        )
