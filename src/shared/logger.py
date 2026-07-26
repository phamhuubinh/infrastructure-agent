from __future__ import annotations

import json
import os
import sys
import threading
import time as _time

_lock = threading.Lock()
_file_lock = threading.Lock()
_json_format = os.environ.get("ORION_LOG_FORMAT") == "json"

# Auto-detect: color console output when stderr is a terminal (TTY).
# `set_enabled(False)` can override this to disable if needed.
_color_output = sys.stderr.isatty()

# File rotation: 10MB per file, keep 5 backups
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5

# Retention: keep only the most recent 500 log lines
_MAX_LINES = 500

# Per-request context (request_id, session_id).
# Thread-local so each request thread gets its own context without passing args.
_tls = threading.local()


def set_context(
    request_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Set request/session IDs for the current thread.

    All subsequent log calls in this thread will include these IDs.
    Call ``clear_context()`` to reset.
    """
    _tls.request_id = request_id
    _tls.session_id = session_id


def clear_context() -> None:
    """Clear the request/session IDs for the current thread."""
    _tls.request_id = None
    _tls.session_id = None


def _log_dir() -> str:
    from pathlib import Path

    d = str(Path.home() / ".orion")
    os.makedirs(d, exist_ok=True)
    return d


def set_enabled(v: bool) -> None:
    """Override console output. True = force color, False = force plain."""
    global _color_output
    _color_output = v


def _rotate_if_needed(path: str) -> None:
    """Rotate log file if it exceeds _MAX_BYTES."""
    try:
        if not os.path.exists(path):
            return
        size = os.path.getsize(path)
        if size < _MAX_BYTES:
            return
        for i in range(_BACKUP_COUNT - 1, 0, -1):
            old = f"{path}.{i}"
            new = f"{path}.{i + 1}"
            if os.path.exists(old):
                os.replace(old, new)
        backup = f"{path}.1"
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(path, backup)
    except OSError:
        pass  # rotation is best-effort


def _trim_to_max_lines(path: str) -> None:
    """Keep only the most recent _MAX_LINES lines in the log file."""
    try:
        if not os.path.exists(path):
            return
        with open(path) as f:
            lines = f.readlines()
        if len(lines) <= _MAX_LINES:
            return
        with open(path, "w") as f:
            f.writelines(lines[-_MAX_LINES:])
    except OSError:
        pass  # trim is best-effort


def _write(line: str) -> None:
    from pathlib import Path

    path = str(Path(_log_dir()) / "orion.log")
    try:
        with _file_lock:
            _rotate_if_needed(path)
            with open(path, "a") as f:
                f.write(line + "\n")
            _trim_to_max_lines(path)
    except OSError:
        import traceback

        print(
            "[logger] failed to write to log file:",
            traceback.format_exc(),
            file=sys.stderr,
        )


def _now() -> str:
    t = _time.time()
    sec = int(t)
    ms = int((t - sec) * 1000)
    import datetime

    dt = datetime.datetime.fromtimestamp(sec)
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d}"


def _format_text(
    level: str,
    component: str,
    timestamp: str,
    fields: dict[str, object],
) -> str:
    pid = os.getpid()
    parts = [f"{timestamp} {level.upper():<8} {component} pid={pid}"]

    # Inject request/session IDs from thread-local context.
    # Skip keys already provided by the caller to avoid duplicates.
    req_id = getattr(_tls, "request_id", None)
    ses_id = getattr(_tls, "session_id", None)
    has_request = "request" in fields
    has_session = "session" in fields
    if req_id and not has_request:
        parts.append(f"request={req_id}")
    if ses_id and not has_session:
        parts.append(f"session={ses_id}")

    for k, v in fields.items():
        if v is None:
            continue
        sv = str(v)
        if " " in sv or '"' in sv:
            sv = sv.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{k}="{sv}"')
        else:
            parts.append(f"{k}={sv}")
    return " ".join(parts)


def _format_color(
    level: str,
    component: str,
    timestamp: str,
    fields: dict[str, object],
) -> str:
    """Format a colored log line with emoji + ANSI for terminal output."""
    emoji: dict[str, str] = {
        "DEBUG": "\033[34m🔵 DEBUG",
        "INFO": "\033[32m🟢 INFO",
        "WARNING": "\033[33m🟡 WARNING",
        "ERROR": "\033[31m🔴 ERROR",
        "CRITICAL": "\033[35m⚫ CRITICAL",
    }
    prefix = emoji.get(level, level.upper())
    pid = os.getpid()
    parts = [f"{timestamp} {prefix} {component}\033[0m pid={pid}"]

    # Inject request/session IDs, skipping duplicates
    req_id = getattr(_tls, "request_id", None)
    ses_id = getattr(_tls, "session_id", None)
    has_request = "request" in fields
    has_session = "session" in fields
    if req_id and not has_request:
        parts.append(f"request={req_id}")
    if ses_id and not has_session:
        parts.append(f"session={ses_id}")

    for k, v in fields.items():
        if v is None:
            continue
        sv = str(v)
        if " " in sv or '"' in sv:
            sv = sv.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{k}="{sv}"')
        else:
            parts.append(f"{k}={sv}")
    return " ".join(parts)


def _format_json(
    level: str, component: str, timestamp: str, fields: dict[str, object]
) -> str:
    record: dict[str, object] = {
        "timestamp": timestamp,
        "level": level.upper(),
        "logger": component,
        "pid": os.getpid(),
    }
    req_id = getattr(_tls, "request_id", None)
    ses_id = getattr(_tls, "session_id", None)
    if req_id and "request" not in fields:
        record["request"] = req_id
    if ses_id and "session" not in fields:
        record["session"] = ses_id
    record.update(fields)
    return json.dumps(record, default=str, ensure_ascii=False)


def log(level: str, component: str, **fields: object) -> None:
    ts = _now()
    msg_val = fields.pop("message", None)
    if msg_val is not None:
        fields["message"] = msg_val

    if _json_format:
        line = _format_json(level, component, ts, fields)
    else:
        line = _format_text(level, component, ts, fields)

    _write(line)


def debug(component: str, **fields: object) -> None:
    log("DEBUG", component, **fields)


def info(component: str, **fields: object) -> None:
    log("INFO", component, **fields)


def warning(component: str, **fields: object) -> None:
    log("WARNING", component, **fields)


def error(component: str, **fields: object) -> None:
    log("ERROR", component, **fields)


def critical(component: str, **fields: object) -> None:
    log("CRITICAL", component, **fields)
