from __future__ import annotations

import time
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
        result["logical_cores"] = threads

    if cores_ok and cores_output.isdigit():
        result["cores"] = int(cores_output)
        result["logical_cores"] = int(cores_output)

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
                    "load_1min": float(parts[0]),
                    "load_5min": float(parts[1]),
                    "load_15min": float(parts[2]),
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


def _parse_proc_stat_cpu(output: str) -> tuple[int, ...] | None:
    first = output.splitlines()[0].split() if output.splitlines() else []
    if not first or first[0] != "cpu" or len(first) < 5:
        return None
    try:
        values = tuple(int(value) for value in first[1:11])
    except ValueError:
        return None
    return values if len(values) >= 4 else None


def _cpu_distribution(
    before: tuple[int, ...], after: tuple[int, ...]
) -> dict[str, object]:
    width = min(len(before), len(after), 8)
    deltas = [max(after[index] - before[index], 0) for index in range(width)]
    total = sum(deltas)
    if total <= 0:
        return {}
    labels = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
    percentages = {
        label: round(deltas[index] * 100.0 / total, 2)
        for index, label in enumerate(labels[:width])
    }
    idle = percentages.get("idle")
    if idle is None:
        return {}
    iowait = percentages.get("iowait", 0.0)
    result: dict[str, object] = {
        f"{name}_percent": value for name, value in percentages.items()
    }
    result["usage_percent"] = round(max(0.0, 100.0 - idle - iowait), 2)
    result["sample_interval_seconds"] = 0.05
    result["collection_strategy"] = "proc_stat_delta"
    # Compatibility fields remain available to old API clients.  New pipeline
    # consumers use the explicit *_percent schema exclusively.
    result.update(percentages)
    return result


def _parse_top_cpu(output: str) -> dict[str, object]:
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
            if "idle" not in result:
                return {}
            result.update(
                {
                    f"{key}_percent": value
                    for key, value in tuple(result.items())
                    if isinstance(value, (int, float))
                }
            )
            idle_value = result["idle"]
            iowait_value = result.get("iowait", 0.0)
            if not isinstance(idle_value, (int, float)) or not isinstance(
                iowait_value, (int, float)
            ):
                return {}
            idle = float(idle_value)
            iowait = float(iowait_value)
            result["usage_percent"] = round(max(0.0, 100.0 - idle - iowait), 2)
            result["collection_strategy"] = "top_fallback"
            return result
    return {}


def _get_cpu_usage(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    first_ok, first_output = run(["cat", "/proc/stat"])
    first = _parse_proc_stat_cpu(first_output) if first_ok else None
    if first is not None:
        time.sleep(0.05)
        second_ok, second_output = run(["cat", "/proc/stat"])
        second = _parse_proc_stat_cpu(second_output) if second_ok else None
        if second is not None:
            distribution = _cpu_distribution(first, second)
            if distribution:
                return distribution

    # ``top`` remains a bounded compatibility fallback for kernels where
    # procfs cannot be sampled. LANG/LC_ALL are fixed by the execution backend.
    ok, output = run(["top", "-bn1"])
    if not ok:
        return {}
    return _parse_top_cpu(output)


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
