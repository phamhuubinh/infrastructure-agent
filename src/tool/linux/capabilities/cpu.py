from __future__ import annotations

from collections.abc import Callable

from .common import _read_os_release


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


def _get_cpu(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: CPU identity, core count, and runtime metrics.
    """
    cores_ok, cores_output = run(["nproc"])
    cpuinfo_ok, cpuinfo_output = run(["cat", "/proc/cpuinfo"])

    result: dict[str, object] = {}

    if cpuinfo_ok:
        threads = 0
        for line in cpuinfo_output.splitlines():
            if line.lower().startswith("model name"):
                _, _, value = line.partition(":")
                if value.strip():
                    result["model"] = value.strip()
            elif line.lower().startswith("processor"):
                threads += 1
        result["threads"] = threads

    if cores_ok and cores_output.isdigit():
        result["cores"] = int(cores_output)

    # Runtime metrics: CPU usage breakdown + load
    usage_data = _get_cpu_usage(run)
    if usage_data:
        result["usage"] = usage_data
    load_ok, load_output = run(["cat", "/proc/loadavg"])
    load = None
    if load_ok:
        parts = load_output.split()
        if len(parts) >= 3:
            try:
                load = {
                    "1min": float(parts[0]),
                    "5min": float(parts[1]),
                    "15min": float(parts[2]),
                }
            except ValueError:
                load = None
    if load is not None:
        result["load"] = load

    return result


def _get_uptime(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/uptime"])
    if ok and output:
        parts = output.split()
        try:
            uptime_seconds = float(parts[0])
        except (IndexError, ValueError):
            return {}
        return {
            "uptime_seconds": uptime_seconds,
            "uptime_hours": round(uptime_seconds / 3600, 1),
            "uptime_days": round(uptime_seconds / 86400, 1),
        }
    return {}


def _get_boot_time(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["who", "-b"])
    if ok and output:
        return {"boot_time": output.strip()}
    return {}


def _get_cpu_usage(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["top", "-bn1"])
    if ok:
        for line in output.splitlines():
            if "Cpu(s)" in line or "%Cpu(s)" in line:
                parts = line.replace(",", " ").split()
                result: dict[str, object] = {}
                for i, p in enumerate(parts):
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
    return {}


def _get_system_load(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/loadavg"])
    if ok:
        parts = output.split()
        if len(parts) >= 3:
            try:
                return {
                    "load_1min": float(parts[0]),
                    "load_5min": float(parts[1]),
                    "load_15min": float(parts[2]),
                    "raw": output.strip(),
                }
            except ValueError:
                pass
    return {}
