from __future__ import annotations

import json
import re
import time

from src.shared.execution.command_result import CommandResult, CommandStatus
from src.tool.capability_result import CapabilityResult, CapabilityStatus

from .common import CommandRunner

_SERVICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$")
_SERVICE_PORTS: dict[str, tuple[int, ...]] = {
    "nginx": (80, 443),
    "apache2": (80, 443),
    "httpd": (80, 443),
    "ssh": (22,),
    "sshd": (22,),
    "postgresql": (5432,),
    "mysql": (3306,),
    "redis": (6379,),
}
_SERVICE_LOG_PATHS: dict[str, tuple[str, ...]] = {
    "nginx": ("/var/log/nginx/error.log", "/var/log/nginx/access.log"),
    "apache2": ("/var/log/apache2/error.log",),
    "httpd": ("/var/log/httpd/error_log",),
    "mysql": ("/var/log/mysql/error.log",),
    "postgresql": ("/var/log/postgresql/postgresql.log",),
    "redis": ("/var/log/redis/redis-server.log",),
}


def _attempt_output(attempt: CommandResult) -> str:
    return (attempt.stdout or attempt.stderr).strip()


def _may_try_alternative(attempt: CommandResult) -> bool:
    return attempt.status in {
        CommandStatus.COMMAND_NOT_FOUND,
        CommandStatus.NON_ZERO_EXIT,
        CommandStatus.UNSUPPORTED_ENVIRONMENT,
        CommandStatus.EMPTY_SUCCESS,
    }


def _collection_failure(message: str) -> CapabilityResult:
    return CapabilityResult(status=CapabilityStatus.COLLECTION_FAILED, error=message)


def _parse_systemd_services(output: str) -> dict[str, object]:
    services: list[dict[str, str]] = []
    running = 0
    exited = 0
    failed = 0
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
        elif parts[2] == "failed" or parts[3] == "failed":
            failed += 1
    return {
        "total": len(services),
        "running": running,
        "exited": exited,
        "failed": failed,
        "failed_services": [s["name"] for s in services if s["active"] == "failed" or s["sub"] == "failed"],
        "services": services,
        "collection_strategy": "systemd",
        "confidence": 1.0,
    }


def _get_services(
    run: CommandRunner,
) -> dict[str, object] | CapabilityResult:
    """
    Subsystem: systemd services summary.
    """
    systemd_attempt = run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--no-legend",
            "--no-pager",
        ]
    )

    if systemd_attempt.success:
        return _parse_systemd_services(systemd_attempt.stdout)
    if not _may_try_alternative(systemd_attempt):
        return _collection_failure("Systemd service collection failed; fallback is unsafe.")

    sysv_attempt = run(["service", "--status-all"])
    if sysv_attempt.success:
        services: list[dict[str, str]] = []
        for line in sysv_attempt.stdout.splitlines():
            match = re.match(r"\s*\[\s*([+?-])\s*\]\s+(.+?)\s*$", line)
            if not match:
                continue
            marker, name = match.groups()
            status = "running" if marker == "+" else "stopped" if marker == "-" else "unknown"
            services.append({"name": name, "status": status})
        data = {
            "total": len(services),
            "running": sum(item["status"] == "running" for item in services),
            "services": services,
            "collection_strategy": "sysv",
            "confidence": 0.85,
        }
        return CapabilityResult(
            status=CapabilityStatus.PARTIAL,
            data=data,
            warnings=("SysV fallback does not expose systemd load/sub states.",),
            error="Service evidence collected through SysV fallback.",
        )
    if not _may_try_alternative(sysv_attempt):
        return _collection_failure("SysV service collection failed; fallback is unsafe.")

    openrc_attempt = run(["rc-status", "--all"])
    if openrc_attempt.success:
        services = []
        for line in openrc_attempt.stdout.splitlines():
            match = re.match(r"\s*(\S+)\s+\[\s*(\S+)\s*\]\s*$", line)
            if match:
                services.append({"name": match.group(1), "status": match.group(2)})
        return CapabilityResult(
            status=CapabilityStatus.PARTIAL,
            data={
                "total": len(services),
                "running": sum(item["status"] == "started" for item in services),
                "services": services,
                "collection_strategy": "openrc",
                "confidence": 0.85,
            },
            warnings=("OpenRC fallback provides alternative service evidence.",),
            error="Service evidence collected through OpenRC fallback.",
        )
    if not _may_try_alternative(openrc_attempt):
        return _collection_failure("OpenRC service collection failed; fallback is unsafe.")

    process_attempt = run(["ps", "-eo", "comm="])
    if process_attempt.success:
        names = sorted(
            {line.strip() for line in process_attempt.stdout.splitlines() if line.strip()}
        )
        return CapabilityResult(
            status=CapabilityStatus.PARTIAL,
            data={
                "processes": names,
                "process_count": len(names),
                "collection_strategy": "process_inventory",
                "confidence": 0.45,
            },
            warnings=("Process presence is not equivalent to service health.",),
            error="Only process-level alternative evidence is available.",
        )
    return _collection_failure("No supported service status strategy succeeded.")


