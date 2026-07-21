from __future__ import annotations

from collections.abc import Callable


def _parse_colon_output(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _read_os_release(run: Callable[..., tuple[bool, str]]) -> dict[str, str]:
    ok, output = run(["cat", "/etc/os-release"])

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

    ok, output = run(["lsb_release", "-a"])

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
