"""Closed stdlib-only RPC parsing for the ephemeral Linux SSH helper."""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_MESSAGE = 1_500_000


def _integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("RPC numeric bound")
    return value


def _text(value: object, maximum: int, *, nonempty: bool = True) -> str:
    if (
        not isinstance(value, str)
        or "\0" in value
        or len(value) > maximum
        or (nonempty and not value.strip())
    ):
        raise ValueError("RPC text bound")
    return value


def _identity(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("RPC identity")
    return value


def parse_message(raw: bytes) -> dict[str, Any]:
    if not raw.endswith(b"\n") or len(raw) > MAX_MESSAGE:
        raise ValueError("RPC framing")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("RPC object")
    kind = value.get("type")
    if kind == "ping" and set(value) == {"type"}:
        return value
    if kind == "cancel" and set(value) == {"type", "request_id"}:
        _identity(value["request_id"])
        return value
    if kind != "request" or set(value) != {"type", "request_id", "operation", "arguments"}:
        raise ValueError("RPC schema")
    _identity(value["request_id"])
    operation, arguments = value["operation"], value["arguments"]
    if not isinstance(operation, str) or not isinstance(arguments, dict):
        raise ValueError("RPC operation")
    _identity(arguments.get("command_id"))
    if operation == "command.run":
        required = {"command_id", "shell", "command"}
        allowed = required | {"cwd", "timeout_seconds", "max_output_bytes"}
        if not required <= set(arguments) <= allowed:
            raise ValueError("RPC run schema")
        if not isinstance(arguments["shell"], str) or arguments["shell"] not in {"sh", "bash"}:
            raise ValueError("RPC shell")
        command = _text(arguments["command"], 65_536)
        if len(command.encode("utf-8")) > 65_536:
            raise ValueError("RPC script UTF-8 bound")
        if arguments.get("cwd") is not None:
            _text(arguments["cwd"], 4096)
        arguments["timeout_seconds"] = _integer(arguments.get("timeout_seconds", 60), 1, 3600)
        arguments["max_output_bytes"] = _integer(
            arguments.get("max_output_bytes", 262_144), 1024, 4_194_304
        )
        arguments.setdefault("cwd", None)
    elif operation == "command.status":
        if not set(arguments) <= {"command_id", "stdout_offset", "stderr_offset"}:
            raise ValueError("RPC status schema")
        for key in ("stdout_offset", "stderr_offset"):
            arguments[key] = _integer(arguments.get(key, 0), 0, 4_194_304)
    elif operation == "command.cancel":
        if set(arguments) != {"command_id"}:
            raise ValueError("RPC cancel schema")
    else:
        raise ValueError("RPC unavailable operation")
    return value


def parse_supervisor_observation(raw: bytes) -> tuple[str, int | None, bool]:
    if len(raw) > 4096:
        raise ValueError("Supervisor observation size")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"state", "exit_code", "cleanup_complete"}:
        raise ValueError("Supervisor observation schema")
    complete = value["cleanup_complete"]
    if type(complete) is not bool:
        raise ValueError("Supervisor cleanup observation")
    state, code = value["state"], value["exit_code"]
    if not isinstance(state, str):
        raise ValueError("Supervisor observation state")
    if state == "succeeded" and type(code) is int and code == 0:
        return state, code, complete
    if state == "failed" and type(code) is int and code != 0:
        return state, code, complete
    if state in {"timed_out", "outcome_unknown"} and code is None:
        return state, None, complete
    raise ValueError("Supervisor observation outcome")


def encode_message(value: dict[str, Any]) -> bytes:
    # Protocol output, including untrusted stdout/stderr, is data only. Refuse
    # invalid non-finite observations rather than emitting non-standard JSON.
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    if len(raw) + 1 > MAX_MESSAGE:
        raise ValueError("RPC output bound")
    return raw + b"\n"


def safe_duration(started: float, finished: float) -> float:
    value = finished - started
    if not math.isfinite(value):
        raise ValueError("RPC duration")
    return max(0.0, value)