def _search_service(
    run: CommandRunner, query: str = ""
) -> dict[str, object]:
    """
    Deterministic service search. Filters systemd units inside the Tool.
    """
    if not query:
        return {"error": "Missing query parameter."}
    collected = _get_services(run)
    data = collected.data if isinstance(collected, CapabilityResult) else collected
    if not isinstance(data, dict):
        return {}
    entries = data.get("services", data.get("processes", []))
    if not isinstance(entries, list):
        return {}
    query_lower = query.lower()
    matches = [item for item in entries if query_lower in str(item).lower()]
    return {"matches": matches, "count": len(matches), "query": query}


def _get_docker(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: Docker engine presence and running containers.
    """
    version_result = run(["docker", "--version"])

    if not version_result.success:
        return {}

    version = version_result.stdout.strip()
    containers: list[dict[str, object]] = []

    containers_result = run(
        ["docker", "ps", "--format", "{{.ID}} {{.Image}} {{.Names}} {{.Status}}"]
    )
    if containers_result.success:
        for line in containers_result.stdout.splitlines():
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
    run: CommandRunner, name: str = ""
) -> dict[str, object] | CapabilityResult:
    if not isinstance(name, str) or not name or not _SERVICE_NAME.fullmatch(name):
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error="Service name is missing or contains unsafe characters.",
        )

    systemd_attempt = run(["systemctl", "is-active", name])
    systemd_output = _attempt_output(systemd_attempt)
    known_states = {"active", "inactive", "failed", "activating", "deactivating", "unknown"}
    if systemd_attempt.success or systemd_output in known_states:
        result: dict[str, object] = {"name": name, "active": systemd_output}
        enabled_attempt = run(["systemctl", "is-enabled", name])
        enabled_output = _attempt_output(enabled_attempt)
        if enabled_attempt.success or enabled_output in {"enabled", "disabled", "static", "masked", "indirect"}:
            result["enabled"] = enabled_output
        if systemd_attempt.success:
            return result
        # systemctl deliberately exits non-zero for inactive/failed states;
        # that state is valid evidence, not a collection failure.
        return CapabilityResult(status=CapabilityStatus.VALID, data=result)
    if not _may_try_alternative(systemd_attempt):
        return _collection_failure("Systemd status failed; fallback is unsafe.")

    sysv_attempt = run(["service", name, "status"])
    sysv_output = _attempt_output(sysv_attempt)
    if sysv_attempt.success:
        return CapabilityResult(
            status=CapabilityStatus.PARTIAL,
            data={
                "name": name,
                "observed_state": "running" if "running" in sysv_output.lower() else "present",
                "raw_status": sysv_output,
                "collection_strategy": "sysv",
                "confidence": 0.85,
            },
            error="Service evidence collected through SysV fallback.",
        )
    if not _may_try_alternative(sysv_attempt):
        return _collection_failure("SysV status failed; fallback is unsafe.")

    openrc_attempt = run(["rc-service", name, "status"])
    if openrc_attempt.success:
        openrc_output = _attempt_output(openrc_attempt)
        return CapabilityResult(
            status=CapabilityStatus.PARTIAL,
            data={
                "name": name,
                "observed_state": "started" if "started" in openrc_output.lower() else "present",
                "raw_status": openrc_output,
                "collection_strategy": "openrc",
                "confidence": 0.85,
            },
            error="Service evidence collected through OpenRC fallback.",
        )
    if not _may_try_alternative(openrc_attempt):
        return _collection_failure("OpenRC status failed; fallback is unsafe.")

    process_attempt = run(["pgrep", "-x", name])
    if process_attempt.success:
        pids = [
            int(value) for value in process_attempt.stdout.split() if value.isdigit()
        ]
        return CapabilityResult(
            status=CapabilityStatus.PARTIAL,
            data={
                "name": name,
                "process_present": True,
                "pids": pids,
                "collection_strategy": "process_lookup",
                "confidence": 0.5,
                "health": "unknown",
            },
            warnings=("Process presence does not prove that the service is healthy.",),
            error="Only process-presence evidence is available.",
        )
    if not _may_try_alternative(process_attempt):
        return _collection_failure("Process lookup failed; fallback is unsafe.")

    expected_ports = _SERVICE_PORTS.get(name.removesuffix(".service"), ())
    if expected_ports:
        port_attempt = run(["ss", "-ltnup"])
        if port_attempt.success:
            matched = [
                port
                for port in expected_ports
                if f":{port} " in f"{port_attempt.stdout} "
            ]
            if matched:
                return CapabilityResult(
                    status=CapabilityStatus.PARTIAL,
                    data={
                        "name": name,
                        "listening_ports": matched,
                        "collection_strategy": "listening_port",
                        "confidence": 0.3,
                        "health": "unknown",
                    },
                    warnings=("A listening port does not prove service identity or health.",),
                    error="Only listening-port alternative evidence is available.",
                )
    return _collection_failure("No supported service status strategy succeeded.")


def _resolve_log_bounds(
    time_range: str | None, since: int | None, until: int | None
) -> tuple[int | None, int | None]:
    if since is not None or until is not None:
        return since, until
    if not time_range:
        return None, None
    now = int(time.time())
    relative = {"1h": 3600, "6h": 21600, "12h": 43200, "24h": 86400, "1d": 86400, "7d": 604800, "30d": 2592000}
    if time_range in relative:
        return now - relative[time_range], now
    match = re.fullmatch(
        r"(\d+)(h|hours?|giờ|tiếng|d|days?|ngày)", time_range, re.IGNORECASE
    )
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        seconds = amount * (3600 if unit in {"h", "hour", "hours", "giờ", "tiếng"} else 86400)
        if 0 < seconds <= 31 * 86400:
            return now - seconds, now
    if time_range == "today":
        return now - (now % 86400), now
    if time_range == "yesterday":
        today = now - (now % 86400)
        return today - 86400, today - 1
    if time_range in {"this_week", "last_week"}:
        today = now - (now % 86400)
        this_monday = today - time.gmtime(now).tm_wday * 86400
        if time_range == "this_week":
            return this_monday, now
        return this_monday - 7 * 86400, this_monday - 1
    return None, None


def _get_service_logs(
    run: CommandRunner,
    service_name: str = "",
    time_range: str | None = None,
    since: int | None = None,
    until: int | None = None,
    limit: int = 50,
) -> dict[str, object] | CapabilityResult:
    if (
        not isinstance(service_name, str)
        or not service_name
        or not _SERVICE_NAME.fullmatch(service_name)
    ):
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error="service_name is required and must be a valid unit name.",
        )
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error="limit must be an integer between 1 and 500.",
        )
    if time_range is not None and not isinstance(time_range, str):
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error="time_range must be a supported string expression.",
        )
    if since is not None and (
        isinstance(since, bool) or not isinstance(since, int) or since < 0
    ):
        return CapabilityResult(status=CapabilityStatus.INVALID_PARAMETERS, error="since must be a non-negative Unix timestamp.")
    if until is not None and (
        isinstance(until, bool) or not isinstance(until, int) or until < 0
    ):
        return CapabilityResult(status=CapabilityStatus.INVALID_PARAMETERS, error="until must be a non-negative Unix timestamp.")
    if since is not None and until is not None and since > until:
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error="since must be less than or equal to until.",
        )
    since, until = _resolve_log_bounds(time_range, since, until)
    if time_range and since is None and until is None:
        return CapabilityResult(
            status=CapabilityStatus.INVALID_PARAMETERS,
            error=f"Unsupported time range: {time_range}",
        )

    unit = service_name if service_name.endswith(".service") else f"{service_name}.service"
    command = ["journalctl", "-u", unit, "--no-pager", "--output", "short-iso", "-n", str(limit)]
    if since is not None:
        command.extend(["--since", f"@{since}"])
    if until is not None:
        command.extend(["--until", f"@{until}"])
    journal_attempt = run(command)
    if journal_attempt.success:
        return {
            "service_name": service_name,
            "since": since,
            "until": until,
            "limit": limit,
            "entries": [
                line for line in journal_attempt.stdout.splitlines() if line.strip()
            ],
            "collection_strategy": "systemd_journal",
        }
    if not _may_try_alternative(journal_attempt):
        return _collection_failure("Service journal collection failed; fallback is unsafe.")

    # Plain files have no reliable generic timestamp parser.  Do not silently
    # ignore a requested time range.
    if since is not None or until is not None:
        return CapabilityResult(
            status=CapabilityStatus.UNSUPPORTED,
            error="Time-bounded service logs require journalctl on this target.",
        )
    paths = _SERVICE_LOG_PATHS.get(service_name.removesuffix(".service"), ())
    for path in paths:
        file_attempt = run(["tail", "-n", str(limit), path])
        if file_attempt.success:
            return CapabilityResult(
                status=CapabilityStatus.PARTIAL,
                data={
                    "service_name": service_name,
                    "source_path": path,
                    "limit": limit,
                    "entries": [
                        line for line in file_attempt.stdout.splitlines() if line.strip()
                    ],
                    "collection_strategy": "allowlisted_file",
                },
                warnings=("File fallback could not apply a structured time range.",),
                error="Service logs collected from an allowlisted file fallback.",
            )
        if not _may_try_alternative(file_attempt):
            return _collection_failure("Allowlisted service log read failed; fallback is unsafe.")
    return CapabilityResult(
        status=CapabilityStatus.UNSUPPORTED,
        error=f"No supported log source is configured for service '{service_name}'.",
    )


def _get_lxd(run: CommandRunner) -> dict[str, object]:
    """
    Subsystem: LXD presence and containers, read directly from the LXD CLI.
    """
    version_result = run(["lxd", "--version"])

    if not version_result.success:
        return {}

    containers: list[object] = []

    containers_result = run(["lxc", "list", "--format", "json"])

    if containers_result.success:
        try:
            data = json.loads(containers_result.stdout)
            containers = [item.get("name") for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, AttributeError, TypeError):
            containers = []

    return {
        "installed": True,
        "version": version_result.stdout,
        "containers": containers,
    }
