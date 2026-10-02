"""Install the archived worker, pair/connect/read through real outbound WebSocket."""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import uvicorn
from orion.api.app import create_app


def smoke(root: Path) -> None:
    manifest = json.loads((root / "worker-manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    with zipfile.ZipFile(root / manifest["wheel"]) as wheel:
        names = wheel.namelist()
        assert all(
            name.startswith(("orion_endpoint/", "orion_worker-")) for name in names
        )
        metadata = wheel.read(
            next(name for name in names if name.endswith("METADATA"))
        ).decode()
        assert "Requires-Python: >=3.12" in metadata
        assert all(
            name not in metadata.lower()
            for name in ("fastembed", "onnxruntime", "mcp", "fastapi")
        )
    with tempfile.TemporaryDirectory(
        prefix="orion worker smoke with spaces "
    ) as temporary:
        work = Path(temporary)
        destination = work / "worker install"
        subprocess.run(
            [
                sys.executable,
                str(root / "install.py"),
                "--destination",
                str(destination),
            ],
            check=True,
        )
        executable = (
            destination
            / "venv"
            / ("Scripts/orion-worker.exe" if os.name == "nt" else "bin/orion-worker")
        )
        state = work / "worker state"
        command = [str(executable), "--data", str(state)]
        subprocess.run([*command, "configure"], check=True)
        policy = json.loads((state / "policy.json").read_text())
        files = work / "allowed files"
        files.mkdir()
        policy["read_roots"] = policy["write_roots"] = [str(files)]
        (state / "policy.json").write_text(json.dumps(policy))
        os.environ["ORION_ENDPOINTS"] = "1"
        app = create_app(work / "server.db")
        loop_future: concurrent.futures.Future[asyncio.AbstractEventLoop] = (
            concurrent.futures.Future()
        )
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="error",
            ws_max_size=1_500_000,
            ws_per_message_deflate=False,
        )
        server = uvicorn.Server(config)

        async def serve() -> None:
            loop_future.set_result(asyncio.get_running_loop())
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
            port = server.servers[0].sockets[0].getsockname()[1]
            origin = f"http://127.0.0.1:{port}"

            def api(
                path: str,
                value: dict[str, object] | None = None,
                raw: bytes | None = None,
                headers: dict[str, str] | None = None,
            ) -> bytes:
                body = json.dumps(value).encode() if value is not None else raw
                request = urllib.request.Request(
                    origin + path,
                    data=body,
                    headers={
                        "Origin": origin,
                        "Content-Type": "application/json",
                        **(headers or {}),
                    },
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    return response.read()

            token = json.loads(api("/api/endpoints/pairing-tokens", {}))["token"]
            environment = {**os.environ, "ORION_PAIRING_TOKEN": token}
            subprocess.run(
                [*command, "pair", "--server", origin, "--name", "Smoke endpoint"],
                env=environment,
                check=True,
            )
            identity = json.loads((state / "identity.json").read_text())
            target = identity["endpoint_id"]
            worker = subprocess.Popen(
                [*command, "run"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            deadline = time.monotonic() + 30
            while not json.loads(api("/api/endpoints"))[0]["online"]:
                if worker.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("worker_connect_timeout")
                time.sleep(0.1)
            manager = app.state.application.endpoints
            future = asyncio.run_coroutine_threadsafe(
                manager.dispatch(target, "system.inspect", {}), loop_future.result()
            )
            assert future.result(timeout=15)["cpu_count"]
            path = str(files / "artifact smoke.txt")
            api(
                f"/api/endpoints/{target}/upload",
                raw=b"artifact-payload",
                headers={
                    "X-Endpoint-Path": path,
                    "Content-Type": "application/octet-stream",
                },
            )
            assert (
                api(f"/api/endpoints/{target}/download", {"path": path})
                == b"artifact-payload"
            )
            result = asyncio.run_coroutine_threadsafe(
                manager.dispatch(target, "file.read", {"path": path}),
                loop_future.result(),
            ).result(15)
            assert base64.b64decode(result["content_b64"]) == b"artifact-payload"
            status = subprocess.check_output([*command, "status"], text=True)
            assert target in status and identity["credential"] not in status
            if os.name != "nt":
                assert (state / "identity.json").stat().st_mode & 0o077 == 0
            api(f"/api/endpoints/{target}/revoke", {})
            assert not manager.configured(target)
        finally:
            if worker is not None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(worker.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    worker.terminate()
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
            server.should_exit = True
            thread.join(timeout=15)
            if thread.is_alive():
                raise RuntimeError("server_shutdown_timeout")
            app.state.application.store.close()
        subprocess.run(
            [
                sys.executable,
                str(root / "install.py"),
                "--destination",
                str(destination),
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(root / "install.py"),
                "--destination",
                str(destination),
                "--uninstall",
            ],
            check=True,
        )
        assert not destination.exists()
    print(
        "Worker artifact install/pair/connect/system/file/revoke/update/uninstall smoke passed"
    )


if __name__ == "__main__":
    smoke(Path(sys.argv[1]).resolve())
