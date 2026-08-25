"""Isolated installer/CLI smoke that never touches an Orion user prefix or data."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _get(url: str) -> tuple[int, str]:
    with urlopen(Request(url), timeout=1) as response:  # noqa: S310 - isolated loopback smoke.
        return response.status, response.read().decode("utf-8")


def _wait_for(url: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if _get(url)[0] == 200:
                return
        except OSError:
            time.sleep(0.05)
    raise SystemExit(f"Orion did not start at {url}")


def main() -> None:
    repository = Path(__file__).parents[2]
    try:
        _free_port()
    except PermissionError:
        # Some restricted CI sandboxes prohibit every loopback bind. The same
        # smoke runs in normal local/CI environments; unit coverage still
        # exercises the ASGI routes without a socket.
        print("operations check skipped: loopback sockets are unavailable")
        return
    with tempfile.TemporaryDirectory(prefix="orion-operations-") as temporary:
        root = Path(temporary)
        prefix, data, home = root / "install", root / "data", root / "home"
        launcher = home / ".local" / "bin" / "orion"
        launcher.parent.mkdir(parents=True)
        launcher.write_text(
            "#!/usr/bin/env bash\nexec ~/projects/Orion_agent/scripts/orion \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        environment = {
            **os.environ,
            "HOME": str(home),
            "PATH": f"{launcher.parent}:{os.environ['PATH']}",
            "ORION_PYTHON": sys.executable,
            "ORION_TEST_SECRET_TOKEN": "operations-marker-secret",
        }
        subprocess.run(
            [
                str(repository / "install.sh"),
                "--prefix",
                str(prefix),
                "--no-dev",
                "--global-launcher",
            ],
            check=True,
            cwd=repository,
            env=environment,
            stdout=subprocess.DEVNULL,
        )
        command = [str(launcher)]
        help_output = subprocess.check_output([*command, "--help"], env=environment, text=True)
        log_output = subprocess.check_output(
            [*command, "log", "--data-dir", str(data)], env=environment, text=True
        )
        if "web" not in help_output or "log" not in help_output:
            raise SystemExit("installed CLI did not expose web/log commands")
        if not (prefix / ".orion-ui" / "index.html").is_file():
            raise SystemExit("installed Orion did not contain packaged frontend assets")
        if "scripts/orion" in launcher.read_text(encoding="utf-8"):
            raise SystemExit("managed launcher retained stale scripts/orion reference")
        if str(data / "orion.db") not in log_output:
            raise SystemExit("installed CLI did not use the isolated data directory")
        if "operations-marker-secret" in log_output:
            raise SystemExit("installed CLI exposed a configured marker secret")

        port = _free_port()
        marker = root / "browser-opened"
        browser = root / "mock-browser"
        browser.write_text(
            "#!/usr/bin/env bash\nprintf opened > \"$ORION_BROWSER_MARKER\"\n",
            encoding="utf-8",
        )
        browser.chmod(0o755)
        no_open_environment = {
            **environment,
            "ORION_BROWSER_MARKER": str(marker),
            # This mock makes an unexpected browser launch observable without
            # ever starting a real browser.
            "BROWSER": str(browser),
        }
        process = subprocess.Popen(
            [*command, "web", "--no-open", "--data-dir", str(data), "--port", str(port)],
            env=no_open_environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_for(f"{base_url}/api/health")
            root_status, root_html = _get(f"{base_url}/")
            asset = next((prefix / ".orion-ui" / "assets").glob("*.js"))
            asset_status, _ = _get(f"{base_url}/assets/{asset.name}")
            health_status, health_body = _get(f"{base_url}/api/health")
            session_request = Request(f"{base_url}/api/sessions", method="POST")
            with urlopen(session_request, timeout=1) as response:  # noqa: S310 - loopback smoke.
                session_id = json.loads(response.read())["session_id"]
        finally:
            process.terminate()
            process.wait(timeout=5)
        if root_status != 200 or "<title>Orion</title>" not in root_html:
            raise SystemExit("root URL did not serve the packaged Orion UI")
        if asset_status != 200 or health_status != 200 or '"status":"ok"' not in health_body:
            raise SystemExit("packaged root/API smoke failed")
        if marker.exists():
            raise SystemExit("--no-open unexpectedly launched a browser")

        # Starting through the bare managed launcher proves it maps to web and
        # preserves the data created by the first local process.
        port = _free_port()
        process = subprocess.Popen(
            [*command],
            env={
                **environment,
                "BROWSER": str(browser),
                "ORION_BROWSER_MARKER": str(root / "bare-browser-opened"),
                "ORION_PORT": str(port),
                "ORION_DATA_DIR": str(data),
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_for(f"{base_url}/")
            if _get(f"{base_url}/api/sessions/{session_id}")[0] != 200:
                raise SystemExit("restart through bare orion did not preserve local data")
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
