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

    Also collects swap and top memory consumers inline so the assessment
    always has this data without requiring separate capability calls.
    """
    ok, output = run(["cat", "/proc/meminfo"])

    raw = _parse_colon_output(output) if ok else {}

    total = _to_int(raw.get("MemTotal", "0"))
    available = _to_int(raw.get("MemAvailable", "0"))
    free = _to_int(raw.get("MemFree", "0"))
    usage_percent = round((1 - available / total) * 100, 1) if total > 0 else 0

    used = total - available if total > available else 0

    # Collect swap info from /proc/meminfo (always available, same file).
    swap_total = _to_int(raw.get("SwapTotal", "0"))
    swap_free = _to_int(raw.get("SwapFree", "0"))
    swap_used = swap_total - swap_free
    swap_usage_percent = (
        round((swap_used / swap_total) * 100, 1) if swap_total > 0 else 0
    )

    # Collect top memory consumers via ps.
    top_consumers: list[dict[str, object]] = []
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

    result: dict[str, object] = {
        "total_kb": total,
        "used_kb": used,
        "free_kb": free,
        "available_kb": available,
        "usage_percent": usage_percent,
        "swap_total_kb": swap_total,
        "swap_used_kb": swap_used,
        "swap_free_kb": swap_free,
        "swap_usage_percent": swap_usage_percent,
        "top_consumers": top_consumers,
    }

    # Strip empty/none values for cleaner serialization.
    if swap_total == 0:
        del result["swap_total_kb"]
        del result["swap_used_kb"]
        del result["swap_free_kb"]
        del result["swap_usage_percent"]

    return result


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
