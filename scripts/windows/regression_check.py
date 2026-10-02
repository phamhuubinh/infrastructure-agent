"""Bound native CI subprocesses and retain diagnostics when a contract test hangs."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["install", "test"])
    args = parser.parse_args()
    log = (
        Path(os.getenv("RUNNER_TEMP", tempfile.gettempdir()))
        / f"orion-native-regression-{args.mode}.log"
    )
    command = (
        [sys.executable, "-m", "pip", "install", "-e", "./backend[dev]"]
        if args.mode == "install"
        else [
            sys.executable,
            "-m",
            "pytest",
            "-vv",
            "-o",
            "faulthandler_timeout=90",
            "backend/tests/test_scheduler.py",
            "backend/tests/test_scheduler_api.py",
            "backend/tests/test_remote_access.py",
            "backend/tests/test_mcp.py",
            "backend/tests/test_endpoints.py",
            "backend/tests/test_device_chat.py",
        ]
    )
    timed_out = False
    with log.open("wb") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            process.wait(timeout=600 if args.mode == "install" else 240)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            else:
                process.kill()
            process.wait(timeout=15)
    with log.open("rb") as output:
        output.seek(max(0, log.stat().st_size - 1_000_000))
        print(output.read().decode("utf-8", errors="replace"))
    if timed_out:
        raise SystemExit(f"Native {args.mode} timed out; retained traceback at {log}.")
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
