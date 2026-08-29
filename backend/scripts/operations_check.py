"""Isolated installer and fixed-address web lifecycle proof."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
PORT = 61888
URL = f"http://{HOST}:{PORT}"


def _get(url: str) -> tuple[int, str]:
    try:
        with urlopen(Request(url), timeout=1) as response:  # noqa: S310 - isolated loopback smoke.
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8")


def _wait_for_health() -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            status, body = _get(f"{URL}/api/health")
            if status == 200 and json.loads(body).get("identity") == "orion":
                return
        except (OSError, ValueError):
            time.sleep(0.05)
    raise SystemExit(f"Orion did not become healthy at {URL}")


def _wait_for_file(path: Path) -> bool:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if path.is_file():
            return True
        time.sleep(0.05)
    return False


def _packaged_text(directory: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in directory.rglob("*")
        if path.is_file()
    )


def _loopback_available() -> bool:
    deadline = time.monotonic() + 5
    while True:
        try:
            with socket.socket() as listener:
                listener.bind((HOST, PORT))
            return True
        except PermissionError:
            print("operations socket check skipped: loopback sockets are unavailable")
            return False
        except OSError as error:
            if error.errno != 98:
                raise
            if time.monotonic() >= deadline:
                print("operations socket check skipped: port 61888 is already in use")
                return False
            time.sleep(0.1)


def _asset_reference(shell: str, suffix: str) -> str:
    match = re.search(rf'/(assets/[^" ]+{re.escape(suffix)})', shell)
    if match is None:
        raise SystemExit(f"installed SPA shell did not reference a generated {suffix} asset")
    return match.group(1)


def _assert_marker(marker: Path, count: int) -> None:
    deadline = time.monotonic() + 3
    expected = "opened" * count
    while time.monotonic() < deadline:
        if marker.is_file():
            actual = marker.read_text(encoding="utf-8")
            if actual == expected:
                return
            if len(actual) > len(expected):
                break
        time.sleep(0.05)
    if not marker.is_file():
        raise SystemExit("Orion did not request the operating-system URL opener")
    raise SystemExit("Orion requested the URL opener an unexpected number of times")


def _terminate(process: subprocess.Popen[str]) -> None:
    process.terminate()
    process.wait(timeout=5)


def _exercise_socket_lifecycle(command: list[str], environment: dict[str, str], root: Path) -> None:
    marker = root / "browser-opened"
    process = subprocess.Popen(
        command,
        env={**environment, "ORION_BROWSER_MARKER": str(marker)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_for_health()
        _assert_marker(marker, 1)
        root_status, root_html = _get(f"{URL}/")
        shell = root_html
        javascript = _asset_reference(shell, ".js")
        stylesheet = _asset_reference(shell, ".css")
        asset_status, _ = _get(f"{URL}/{javascript}")
        css_status, _ = _get(f"{URL}/{stylesheet}")
        route_status, route_html = _get(f"{URL}/projects")
        health_status, health_body = _get(f"{URL}/api/health")
        missing_api_status, missing_api_body = _get(f"{URL}/api/not-a-route")
        session_request = Request(f"{URL}/api/sessions", method="POST")
        with urlopen(session_request, timeout=1) as response:  # noqa: S310 - isolated loopback smoke.
            session_id = json.loads(response.read())["session_id"]

        second = subprocess.run(
            command,
            env={**environment, "ORION_BROWSER_MARKER": str(marker)},
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if second.returncode != 0 or "already running" not in second.stdout:
            raise SystemExit("a second orion invocation did not reuse the healthy Orion server")
        _assert_marker(marker, 2)
    finally:
        _terminate(process)

    if root_status != 200 or "<title>Orion</title>" not in root_html:
        raise SystemExit("root URL did not serve the packaged Orion UI")
    if asset_status != 200 or css_status != 200:
        raise SystemExit("a real packaged Orion frontend asset was not served")
    if route_status != 200 or route_html != root_html:
        raise SystemExit("a client-side route refresh did not return the SPA shell")
    if health_status != 200 or json.loads(health_body).get("identity") != "orion":
        raise SystemExit("health did not identify the Orion server")
    if missing_api_status != 404 or "<html" in missing_api_body.lower():
        raise SystemExit("an unknown API route received SPA HTML")

    restarted = subprocess.Popen(
        [*command, "web"],
        env={**environment, "ORION_BROWSER_MARKER": str(marker)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_for_health()
        _assert_marker(marker, 3)
        session_status, _ = _get(f"{URL}/api/sessions/{session_id}")
        if session_status != 200:
            raise SystemExit("local data did not survive a normal Orion restart")
    finally:
        _terminate(restarted)

    with socket.socket() as unrelated:
        unrelated.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        unrelated.bind((HOST, PORT))
        unrelated.listen()
        rejected = subprocess.run(
            command,
            env={**environment, "ORION_BROWSER_MARKER": str(marker)},
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    if (
        rejected.returncode == 0
        or "Port 61888 is already in use by another application." not in rejected.stderr
    ):
        raise SystemExit("a non-Orion service on 61888 was not rejected clearly")
    if marker.read_text(encoding="utf-8") != "opened" * 3:
        raise SystemExit("a non-Orion service caused a browser-open request")


def main() -> None:
    repository = Path(__file__).parents[2]
    if not _loopback_available():
        return
    with tempfile.TemporaryDirectory(prefix="orion-operations-") as temporary:
        root = Path(temporary)
        prefix, data, home = root / "install", root / "data", root / "home"
        launcher = home / ".local" / "bin" / "orion"
        launcher.parent.mkdir(parents=True)
        launcher.write_text(
            '#!/usr/bin/env bash\nexec ~/projects/Orion_agent/scripts/orion "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        opener = launcher.parent / "xdg-open"
        opener.write_text(
            '#!/usr/bin/env bash\nprintf opened >> "$ORION_BROWSER_MARKER"\n',
            encoding="utf-8",
        )
        opener.chmod(0o755)
        environment = {
            **os.environ,
            "HOME": str(home),
            "PATH": f"{launcher.parent}:{os.environ['PATH']}",
            "ORION_DATA_DIR": str(data),
            "ORION_PYTHON": sys.executable,
            "ORION_TEST_SECRET_TOKEN": "operations-marker-secret",
            "ORION_API_KEY": "operations-ui-secret-marker",
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
        help_output = subprocess.check_output([*command, "help"], env=environment, text=True)
        rejected_help = subprocess.run(
            [*command, "--help"], env=environment, text=True, capture_output=True, check=False
        )
        log_output = subprocess.check_output([*command, "log"], env=environment, text=True)
        if (
            help_output
            != (
                "Orion\n\nUsage:\n"
                "  orion          Start Orion\n"
                "  orion web      Start Orion\n"
                "  orion log      Show Orion logs\n"
                "  orion help     Show this help\n"
            )
            or rejected_help.returncode == 0
        ):
            raise SystemExit("installed CLI help surface is not minimal")
        packaged_ui = prefix / ".orion-ui"
        shell = packaged_ui / "_shell.html"
        if not shell.is_file() or not (packaged_ui / "orion-icon.png").is_file():
            raise SystemExit("installed Orion did not contain the real packaged frontend")
        shell_html = shell.read_text(encoding="utf-8")
        for asset in (_asset_reference(shell_html, ".js"), _asset_reference(shell_html, ".css")):
            if not (packaged_ui / asset).is_file():
                raise SystemExit("installed SPA shell referenced a missing generated asset")
        if "operations-ui-secret-marker" in _packaged_text(packaged_ui):
            raise SystemExit("installed UI exposed an API-key test marker")
        if "scripts/orion" in launcher.read_text(encoding="utf-8"):
            raise SystemExit("managed launcher retained stale scripts/orion reference")
        if str(data / "orion.db") not in log_output or "operations-marker-secret" in log_output:
            raise SystemExit("orion log did not use sanitized isolated local data")

        _exercise_socket_lifecycle(command, environment, root)


if __name__ == "__main__":
    main()
