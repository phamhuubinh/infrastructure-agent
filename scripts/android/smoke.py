"""Exercise an Orion debug APK via UIAutomator and a local provider fixture.

Bootstrap the backend development dependencies and boot a disposable emulator,
then run ``python scripts/android/smoke.py Orion.apk --serial emulator-5554``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import ExitStack, closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TypeVar
from urllib.parse import parse_qs
from xml.etree import ElementTree as ET

from uvicorn._types import (
    ASGIApplication,
    ASGIReceiveCallable,
    ASGISendCallable,
    ASGISendEvent,
    Scope,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "io.orion.desktop"
ACTIVITY = f"{PACKAGE}/.MainActivity"
RESUME_PROMPT = "Resume the active fixture stream."
FIRST_DELTA = "Android cursor "
FINAL_REPLY = FIRST_DELTA + "resumed."


class StreamInterrupted(Exception):
    pass


class ResumeProbe:
    def __init__(self) -> None:
        self.interrupted: tuple[str, str] | None = None
        self.resumed = threading.Event()
        self.release = threading.Event()

    def wrap(self, app: ASGIApplication) -> ASGIApplication:
        async def observe(
            scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
        ) -> None:
            path = scope.get("path", "")
            if not re.fullmatch(r"/api/requests/[^/]+/stream", path):
                await app(scope, receive, send)
                return
            after = parse_qs(scope["query_string"].decode()).get("after", [None])[0]
            if self.interrupted == (path, after):
                self.resumed.set()

            async def forward(message: ASGISendEvent) -> None:
                await send(message)
                body = message.get("body", b"")
                if self.interrupted is None and body.startswith(b"id: "):
                    record = json.loads(body.split(b"\ndata: ", 1)[1])
                    if (
                        record["type"] == "assistant.delta"
                        and record["payload"]["content"] == FIRST_DELTA
                    ):
                        self.interrupted = (path, record["event_id"])
                        raise StreamInterrupted

            try:
                await app(scope, receive, forward)
            except StreamInterrupted:
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )

        return observe


class Emulator:
    def __init__(self, adb: str, serial: str) -> None:
        if not serial.startswith("emulator-"):
            raise ValueError("Select a disposable Android emulator by serial")
        self.command = [adb, "-s", serial]

    def run(self, *args: str, timeout: int = 25) -> str:
        result = subprocess.run(
            [*self.command, *args],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode:
            operation = " ".join(args[:3])
            raise RuntimeError(f"adb {operation} failed (exit {result.returncode})")
        return result.stdout.strip()

    def launch(self) -> None:
        result = self.run("shell", "am", "start", "-W", "-n", ACTIVITY)
        if "Status: ok" not in result:
            raise RuntimeError(f"Orion activity failed to launch: {result}")


def status_rows(database: Path) -> list[tuple[str]]:
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute("SELECT status FROM requests ORDER BY created_at").fetchall()


T = TypeVar("T")


def until(description: str, probe: Callable[[], T | None], timeout: int = 35) -> T:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value is not None:
            return value
        time.sleep(0.35)
    raise RuntimeError(f"Timed out waiting for {description}")


class Ui:
    def __init__(self, emulator: Emulator) -> None:
        self.emulator = emulator
        self.dump_path = f"/sdcard/orion-smoke-{uuid.uuid4().hex}.xml"

    def nodes(self, package: str, *, clickable: bool = False) -> list[ET.Element]:
        try:
            self.emulator.run("shell", "rm", "-f", self.dump_path)
            self.emulator.run(
                "shell", "uiautomator", "dump", self.dump_path, timeout=12
            )
            raw = self.emulator.run("exec-out", "cat", self.dump_path)
            root = ET.fromstring(raw)
        except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError):
            return []
        return [
            node
            for node in root.iter("node")
            if node.get("package") == package
            and (not clickable or node.get("clickable") == "true")
        ]

    @staticmethod
    def label(node: ET.Element, name: str) -> bool:
        return any(node.get(attr) == name for attr in ("text", "content-desc", "hint"))

    def find(
        self, name: str, *, package: str = PACKAGE, clickable: bool = False
    ) -> ET.Element:
        def probe() -> ET.Element | None:
            return next(
                (
                    node
                    for node in self.nodes(package, clickable=clickable)
                    if self.label(node, name)
                ),
                None,
            )

        return until(f"accessibility node {name!r}", probe)

    def tap(self, node: ET.Element) -> None:
        bounds = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not bounds:
            raise RuntimeError("Accessibility node did not provide screen bounds")
        left, top, right, bottom = map(int, bounds.groups())
        if right <= left or bottom <= top:
            raise RuntimeError("Accessibility node is off-screen")
        self.emulator.run(
            "shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2)
        )

    def click(self, name: str) -> None:
        self.tap(self.find(name))

    def fill(
        self, name: str, value: str, *, index: int, check_keyboard: bool = False
    ) -> None:
        def probe() -> ET.Element | None:
            edits = [
                node
                for node in self.nodes(PACKAGE)
                if node.get("class") == "android.widget.EditText"
            ]
            named = next((node for node in edits if self.label(node, name)), None)
            if named is not None:
                return named
            return edits[index] if len(edits) > index else None

        self.tap(until(f"editable accessibility node {name!r}", probe))
        if not re.fullmatch(r"[a-zA-Z0-9 .:/_-]+", value):
            raise ValueError("ADB fixture input requires plain ASCII")
        if check_keyboard:
            until(
                "Android IME shown", lambda: True if self.keyboard_visible() else None
            )
        self.emulator.run("shell", "input", "text", value.replace(" ", "%s"))
        if self.keyboard_visible():
            self.emulator.run("shell", "input", "keyevent", "KEYCODE_BACK")

    def keyboard_visible(self) -> bool:
        return "mInputShown=true" in self.emulator.run(
            "shell", "dumpsys", "input_method"
        )


def check_file_picker(ui: Ui, stack: ExitStack, directory: Path) -> None:
    name = f"orion-attachment-{uuid.uuid4().hex[:8]}.txt"
    local = directory / name
    local.write_text("Orion Android document fixture.", encoding="utf-8")
    remote = f"/sdcard/Download/{name}"
    ui.emulator.run("push", str(local), remote)
    stack.callback(ui.emulator.run, "shell", "rm", "-f", remote)
    ui.tap(ui.find("Attach document", clickable=True))
    documents = "com.google.android.documentsui"
    ui.tap(ui.find("Show roots", package=documents))
    ui.tap(ui.find("Downloads", package=documents))
    ui.tap(ui.find(name, package=documents))
    ui.find(name)
    print(
        "Android DocumentsUI returned the text file and Orion displayed its attachment.",
        flush=True,
    )


def native_sessions(database: Path) -> list[tuple[str, int]]:
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(
            "SELECT platform, revoked_at IS NOT NULL FROM native_sessions ORDER BY created_at"
        ).fetchall()


def smoke(emulator: Emulator, apk: Path, *, extended: bool) -> None:
    if emulator.run("shell", "getprop", "sys.boot_completed") != "1":
        raise RuntimeError("Android emulator has not completed boot")
    if emulator.run("shell", "pm", "list", "packages", PACKAGE):
        raise RuntimeError("Refusing to overwrite an existing Orion installation")
    provider_type = runpy.run_path(str(ROOT / "scripts/linux/headless_smoke.py"))[
        "Provider"
    ]
    probe = ResumeProbe()

    class Provider(provider_type):
        def reply(self, body: dict) -> None:
            if body["messages"][-1].get("content") != RESUME_PROMPT:
                super().reply(body)
                return
            for content in (FIRST_DELTA, "resumed."):
                value = {"choices": [{"index": 0, "delta": {"content": content}}]}
                self.wfile.write(f"data: {json.dumps(value)}\n\n".encode())
                if content == FIRST_DELTA:
                    # The provider adapter reads 16 KiB blocks. Flush the first
                    # event through that buffer before holding the response open.
                    self.wfile.write(b":" + b" " * 16_384 + b"\n\n")
                self.wfile.flush()
                if content == FIRST_DELTA and not probe.release.wait(45):
                    return
            self.wfile.write(
                b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                b"data: [DONE]\n\n"
            )

    remote_fixture = runpy.run_path(str(ROOT / "scripts/desktop/smoke.py"))[
        "remote_fixture"
    ]
    with ExitStack() as stack:
        provider = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Provider))
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join, 15)
        stack.callback(provider.shutdown)
        stack.callback(provider_type.release.set)
        stack.callback(probe.release.set)
        os.environ["ORION_MODEL_BASE_URL"] = (
            f"http://127.0.0.1:{provider.server_port}/v1"
        )
        os.environ["ORION_MODEL_ID"] = "headless-fixture"
        database = (
            Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="orion-android-uia-")
                )
            )
            / "orion.db"
        )
        origin, code = remote_fixture(
            stack, database, wrap=probe.wrap if extended else None
        )
        spec = f"tcp:{origin.rsplit(':', 1)[1]}"
        emulator.run("reverse", "--no-rebind", spec, spec)
        stack.callback(emulator.run, "reverse", "--remove", spec)
        emulator.run("install", str(apk), timeout=120)
        stack.callback(emulator.run, "uninstall", PACKAGE)
        ui = Ui(emulator)
        stack.callback(emulator.run, "shell", "rm", "-f", ui.dump_path)
        emulator.launch()
        ui.find("Kết nối server")
        ui.fill("Tên server", "Android fixture", index=0)
        ui.fill("Địa chỉ server", origin, index=1)
        ui.click("Lưu server")
        ui.click("Mở Android fixture")
        ui.fill("Mã kết nối", code, index=2)
        ui.click("Kết nối bằng mã")
        until(
            "Android session in SQLite",
            lambda: True if native_sessions(database) == [("android", 0)] else None,
        )
        ui.find("Sign out")
        print(
            "Android native enrollment recorded one active server session.", flush=True
        )
        emulator.run("shell", "am", "force-stop", PACKAGE)
        emulator.launch()
        ui.click("Mở Android fixture")
        ui.find("Sign out")
        if native_sessions(database) != [("android", 0)]:
            raise AssertionError(
                "Relaunch did not reuse its existing Android enrollment"
            )
        print("Android relaunch reused the saved profile and enrollment.", flush=True)
        ui.fill(
            "Chat input", "Send the fixture response.", index=0, check_keyboard=extended
        )
        ui.click("Send message")
        until(
            "one completed chat",
            lambda: True if status_rows(database) == [("completed",)] else None,
        )
        ui.find("Headless fixture.")
        if extended:
            ui.fill("Chat input", "Wait for SIGINT.", index=0)
            ui.click("Send message")
            ui.find("Stop generating")
            if not provider_type.waiting.wait(20):
                raise RuntimeError("The request did not reach the holding provider")
            emulator.run("shell", "input", "keyevent", "KEYCODE_HOME")
            until(
                "Orion in the Android background",
                lambda: (
                    True
                    if not any(
                        PACKAGE in line
                        for line in emulator.run(
                            "shell", "dumpsys", "activity", "activities"
                        ).splitlines()
                        if "topResumedActivity=" in line
                    )
                    else None
                ),
            )
            # Interrupt the emulator's route to this fixture without changing
            # system-wide Wi-Fi or relying on an external endpoint.
            emulator.run("reverse", "--remove", spec)
            try:
                if spec in emulator.run("reverse", "--list").split():
                    raise AssertionError("Fixture route is still available")
                emulator.launch()
            finally:
                emulator.run("reverse", "--no-rebind", spec, spec)
            ui.click("Stop generating")
            until(
                "one completed and one cancelled chat",
                lambda: (
                    True
                    if status_rows(database) == [("completed",), ("cancelled",)]
                    else None
                ),
            )
            print(
                "Android restored the fixture route and cancelled the single admitted request.",
                flush=True,
            )
            ui.fill("Chat input", RESUME_PROMPT, index=0)
            ui.click("Send message")
            if not probe.resumed.wait(25) or probe.interrupted is None:
                raise AssertionError(
                    "Android did not reopen the same request stream after its delta cursor"
                )
            request_id = probe.interrupted[0].split("/")[-2]
            with closing(
                sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
            ) as db:
                status = db.execute(
                    "SELECT status FROM requests WHERE request_id = ?", (request_id,)
                ).fetchone()
            if status != ("running",):
                raise AssertionError(
                    f"Request was not running when observation resumed: {status}"
                )
            probe.release.set()
            ui.find(FINAL_REPLY)
            expected = [("completed",), ("cancelled",), ("completed",)]
            until(
                "exactly three requests with the resumed request completed",
                lambda: True if status_rows(database) == expected else None,
            )
            print(
                f"Android resumed active request {request_id} after cursor {probe.interrupted[1]}.",
                flush=True,
            )
            check_file_picker(ui, stack, database.parent)
        ui.click("Sign out")
        until(
            "revoked Android session",
            lambda: True if native_sessions(database) == [("android", 1)] else None,
        )
        ui.find("Kết nối bằng mã")
        print(
            "Android chat completed and sign-out revoked its server session.",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Check IME, network recovery, active stream resume and the system file picker",
    )
    args = parser.parse_args()
    smoke(
        Emulator(args.adb, args.serial),
        args.apk.resolve(strict=True),
        extended=args.extended,
    )


if __name__ == "__main__":
    main()
