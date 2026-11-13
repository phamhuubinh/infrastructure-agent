"""Exercise an installed Linux wheel with a local provider and real POSIX signals."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Provider(BaseHTTPRequestHandler):
    waiting = threading.Event()
    release = threading.Event()

    def do_POST(self) -> None:
        assert self.path == "/v1/chat/completions"
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["model"] == "headless-fixture" and body["stream"]
        hold = body["messages"][-1].get("content") == "Wait for SIGINT."
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if hold:
            self.waiting.set()
            self.release.wait(timeout=45)
            return
        self.reply(body)

    def reply(self, body: dict) -> None:
        for value in (
            {"choices": [{"index": 0, "delta": {"content": "Headless fixture."}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ):
            self.wfile.write(f"data: {json.dumps(value)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


def smoke(cli: Path, root: Path, provider_port: int) -> None:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ORION_")
        and name
        not in {"DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    tools = root / "tools"
    tools.mkdir()
    marker = root / "unexpected-tool"
    for name in ("xdg-open", "gio", "node", "npm"):
        guard = tools / name
        guard.write_text(
            '#!/bin/sh\nprintf "%s" "$0" >> "$ORION_SMOKE_MARKER"\nexit 87\n'
        )
        guard.chmod(0o755)
    env.update(
        ORION_SMOKE_MARKER=str(marker),
        ORION_DATA_DIR=str(root / "data"),
        ORION_UI_DIR=str(root / "no-ui"),
        ORION_MODEL_BASE_URL=f"http://127.0.0.1:{provider_port}/v1",
        ORION_MODEL_ID="headless-fixture",
        PATH=str(tools) + os.pathsep + env["PATH"],
    )

    def command(
        *args: str, input: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(cli), *args],
            env=env,
            cwd=root,
            input=input,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            check=False,
        )

    with (root / "serve.log").open("w+", encoding="utf-8") as log:
        for start in range(2):
            with subprocess.Popen(
                [str(cli), "serve"], env=env, cwd=root, stderr=log
            ) as server:
                try:
                    for _ in range(100):
                        if server.poll() is not None:
                            raise RuntimeError(
                                "Headless service exited before readiness."
                            )
                        ready = command("doctor", "--json")
                        if ready.returncode == 0:
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Headless service did not reach readiness.")
                    assert json.loads(ready.stdout)["model_profile_configured"]
                    if start:
                        sessions = command("session", "list", "--json")
                        assert sessions.returncode == 0 and json.loads(sessions.stdout)
                        continue
                    prompt = root / "prompt.txt"
                    prompt.write_text("Send the fixture response.", encoding="utf-8")
                    result = command("run", "--prompt-file", str(prompt), "--json")
                    assert result.returncode == 0, (result.stdout, result.stderr)
                    rows = [json.loads(line) for line in result.stdout.splitlines()]
                    assert rows[-1]["status"] == "completed"
                    assert any(
                        row.get("payload", {}).get("content") == "Headless fixture."
                        for row in rows
                    )
                    with subprocess.Popen(
                        [str(cli), "chat", "--json"],
                        env=env,
                        cwd=root,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding="utf-8",
                    ) as pending:
                        try:
                            assert pending.stdin is not None
                            pending.stdin.write("Wait for SIGINT.")
                            pending.stdin.close()
                            pending.stdin = None
                            assert Provider.waiting.wait(timeout=25), (
                                "Provider was never reached"
                            )
                            pending.send_signal(signal.SIGINT)
                            stdout, stderr = pending.communicate(timeout=30)
                            assert pending.returncode == 130, (stdout, stderr)
                        finally:
                            if pending.poll() is None:
                                pending.kill()
                    records = [json.loads(line) for line in stdout.splitlines()]
                    request_id = next(
                        row["request_id"]
                        for row in records
                        if row["kind"] == "cancellation"
                    )
                    for _ in range(20):
                        state = command("request", "status", request_id, "--json")
                        assert state.returncode == 0, state.stderr
                        if json.loads(state.stdout)["status"] == "cancelled":
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError(
                            "SIGINT did not cancel the admitted request."
                        )
                except BaseException:
                    log.seek(0)
                    print(log.read(), file=sys.stderr)
                    raise
                finally:
                    if server.poll() is None:
                        server.send_signal(signal.SIGINT)
                        try:
                            assert server.wait(timeout=30) == 0
                        except subprocess.TimeoutExpired:
                            server.kill()
                            raise
    assert not marker.exists(), "Headless service invoked a display or build tool."


def main() -> None:
    if sys.platform != "linux" or len(sys.argv) != 2:
        raise SystemExit(
            "Usage on Linux: python scripts/linux/headless_smoke.py /path/to/orion"
        )
    cli = Path(sys.argv[1]).resolve(strict=True)
    with (
        ThreadingHTTPServer(("127.0.0.1", 0), Provider) as provider,
        tempfile.TemporaryDirectory(prefix="orion headless smoke ") as directory,
    ):
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        try:
            smoke(cli, Path(directory), provider.server_port)
        finally:
            Provider.release.set()
            provider.shutdown()
            thread.join()
    print(
        "PASS: installed Linux CLI, local provider fixture, SIGINT and data after restart"
    )


if __name__ == "__main__":
    main()
