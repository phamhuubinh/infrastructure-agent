from __future__ import annotations

import subprocess
from collections.abc import Callable

from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool


def _run(
    command: list[str],
    timeout: int = 5,
) -> tuple[bool, str]:
    """
    Execute one local command and return (success, stdout).

    This is the single execution boundary for the Linux Tool. Every
    capability below reaches the OS only through this function. Adding
    SSH or container execution later means changing only this function --
    no capability logic needs to change.
    """
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""

    if completed.returncode != 0:
        return False, ""

    return True, completed.stdout.strip()


def _read_os_release() -> dict[str, str]:
    ok, output = _run(["cat", "/etc/os-release"])

    if ok:
        fields: dict[str, str] = {}

        for line in output.splitlines():
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

        return {
            "name": fields.get("NAME", "unknown"),
            "version": fields.get("VERSION_ID", "unknown"),
            "id": fields.get("ID", "unknown"),
        }

    ok, output = _run(["lsb_release", "-a"])

    if ok:
        fields = {}

        for line in output.splitlines():
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()

        return {
            "name": fields.get("Distributor ID", "unknown"),
            "version": fields.get("Release", "unknown"),
            "id": "unknown",
        }

    return {
        "name": "unknown",
        "version": "unknown",
        "id": "unknown",
    }


def _get_system() -> dict[str, object]:
    """
    Subsystem: machine identity (distro, hostname, kernel).
    """
    os_info = _read_os_release()

    hostname_ok, hostname = _run(["hostname"])
    kernel_ok, kernel = _run(["uname", "-r"])

    return {
        "os": os_info,
        "hostname": hostname if hostname_ok else "unknown",
        "kernel": kernel if kernel_ok else "unknown",
    }


def _get_network() -> dict[str, object]:
    """
    Subsystem: networking (interfaces, addresses, routes).
    """
    interfaces: list[dict[str, object]] = []

    ok, output = _run(["ip", "-o", "addr", "show"])

    if ok:
        for line in output.splitlines():
            parts = line.split()

            if len(parts) < 4:
                continue

            interfaces.append(
                {
                    "name": parts[1],
                    "family": parts[2],
                    "address": parts[3],
                }
            )

    routes: list[str] = []

    ok, output = _run(["ip", "route"])

    if ok:
        routes = [line.strip() for line in output.splitlines() if line.strip()]

    return {
        "interfaces": interfaces,
        "routes": routes,
    }


def _get_services() -> dict[str, object]:
    """
    Subsystem: systemd services.
    """
    ok, output = _run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--no-legend",
            "--no-pager",
        ]
    )

    services: list[dict[str, object]] = []

    if ok:
        for line in output.splitlines():
            parts = line.split(None, 4)

            if len(parts) < 4:
                continue

            services.append(
                {
                    "name": parts[0],
                    "load": parts[1],
                    "active": parts[2],
                    "sub": parts[3],
                }
            )

    return {"services": services}


def _get_docker() -> dict[str, object]:
    """
    Subsystem: Docker engine presence on this host (not the Docker API).
    """
    ok, output = _run(["docker", "--version"])

    if not ok:
        return {"installed": False, "version": None}

    return {"installed": True, "version": output}


_CAPABILITIES: dict[str, Callable[[], dict[str, object]]] = {
    "get_system": _get_system,
    "get_network": _get_network,
    "get_services": _get_services,
    "get_docker": _get_docker,
}


class LinuxTool(Tool):
    """
    Tool exposing live, subsystem-level Linux capabilities to the Model.

    The Model requests a named capability (e.g. "get_system"); it never
    sees or chooses shell commands. A capability may run more than one
    command and apply fallback logic internally.

    If the requested capability does not exist, execute() returns a
    failed ToolResult listing the valid capability names, so the Model
    can pick a different one or conclude the task cannot currently be
    completed -- it never falls back to shell commands.

    To add a capability: write one function returning structured data,
    then add one entry to _CAPABILITIES. No other code needs to change.
    """

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        action = arguments.get("action")

        if not isinstance(action, str):
            raise ValueError("Missing action.")

        handler = _CAPABILITIES.get(action)

        if handler is None:
            available = ", ".join(sorted(_CAPABILITIES))

            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'. Available actions: {available}.",
            )

        return ToolResult(
            success=True,
            data=handler(),
        )
