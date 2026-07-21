from __future__ import annotations

from collections.abc import Callable

from .common import _parse_colon_output


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
        return {
            "total_kb": total,
            "used_kb": used,
            "free_kb": free,
            "usage_percent": usage_percent,
        }
    return {"total_kb": 0, "used_kb": 0, "free_kb": 0, "usage_percent": 0}
