from __future__ import annotations

from collections.abc import Callable


def _get_package(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: installed packages summary (count only — use search_package for detail).
    """
    ok, output = run(
        [
            "dpkg-query",
            "-W",
            "-f=${Package} ${Version}\n",
        ]
    )

    if ok:
        lines = [ln for ln in output.splitlines() if ln.strip()]
        return {
            "package_count": len(lines),
            "summary": f"{len(lines)} packages installed",
        }

    ok, output = run(
        [
            "rpm",
            "-qa",
            "--qf",
            "%{NAME} %{VERSION}\n",
        ]
    )

    if ok:
        lines = [ln for ln in output.splitlines() if ln.strip()]
        return {
            "package_count": len(lines),
            "summary": f"{len(lines)} packages installed",
        }

    return {"package_count": 0, "summary": "unable to query packages"}


def _search_package(
    run: Callable[..., tuple[bool, str]], query: str = ""
) -> dict[str, object]:
    """
    Deterministic package search. Filters package list inside the Tool.
    Returns only matching packages — no thousands of raw entries.
    """
    if not query:
        return {"error": "Missing query parameter."}
    ok, output = run(["dpkg-query", "-W", "-f=${Package} ${Version}\n"])
    if ok:
        matches = []
        query_lower = query.lower()
        for line in output.splitlines():
            if query_lower in line.lower():
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    matches.append({"name": parts[0], "version": parts[1]})
        return {"matches": matches, "count": len(matches), "query": query}

    ok, output = run(["rpm", "-qa", "--qf", "%{NAME} %{VERSION}\n"])
    if ok:
        matches = []
        query_lower = query.lower()
        for line in output.splitlines():
            if query_lower in line.lower():
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    matches.append({"name": parts[0], "version": parts[1]})
        return {"matches": matches, "count": len(matches), "query": query}

    return {"matches": [], "count": 0, "query": query}
