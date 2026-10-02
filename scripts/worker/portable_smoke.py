"""Run frozen binary without host Python/PATH, pair/read/files and clean temporary Exit."""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from orion.api.app import create_app


class Fixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b'<title>Portable local fixture</title><input id="name"><button id="button">Fixture button</button>'
        )

    def log_message(self, format: str, *args: object) -> None:
        pass


def smoke(root: Path) -> None:
    manifest = json.loads((root / "portable-manifest.json").read_text())
    assert manifest["python_prerequisite"] is False
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    executable = root / manifest["entrypoint"]
    isolated = {**os.environ, "PATH": "", "PYTHONPATH": "", "PYTHONHOME": ""}
    test = json.loads(
        subprocess.check_output(
            [str(executable), "--self-test"], env=isolated, text=True
        )
    )
    assert test["portable"] and test["version"] == manifest["version"]
    browser_tests = os.getenv("ORION_PORTABLE_BROWSER_TESTS") == "1"
    if browser_tests:
        subprocess.run(
            [str(executable), "browser", "install"], env=isolated, check=True
        )
    with tempfile.TemporaryDirectory(prefix="portable smoke with spaces ") as temporary:
        work = Path(temporary)
        files = work / "allowed files"
        files.mkdir()
        policy = work / "policy.json"
        policy.write_text(
            json.dumps(
                {
                    "read_roots": [str(files)],
                    "write_roots": [str(files)],
                    "browser": browser_tests,
                }
            )
        )
        fixture = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        fixture_thread = threading.Thread(target=fixture.serve_forever)
        fixture_thread.start()
        os.environ["ORION_ENDPOINTS"] = "1"
        app = create_app(work / "server.db")
        loop: concurrent.futures.Future[asyncio.AbstractEventLoop] = (
            concurrent.futures.Future()
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=0,
                log_level="error",
                ws_per_message_deflate=False,
            )
        )

        async def serve() -> None:
            loop.set_result(asyncio.get_running_loop())
            await server.serve()

        thread = threading.Thread(target=lambda: asyncio.run(serve()))
        thread.start()
        worker = None
        try:
            deadline = time.monotonic() + 30
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("server_start_timeout")
                time.sleep(0.05)
            origin = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"

            def api(path: str, data: dict[str, object] | None = None) -> object:
                request = urllib.request.Request(
                    origin + path,
                    data=json.dumps(data).encode() if data is not None else None,
                    headers={"Origin": origin, "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    return json.loads(response.read())

            token = api("/api/endpoints/pairing-tokens", {})["token"]
            worker = subprocess.Popen(
                [
                    str(executable),
                    "--server",
                    origin,
                    "--name",
                    "Portable fixture",
                    "--policy",
                    str(policy),
                    "--data",
                    str(work / "worker state"),
                ],
                env={
                    **isolated,
                    "ORION_PAIRING_TOKEN": token,
                    "TMPDIR": str(work),
                    "TEMP": str(work),
                    "TMP": str(work),
                },
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 30
            while True:
                rows = api("/api/endpoints")
                if rows and rows[0]["online"]:
                    break
                if worker.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("portable_connect_timeout")
                time.sleep(0.1)
            target = rows[0]["endpoint_id"]
            assert rows[0]["temporary"]
            manager = app.state.application.endpoints

            def rpc(operation: str, args: dict[str, object]) -> dict[str, object]:
                return asyncio.run_coroutine_threadsafe(
                    manager.dispatch(target, operation, args), loop.result()
                ).result(15)

            assert rpc("system.inspect", {})["cpu_count"]
            destination = str(files / "portable file.txt")
            rpc("file.write", {"path": destination, "content": "portable fixture"})
            assert (files / "portable file.txt").read_text() == "portable fixture"
            assert rpc("file.read", {"path": destination})["content_b64"]
            if browser_tests:
                assert "browser.open" in rows[0]["capabilities"]
                result = rpc(
                    "browser.open", {"url": f"http://127.0.0.1:{fixture.server_port}"}
                )
                assert result["title"] == "Portable local fixture"
                rpc("browser.type", {"selector": "#name", "text": "fixture value"})
                rpc("browser.click", {"selector": "#button"})
                assert "Fixture button" in rpc("browser.snapshot", {})["snapshot"]
                rpc("browser.close", {})
            assert not (work / "worker state/identity.json").exists()
            worker.communicate(input=b"exit\n", timeout=15)
            assert worker.returncode == 0
            assert manager.store.get(target)["revoked_at"] is not None
            assert not list(work.glob("orion-remote-session-*"))
            assert api(f"/api/endpoints/{target}/forget", {"confirmed": True})[
                "forgotten"
            ]
            # The very same frozen binary can explicitly remember, exit and reconnect.
            state = work / "remembered state"
            for attempt in range(2):
                environment = dict(isolated)
                if not attempt:
                    environment["ORION_PAIRING_TOKEN"] = api(
                        "/api/endpoints/pairing-tokens", {}
                    )["token"]
                worker = subprocess.Popen(
                    [
                        str(executable),
                        "--remember",
                        "--server",
                        origin,
                        "--name",
                        "Remembered fixture",
                        "--policy",
                        str(policy),
                        "--data",
                        str(state),
                    ],
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                deadline = time.monotonic() + 30
                while True:
                    rows = api("/api/endpoints")
                    if rows and rows[0]["online"]:
                        break
                    if worker.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("remembered_connect_timeout")
                    time.sleep(0.1)
                remembered = json.loads((state / "identity.json").read_text())
                assert not rows[0]["temporary"]
                assert rows[0]["endpoint_id"] == remembered["endpoint_id"]
                worker.communicate(input=b"disconnect\n", timeout=15)
                assert worker.returncode == 0
                assert manager.store.authenticate(
                    remembered["endpoint_id"], remembered["credential"]
                )
            api(f"/api/endpoints/{remembered['endpoint_id']}/revoke", {})
            assert not manager.store.authenticate(
                remembered["endpoint_id"], remembered["credential"]
            )
        finally:
            if worker and worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive()
            app.state.application.store.close()
            fixture.shutdown()
            fixture_thread.join(timeout=5)
            fixture.server_close()
    print(
        "PASS: portable no-Python/no-PATH pairing/system/file/temporary Exit/forget/remembered reconnect"
    )


if __name__ == "__main__":
    smoke(Path(sys.argv[1]).resolve())
