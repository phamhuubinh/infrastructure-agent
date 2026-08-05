from __future__ import annotations

from collections.abc import Callable

from .common import _parse_colon_output


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.split()[0]) if value.split() else None
    except ValueError:
        return None


def _get_memory(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: system memory (from /proc/meminfo, values in kB).

    Also collects swap and top memory consumers inline so the assessment
    always has this data without requiring separate capability calls.
    """
    ok, output = run(["cat", "/proc/meminfo"])

    if not ok:
        return {}

    raw = _parse_colon_output(output)

    total = _to_int(raw.get("MemTotal"))
    available = _to_int(raw.get("MemAvailable"))
    free = _to_int(raw.get("MemFree"))

    # Collect swap info from /proc/meminfo (always available, same file).
    swap_total = _to_int(raw.get("SwapTotal"))
    swap_free = _to_int(raw.get("SwapFree"))

    # Collect top memory consumers via ps.
    top_consumers: list[dict[str, object]] = []
    ps_ok = False
    try:
        ps_ok, ps_out = run(
            ["ps", "aux", "--sort=-%mem", "--no-headers"],
            timeout=10,
        )
        if ps_ok and ps_out.strip():
            lines = ps_out.strip().split("\n")[:6]
            for line in lines:
                parts = line.split()
                if len(parts) >= 11:
                    top_consumers.append(
                        {
                            "user": parts[0],
                            "pid": parts[1],
                            "cpu_pct": parts[2],
                            "mem_pct": parts[3],
                            "command": parts[10],
                        }
                    )
    except Exception:
        pass

    result: dict[str, object] = {}
    if total is not None:
        result["total_kb"] = total
        result["total_bytes"] = total * 1024
    if free is not None:
        result["free_kb"] = free
        result["free_bytes"] = free * 1024
    if available is not None:
        result["available_kb"] = available
        result["available_bytes"] = available * 1024
    if total is not None and available is not None and total > 0:
        used = max(total - available, 0)
        result["used_kb"] = used
        result["used_bytes"] = used * 1024
        result["usage_percent"] = round((1 - available / total) * 100, 1)
    if swap_total is not None and swap_free is not None:
        swap_used = max(swap_total - swap_free, 0)
        result["swap_total_kb"] = swap_total
        result["swap_used_kb"] = swap_used
        result["swap_free_kb"] = swap_free
        result["swap_total_bytes"] = swap_total * 1024
        result["swap_used_bytes"] = swap_used * 1024
        result["swap_free_bytes"] = swap_free * 1024
        if swap_total > 0:
            result["swap_usage_percent"] = round(
                (swap_used / swap_total) * 100, 1
            )
    if ps_ok:
        result["top_consumers"] = top_consumers

    return result


def _get_swap(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    ok, output = run(["cat", "/proc/meminfo"])
    if not ok:
        return {}
    raw = _parse_colon_output(output)
    total = _to_int(raw.get("SwapTotal"))
    free = _to_int(raw.get("SwapFree"))
    if total is None or free is None:
        return {}
    used = max(total - free, 0)
    result: dict[str, object] = {
        "total_kb": total,
        "used_kb": used,
        "free_kb": free,
        "total_bytes": total * 1024,
        "used_bytes": used * 1024,
        "free_bytes": free * 1024,
    }
    if total > 0:
        result["usage_percent"] = round((used / total) * 100, 1)
    return result
