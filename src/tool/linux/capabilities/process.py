from __future__ import annotations

from collections.abc import Callable


def _get_process(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: running processes. Returns summary + top consumers.
    Full list is omitted to keep prompt size manageable.
    """
    ok, output = run(
        [
            "ps",
            "-eo",
            "pid=,pcpu=,pmem=,args=",
            "--no-headers",
        ]
    )

    processes: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 3)

            if len(parts) < 4:
                continue

            pid, pcpu, pmem, args = parts

            processes.append(
                {
                    "pid": int(pid) if pid.isdigit() else 0,
                    "command": args,
                    "cpu_percent": pcpu,
                    "memory_percent": pmem,
                }
            )

    def _try_float(v: object) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    # Sort by memory descending, take top 5 for summary
    sorted_procs = sorted(
        processes, key=lambda p: _try_float(p.get("memory_percent", 0)), reverse=True
    )
    top_by_mem = sorted_procs[:5]

    # Sort by CPU descending
    sorted_cpu = sorted(
        processes, key=lambda p: _try_float(p.get("cpu_percent", 0)), reverse=True
    )
    top_by_cpu = sorted_cpu[:5]

    # Trim command to 40 chars max
    for p in top_by_cpu + top_by_mem:
        cmd = str(p.get("command", ""))
        if len(cmd) > 40:
            p["command"] = cmd[:40] + "..."

    zombie_count = sum(
        1 for p in processes if "zombie" in str(p.get("command", "")).lower()
    )
    defunct_count = sum(
        1 for p in processes if "defunct" in str(p.get("command", "")).lower()
    )

    return {
        "total": len(processes),
        "summary": f"{len(processes)} running processes",
        "zombie_count": zombie_count + defunct_count,
        "top_cpu": top_by_cpu,
        "top_memory": top_by_mem,
    }


def _get_process_by_name(
    run: Callable[..., tuple[bool, str]], name: str = ""
) -> dict[str, object]:
    return _search_process(run, query=name) if name else _get_process(run)


def _search_process(
    run: Callable[..., tuple[bool, str]], query: str = ""
) -> dict[str, object]:
    """
    Deterministic process search. Filters full command lines inside the Tool.
    """
    if not query:
        return {"error": "Missing query parameter."}
    ok, output = run(["ps", "-eo", "pid,args", "--no-headers"])
    if not ok:
        return {"matches": [], "count": 0, "query": query}
    matches = []
    query_lower = query.lower()
    for line in output.splitlines():
        if query_lower in line.lower():
            parts = line.split(None, 1)
            if parts:
                matches.append(
                    {"pid": parts[0], "command": parts[1] if len(parts) > 1 else ""}
                )
    return {"matches": matches, "count": len(matches), "query": query}
