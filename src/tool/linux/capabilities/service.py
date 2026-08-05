from __future__ import annotations

import json
from collections.abc import Callable


def _get_services(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: systemd services summary.
    """
    ok, output = run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--no-legend",
            "--no-pager",
        ]
    )

    services: list[dict[str, str]] = []
    running = 0
    exited = 0
    failed = 0

    if not ok:
        return {}

    for line in output.splitlines():
        parts = line.split(None, 4)

        if len(parts) < 4:
            continue

        service = {
            "name": parts[0],
            "load": parts[1],
            "active": parts[2],
            "sub": parts[3],
            "status": parts[3],
        }
        services.append(service)
        if parts[2] == "active" and parts[3] == "running":
            running += 1
        elif parts[3] == "exited":
            exited += 1
        elif parts[3] == "failed":
            failed += 1

    failed_names = [s["name"] for s in services if s["sub"] == "failed"]

    return {
        "total": len(services),
        "running": running,
        "exited": exited,
        "failed": failed,
        "failed_services": failed_names,
        "services": services,
    }


def _search_service(
    run: Callable[..., tuple[bool, str]], query: str = ""
) -> dict[str, object]:
    """
    Deterministic service search. Filters systemd units inside the Tool.
    """
    if not query:
        return {"error": "Missing query parameter."}
    ok, output = run(
        ["systemctl", "list-units", "--type=service", "--no-legend", "--no-pager"]
    )
    if not ok:
        return {}
    matches = []
    query_lower = query.lower()
    for line in output.splitlines():
        if query_lower in line.lower():
            parts = line.split(None, 4)
            if len(parts) >= 4:
                matches.append(
                    {
                        "name": parts[0],
                        "load": parts[1],
                        "active": parts[2],
                        "sub": parts[3],
                    }
                )
    return {"matches": matches, "count": len(matches), "query": query}


def _get_docker(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: Docker engine presence and running containers.
    """
    ok, output = run(["docker", "--version"])

    if not ok:
        return {}

    version = output.strip()
    containers: list[dict[str, object]] = []

    ok2, output2 = run(
        ["docker", "ps", "--format", "{{.ID}} {{.Image}} {{.Names}} {{.Status}}"]
    )
    if ok2:
        for line in output2.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 3:
                containers.append(
                    {
                        "id": parts[0],
                        "image": parts[1],
                        "name": parts[2],
                        "status": parts[3] if len(parts) > 3 else "",
                    }
                )

    return {
        "installed": True,
        "version": version,
        "containers": containers,
        "container_count": len(containers),
    }


def _get_service(
    run: Callable[..., tuple[bool, str]], name: str = ""
) -> dict[str, object]:
    if not name:
        return {"error": "Missing service name."}
    ok, output = run(["systemctl", "is-active", name])
    ok2, output2 = run(["systemctl", "is-enabled", name])
    result: dict[str, object] = {"name": name}
    if ok and output.strip():
        result["active"] = output.strip()
    if ok2 and output2.strip():
        result["enabled"] = output2.strip()
    return result


def _get_lxd(run: Callable[..., tuple[bool, str]]) -> dict[str, object]:
    """
    Subsystem: LXD presence and containers, read directly from the LXD CLI.
    """
    ok, version = run(["lxd", "--version"])

    if not ok:
        return {}

    containers: list[object] = []

    ok, output = run(["lxc", "list", "--format", "json"])

    if ok:
        try:
            data = json.loads(output)
            containers = [item.get("name") for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, AttributeError, TypeError):
            containers = []

    return {
        "installed": True,
        "version": version,
        "containers": containers,
    }
