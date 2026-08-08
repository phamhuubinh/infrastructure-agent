from __future__ import annotations

from .common import CommandRunner


def _get_process(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: running processes. Returns summary + top consumers.
    Full list is omitted to keep prompt size manageable.
    """
    result = run(
        [
            "ps",
            "-eo",
            "pid=,stat=,pcpu=,pmem=,args=",
            "--no-headers",
        ]
    )

    processes: list[dict[str, object]] = []

    if not result.success:
        return {}

    for line in result.stdout.splitlines():
        parts = line.split(None, 4)

        if len(parts) < 5:
            continue

        pid, stat, pcpu, pmem, args = parts
        if not pid.isdigit():
            continue

        processes.append(
            {
                "pid": int(pid),
                "state": stat,
                "command": args,
                "cpu_percent": pcpu,
                "memory_percent": pmem,
            }
        )

    def _try_float(v: object) -> float:
        try:
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                return float(v)
            return float("-inf")
        except (ValueError, TypeError):
            return float("-inf")

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

    # GA2-G03: zombie detection must rely on process state semantics (STAT
    # contains 'Z'), not merely finding 'zombie'/'defunct' in a command line.
    zombie_processes = [
        str(p.get("command", ""))[:80]
        for p in processes
        if "Z" in str(p.get("state", ""))
    ]
    zombie_count = len(zombie_processes)

    return {
        "total": len(processes),
        "summary": f"{len(processes)} running processes",
        "zombie_count": zombie_count,
        "zombie_processes": zombie_processes[:20],
        "top_cpu": top_by_cpu,
        "top_memory": top_by_mem,
    }


def _get_process_by_name(run: CommandRunner, name: str = "") -> dict[str, object]:
    return _search_process(run, query=name) if name else _get_process(run)


def _search_process(run: CommandRunner, query: str = "") -> dict[str, object]:
    """
    Deterministic process search. Filters full command lines inside the Tool.
    """
    if not query:
        return {"error": "Missing query parameter."}
    result = run(["ps", "-eo", "pid,args", "--no-headers"])
    if not result.success:
        return {}
    matches = []
    query_lower = query.lower()
    for line in result.stdout.splitlines():
        if query_lower in line.lower():
            parts = line.split(None, 1)
            if parts:
                matches.append(
                    {"pid": parts[0], "command": parts[1] if len(parts) > 1 else ""}
                )
    return {"matches": matches, "count": len(matches), "query": query}
