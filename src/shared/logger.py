from __future__ import annotations

import json
import os
import sys
import threading
import time as _time

_lock = threading.Lock()
_enabled = False
_file_lock = threading.Lock()
_json_format = os.environ.get("ORION_LOG_FORMAT") == "json"

# File rotation: 10MB per file, keep 5 backups
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5


def _log_dir() -> str:
    from pathlib import Path

    d = str(Path.home() / ".orion")
    os.makedirs(d, exist_ok=True)
    return d


def set_enabled(v: bool) -> None:
    global _enabled
    _enabled = v


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


def _write(line: str) -> None:
    from pathlib import Path

    path = str(Path(_log_dir()) / "orion.log")
    try:
        with _file_lock:
            _rotate_if_needed(path)
            with open(path, "a") as f:
                f.write(line + "\n")
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
    level: str, component: str, timestamp: str, fields: dict[str, object]
) -> str:
    pid = os.getpid()
    parts = [f"{timestamp} {level.upper():<8} {component} pid={pid}"]
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
        **fields,
    }
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
    if _enabled:
        with _lock:
            print(line, flush=True)


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
