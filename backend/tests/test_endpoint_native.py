"""Deterministic browser fixture and native desktop capture/input integration."""

from __future__ import annotations

import asyncio
import base64
import http.server
import os
import threading
from pathlib import Path

import pytest

from orion_endpoint.browser import Browser
from orion_endpoint.desktop import Desktop
from orion_endpoint.policy import Policy


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        if self.path == "/download":
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="fixture.txt"')
            self.end_headers()
            self.wfile.write(b"controlled-download")
            return
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b'<title>Local fixture</title><label>Name<input id="name"></label>'
            b'<button id="button">Click me</button><p>Untrusted webpage data</p>'
            b'<a id="download" href="/download">Download fixture</a>'
        )

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_isolated_browser_local_fixture(tmp_path: Path) -> None:
    async def scenario() -> None:
        downloads = tmp_path / "controlled downloads"
        downloads.mkdir()
        browser = Browser(
            Policy(
                browser=True,
                write_roots=[str(downloads)],
                browser_download_directory=str(downloads),
            )
        )
        if not await browser.available():
            if os.getenv("ORION_NATIVE_TESTS") == "1":
                pytest.fail("Required provisioned browser unavailable")
            pytest.skip("Managed browser not provisioned; unavailable path tested separately")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            result = await browser.execute("open", {"url": url})
            assert result["title"] == "Local fixture" and result["untrusted_external_content"]
            assert not await browser.context.cookies()
            await browser.execute("type", {"selector": "#name", "text": "fixture text"})
            assert await browser.page.locator("#name").input_value() == "fixture text"
            await browser.execute("key", {"key": "left"})
            await browser.execute("click", {"selector": "#button"})
            assert "Click me" in (await browser.execute("snapshot", {}))["snapshot"]
            await browser.execute("navigate", {"url": url})
            await browser.execute("click", {"selector": "#download"})
            await asyncio.gather(*browser.download_tasks)
            saved = list(downloads.glob("download-*"))
            assert len(saved) == 1 and saved[0].read_bytes() == b"controlled-download"
            with pytest.raises(ValueError):
                await browser.execute("navigate", {"url": "file:///etc/passwd"})
        finally:
            await browser.close()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        assert browser.page is None and browser.context is None

    asyncio.run(scenario())


def test_native_desktop_capture_and_input_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("ORION_NATIVE_TESTS") != "1":
        pytest.skip("Native desktop fixture runs under Xvfb or interactive Windows CI")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    desktop = Desktop(Policy(desktop_capture=True, desktop_control=True, max_resolution=640))
    geometry = desktop.geometry()
    assert geometry
    result = desktop.capture(1)
    assert result["width"] <= 640 and result["height"] <= 640
    assert base64.b64decode(result["image_b64"])[:2] == b"\xff\xd8"
    with pytest.raises(ValueError):
        desktop.input("click", {"monitor": 1, "x": geometry[0]["width"], "y": 0, "button": "left"})
    # Only move the pointer in a deterministic safe display area; no privileged desktop.
    from pynput import mouse

    pointer = mouse.Controller()
    original = pointer.position
    try:
        desktop.input("move", {"monitor": 1, "x": 3, "y": 4})
        assert pointer.position == (geometry[0]["left"] + 3, geometry[0]["top"] + 4)
    finally:
        pointer.position = original


def test_worker_wheel_contains_only_executor(tmp_path: Path) -> None:
    import subprocess
    import sys
    import zipfile

    repository = Path(__file__).parents[2]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            str(repository / "worker"),
            "--outdir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
    )
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert all(
            name.startswith(("orion_endpoint/", "orion_worker-")) for name in archive.namelist()
        )
        metadata = archive.read(
            next(name for name in archive.namelist() if name.endswith("METADATA"))
        ).decode()
        assert "Requires-Python: >=3.12" in metadata
        for forbidden in ("fastapi", "fastembed", "onnxruntime", "numpy", "mcp"):
            assert forbidden not in metadata
