"""Standalone Linux stdlib supervisor, sent as fixed source by the SSH helper.

It adopts/reaps detached descendants, reports shell/cleanup observations through
a private inherited FD, then kills its own group. The helper independently checks
process observations too. No third-party/application imports.
"""

from __future__ import annotations

import ctypes
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any


def _arguments(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > 16_384:
        raise ValueError("supervisor input bound")
    value = json.loads(raw)
    fields = {"shell", "script", "cwd", "timeout_seconds", "parent_pid", "metadata_fd"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("supervisor input schema")
    if not isinstance(value["shell"], str) or value["shell"] not in {
        "/bin/sh",
        "/bin/bash",
        "/usr/bin/sh",
        "/usr/bin/bash",
    }:
        raise ValueError("supervisor shell")
    for key in ("script", "cwd"):
        text = value[key]
        if key == "cwd" and text is None:
            continue
        if not isinstance(text, str) or not text.strip() or len(text) > 4096 or "\0" in text:
            raise ValueError("supervisor path")
    path = PurePosixPath(value["script"])
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("supervisor script path")
    for key, minimum, maximum in (
        ("timeout_seconds", 1, 3600),
        ("parent_pid", 1, 2_147_483_647),
        ("metadata_fd", 3, 1_048_576),
    ):
        if type(value[key]) is not int or not minimum <= value[key] <= maximum:
            raise ValueError("supervisor numeric bound")
    return value


def _kill_owned_group(*_: object) -> None:
    # This process is launched start_new_session=True. Never trust a group/PID
    # supplied in the request or kill the helper/control-plane process group.
    if sys.platform != "linux":
        os._exit(125)
    if os.getpgrp() == os.getpid() and os.getsid(0) == os.getpid():
        try:
            os.killpg(os.getpid(), signal.SIGKILL)
        except OSError:
            pass
    os._exit(125)


def _private_script(path: Path) -> None:
    if sys.platform != "linux":
        raise OSError("Linux script ownership is unavailable")
    if path != path.resolve(strict=True):
        raise ValueError("linked script")
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or info.st_mode & 0o077
    ):
        raise ValueError("script ownership")
    if info.st_size > 65_536:
        raise ValueError("script size")
    parent = path.parent
    directory = parent.lstat()
    if (
        not stat.S_ISDIR(directory.st_mode)
        or directory.st_uid != os.geteuid()
        or directory.st_mode & 0o077
    ):
        raise ValueError("script directory ownership")


def _terminate_children() -> bool:
    """A per-command subreaper owns even double-forked/session-detached children.

    Kill direct children through pidfds, reap them, then repeat for adopted orphans.
    ECHILD supplies the final kernel check; a proc listing alone is insufficient.
    """
    if sys.platform != "linux":
        raise OSError("Linux child supervision is unavailable")
    deadline = time.monotonic() + 3
    try:
        while time.monotonic() < deadline:
            for _ in range(4096):
                try:
                    reaped, _ = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    return True
                if reaped == 0:
                    break
            with open(f"/proc/self/task/{os.getpid()}/children", "rb") as stream:
                raw = stream.read(65_537)
            if len(raw) > 65_536:
                return False
            children = raw.split()
            if len(children) > 4096:
                return False
            for value in children:
                pid = int(value)
                try:
                    descriptor = os.pidfd_open(pid, 0)
                    try:
                        text = Path(f"/proc/{pid}/stat").read_text(errors="replace")
                        # These unreaped children cannot have their PID reused.
                        if int(text.rsplit(")", 1)[1].split()[1]) != os.getpid():
                            return False
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                    finally:
                        os.close(descriptor)
                except ProcessLookupError:
                    pass
            time.sleep(0.01)
    except (OSError, ValueError, IndexError, AttributeError):
        return False
    return False


def supervise(raw: str) -> None:
    # The platform gate precedes any process launch, chmod, signal or file read.
    if sys.platform != "linux":
        raise OSError("Linux supervisor is unavailable")
    values = _arguments(raw)
    if os.getpgrp() != os.getpid() or os.getsid(0) != os.getpid():
        raise OSError("Supervisor does not own a new session")
    outcome: dict[str, object] = {"state": "outcome_unknown", "exit_code": None}
    subreaper = False

    def finish(*_: object) -> None:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        complete = subreaper and _terminate_children()
        try:
            os.write(
                values["metadata_fd"],
                json.dumps(
                    {
                        **outcome,
                        "cleanup_complete": complete,
                    }
                ).encode("ascii"),
            )
        except OSError:
            pass
        _kill_owned_group()

    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGHUP, finish)
    library = ctypes.CDLL(None, use_errno=True)
    library.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    library.prctl.restype = ctypes.c_int
    # PR_SET_CHILD_SUBREAPER applies before any shell can daemonize. Each command
    # has its own supervisor, so adopted children cannot be mixed across commands.
    if library.prctl(36, 1, 0, 0, 0) != 0:
        finish()
    subreaper = True
    # PR_SET_PDEATHSIG catches helper crash/SIGKILL without relying on SSH EOF.
    # Recheck PPID after installing it to close the parent-death setup race.
    if library.prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or os.getppid() != values["parent_pid"]:
        finish()
    try:
        _private_script(Path(values["script"]))
        process = subprocess.Popen(
            [
                values["shell"],
                *(["--noprofile", "--norc"] if values["shell"].endswith("bash") else []),
                values["script"],
            ],
            cwd=values["cwd"],
            stdin=subprocess.DEVNULL,
            close_fds=True,
            # stdout/stderr are the helper's bounded capture pipes. The private
            # metadata FD is closed in this child and is never shell authority.
        )
        try:
            code = process.wait(timeout=values["timeout_seconds"])
            outcome = {"state": "succeeded" if code == 0 else "failed", "exit_code": code}
        except subprocess.TimeoutExpired:
            outcome = {"state": "timed_out", "exit_code": None}
    except Exception:
        pass  # Never print script, cwd, private paths or exception details.
    finally:
        finish()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("supervisor invocation")
        supervise(sys.argv[1])
    except Exception:
        os._exit(125)
