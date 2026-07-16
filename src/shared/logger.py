from __future__ import annotations

import sys
import time
import os
import threading

_lock = threading.Lock()
_enabled = False
_file_lock = threading.Lock()


def _log_dir() -> str:
    from pathlib import Path

    d = str(Path.home() / ".orion")
    os.makedirs(d, exist_ok=True)
    return d


def set_enabled(v: bool) -> None:
    global _enabled
    _enabled = v


def _write(line: str) -> None:
    from pathlib import Path

    path = str(Path(_log_dir()) / "orion.log")
    try:
        with _file_lock:
            with open(path, "a") as f:
                f.write(line + "\n")
    except Exception:
        pass


def _now() -> str:
    t = time.time()
    sec = int(t)
    ms = int((t - sec) * 1000)
    import datetime

    dt = datetime.datetime.fromtimestamp(sec)
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d}"


def log(level: str, component: str, **fields: object) -> None:
    pid = os.getpid()
    parts = [f"{_now()} {level.upper():<8} {component} pid={pid}"]
    msg = fields.pop("message", None)
    for k, v in fields.items():
        if v is None:
            continue
        sv = str(v)
        if " " in sv or '"' in sv:
            sv = sv.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{k}="{sv}"')
        else:
            parts.append(f"{k}={sv}")
    if msg is not None:
        sm = str(msg).replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'message="{sm}"')
    line = " ".join(parts)
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
