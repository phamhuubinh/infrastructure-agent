from __future__ import annotations

from .common import CommandRunner


def _get_package(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: installed packages summary (count only — use search_package for detail).
    """
    result = run(
        [
            "dpkg-query",
            "-W",
            "-f=${Package} ${Version}\n",
        ]
    )

    if result.success:
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return {
            "package_count": len(lines),
            "summary": f"{len(lines)} packages installed",
        }

    result = run(
        [
            "rpm",
            "-qa",
            "--qf",
            "%{NAME} %{VERSION}\n",
        ]
    )

    if result.success:
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return {
            "package_count": len(lines),
            "summary": f"{len(lines)} packages installed",
        }

    return {"package_count": 0, "summary": "unable to query packages"}


def _search_package(
    run: CommandRunner, query: str = ""
) -> dict[str, object]:
    """
    Deterministic package search. Filters package list inside the Tool.
    Returns only matching packages — no thousands of raw entries.
    """
    if not query:
        return {"error": "Missing query parameter."}
    result = run(["dpkg-query", "-W", "-f=${Package} ${Version}\n"])
    if result.success:
        matches = []
        query_lower = query.lower()
        for line in result.stdout.splitlines():
            if query_lower in line.lower():
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    matches.append({"name": parts[0], "version": parts[1]})
        return {"matches": matches, "count": len(matches), "query": query}

    result = run(["rpm", "-qa", "--qf", "%{NAME} %{VERSION}\n"])
    if result.success:
        matches = []
        query_lower = query.lower()
        for line in result.stdout.splitlines():
            if query_lower in line.lower():
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    matches.append({"name": parts[0], "version": parts[1]})
        return {"matches": matches, "count": len(matches), "query": query}

    return {"matches": [], "count": 0, "query": query}
