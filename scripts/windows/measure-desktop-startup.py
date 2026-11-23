"""Profile an isolated Windows WebView2 launch without touching the running Orion Host."""

from __future__ import annotations

import argparse
import json
import mmap
import os
import statistics
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


def events(path: Path, key: str = "elapsed_ms") -> dict[str, int]:
    if not path.is_file():
        return {}
    return {
        event["phase"]: event[key]
        for event in map(json.loads, path.read_text(encoding="utf-8").splitlines())
    }


def sample(executable: Path, sidecar: Path) -> dict[str, object]:
    directory = Path(tempfile.gettempdir()) / ("orion-startup-" + uuid.uuid4().hex)
    started = time.perf_counter()
    started_wall = time.time_ns() // 1_000_000
    subprocess.run(
        [str(executable), "--startup-probe", str(directory), str(sidecar)],
        timeout=65,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    finished_wall = time.time_ns() // 1_000_000
    native = events(directory / "startup.jsonl")
    wall = events(directory / "startup.jsonl", "wall_ms")
    required = {
        "native_entry",
        "backend_start",
        "backend_ready",
        "webview_start",
        "page_loaded",
        "ui_ready",
    }
    if not required <= native.keys():
        raise RuntimeError(
            "Use an Orion debug executable with isolated startup-probe support"
        )
    return {
        "sidecar_ms": native["backend_ready"] - native["backend_start"],
        "webview_ms": native["page_loaded"] - native["webview_start"],
        "native_to_page_ms": native["page_loaded"],
        "launch_to_native_ms": wall["native_entry"] - started_wall,
        "launch_to_page_ms": wall["page_loaded"] - started_wall,
        "launch_to_ready_ms": wall["ui_ready"] - started_wall,
        "page_to_ready_ms": native["ui_ready"] - native["page_loaded"],
        "exit_after_page_ms": finished_wall - wall["page_loaded"],
        "process_lifetime_ms": round((time.perf_counter() - started) * 1000),
        "native_events": native,
        "sidecar_events": events(directory / "managed/backend-startup.jsonl"),
        "probe_directory": str(directory),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", type=Path, required=True, help="debug Orion.exe")
    parser.add_argument(
        "--sidecar", type=Path, required=True, help="frozen OrionBackend.exe"
    )
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if os.name != "nt" or not 1 <= args.samples <= 10:
        parser.error("Windows and between 1 and 10 samples are required")
    executable, sidecar = (
        args.desktop.resolve(strict=True),
        args.sidecar.resolve(strict=True),
    )
    with (
        executable.open("rb") as stream,
        mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image,
    ):
        if any(
            image.find(marker) < 0 for marker in (b"--startup-probe", b"native_entry")
        ):
            parser.error(
                "This Orion executable does not support the isolated startup probe"
            )
    samples = [sample(executable, sidecar) for _ in range(args.samples)]
    medians = {
        key: statistics.median(int(str(row[key])) for row in samples)
        for key in (
            "sidecar_ms",
            "webview_ms",
            "native_to_page_ms",
            "launch_to_native_ms",
            "launch_to_page_ms",
            "launch_to_ready_ms",
            "page_to_ready_ms",
            "exit_after_page_ms",
            "process_lifetime_ms",
        )
    }
    print(json.dumps({"samples": samples, "medians": medians}, indent=2))


if __name__ == "__main__":
    main()
