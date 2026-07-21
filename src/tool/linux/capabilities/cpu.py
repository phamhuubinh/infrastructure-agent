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

    model = "unknown"
    threads = 0

    if cpuinfo_ok:
        for line in cpuinfo_output.splitlines():
            if line.lower().startswith("model name"):
                _, _, value = line.partition(":")
                model = value.strip()
            elif line.lower().startswith("processor"):
                threads += 1

    cores = int(cores_output) if cores_ok and cores_output.isdigit() else 0

    # Runtime metrics: CPU usage breakdown + load
    usage_data = _get_cpu_usage(run)
    load_ok, load_output = run(["cat", "/proc/loadavg"])
    load = None
    if load_ok:
        parts = load_output.split()
        if len(parts) >= 3:
            load = {
                "1min": float(parts[0])
                if parts[0].replace(".", "", 1).isdigit()
                else 0,
                "5min": float(parts[1])
                if parts[1].replace(".", "", 1).isdigit()
                else 0,
                "15min": float(parts[2])
                if parts[2].replace(".", "", 1).isdigit()
                else 0,
            }

    return {
        "model": model,
        "cores": cores,
        "threads": threads,
        "usage": usage_data,
        "load": load,
    }


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
    return {"raw": "unknown", "user": 0, "system": 0, "idle": 0}


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
