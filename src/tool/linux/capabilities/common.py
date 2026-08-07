from __future__ import annotations

from typing import Protocol

from src.shared.execution.command_result import CommandResult


class CommandRunner(Protocol):
    """Callable used by Linux capabilities to execute one command."""

    def __call__(self, command: list[str], timeout: int = 15) -> CommandResult: ...


def _parse_colon_output(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _read_os_release(run: CommandRunner) -> dict[str, str]:
    result = run(["cat", "/etc/os-release"])

    if result.success:
        fields: dict[str, str] = {}

        for line in result.stdout.splitlines():
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

        return {
            "name": fields.get("NAME", "unknown"),
            "version": fields.get("VERSION_ID", "unknown"),
            "id": fields.get("ID", "unknown"),
        }

    result = run(["lsb_release", "-a"])

    if result.success:
        fields = {}

        for line in result.stdout.splitlines():
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
