"""Verify a Windows Orion desktop executable with the bundled UI and backend."""

from __future__ import annotations

import ctypes
import hashlib
import os
import runpy
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack, closing
from ctypes import wintypes
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener, urlopen

import uvicorn
from orion.access import LocalAccessAdapter
from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def close_window(pid: int) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    owned = []

    @callback
    def collect(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            if title.value == "Orion":
                owned.append(hwnd)
        return True

    assert user32.EnumWindows(collect, 0) and owned, "No Tauri window found"
    assert len(owned) == 1, owned
    assert user32.PostMessageW(owned[0], 0x0010, 0, 0), ctypes.get_last_error()


def remote_fixture(stack: ExitStack, database: Path) -> tuple[str, str]:
    listener = stack.enter_context(socket.socket())
    listener.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    config = RemoteAccessConfig(
        True, "127.0.0.1", origin, hash_password("fixture-only")
    )
    app = create_app(database, remote_config=config)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", proxy_headers=False))
    thread = threading.Thread(
        target=lambda: server.run(sockets=[listener]), daemon=True
    )
    thread.start()
    stack.callback(app.state.application.store.close)
    stack.callback(thread.join, 15)
    stack.callback(setattr, server, "should_exit", True)
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            raise RuntimeError("Native enrollment fixture failed to start")
        time.sleep(0.05)
    owner = LocalAccessAdapter().current_principal()
    code = app.state.application.native_auth.create_enrollment(owner)
    return origin, code.code


def check_remote(page: Page, origin: str, code: str) -> None:
    def vault(command: str):
        return page.evaluate(
            "([command, origin]) => window.__TAURI_INTERNALS__.invoke(command, { origin })",
            [command, origin],
        )

    settings = page.get_by_role("link", name="Cài đặt", exact=True)
    settings.click(timeout=12000)
    page.get_by_label("Tên server").fill("Fixture remote")
    page.get_by_label("Địa chỉ server").fill(origin)
    page.get_by_role("button", name="Lưu server", exact=True).click()
    page.get_by_role("button", name="Mở Fixture remote", exact=True).click()
    try:
        page.get_by_label("Mã kết nối").fill(code, timeout=12000)
        page.get_by_role("button", name="Kết nối bằng mã", exact=True).click()
        settings.wait_for(timeout=15000)
        assert vault("orion_vault_get")["token_type"] == "Bearer"
        page.get_by_role("button", name="Sign out", exact=True).click()
        page.get_by_label("Mã kết nối").wait_for(timeout=12000)
        page.wait_for_function(
            """async (origin) =>
                (await window.__TAURI_INTERNALS__.invoke("orion_vault_get", { origin })) === null
            """,
            arg=origin,
            timeout=12000,
        )
    finally:
        vault("orion_vault_clear")
    page.get_by_role("button", name="Mở Orion trên máy này", exact=True).click()
    settings.wait_for(timeout=12000)


def smoke(executable: Path, data_dir: Path, log_path: Path) -> None:
    assert not data_dir.exists(), f"Test refuses existing app data: {data_dir}"
    provider_type = runpy.run_path(str(ROOT / "scripts/linux/headless_smoke.py"))[
        "Provider"
    ]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    with ExitStack() as stack:
        provider = stack.enter_context(
            ThreadingHTTPServer(("127.0.0.1", 0), provider_type)
        )
        directory = os.getenv("ORION_SMOKE_WEBVIEW2_DATA_DIR") or stack.enter_context(
            tempfile.TemporaryDirectory(prefix="orion-webview-smoke-")
        )
        remote_data = stack.enter_context(
            tempfile.TemporaryDirectory(prefix="orion-desktop-remote-")
        )
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join)
        stack.callback(provider.shutdown)
        stack.callback(provider_type.release.set)
        webview_data = Path(directory).resolve(strict=True)
        port_file = webview_data / "EBWebView" / "DevToolsActivePort"
        environment = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(("ORION_", "WEBVIEW2_"))
        }
        environment.update(
            PATH="",
            ORION_MODEL_ID="headless-fixture",
            ORION_MODEL_BASE_URL=f"http://127.0.0.1:{provider.server_port}/v1",
            WEBVIEW2_USER_DATA_FOLDER=str(webview_data),
            WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=0",
        )
        loopback = build_opener(ProxyHandler({}))
        with log_path.open("wb") as log:
            proc = subprocess.Popen(
                [str(executable)],
                env=environment,
                startupinfo=startup,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 60
                endpoint = None
                startup_error = None
                while endpoint is None and time.monotonic() < deadline:
                    assert proc.poll() is None, (
                        f"Tauri exited before WebView readiness: {proc.returncode}"
                    )
                    try:
                        port = int(
                            port_file.read_text(encoding="utf-8").splitlines()[0]
                        )
                        if not 0 < port <= 65535:
                            raise ValueError("Invalid WebView2 debugger port")
                        for host in ("127.0.0.1", "[::1]"):
                            candidate = f"http://{host}:{port}"
                            try:
                                with loopback.open(
                                    candidate + "/json/version", timeout=1
                                ) as response:
                                    assert response.status == 200
                                endpoint = candidate
                                break
                            except OSError as error:
                                startup_error = error
                    except (OSError, ValueError, IndexError) as error:
                        startup_error = error
                    if endpoint is None:
                        time.sleep(0.25)
                if endpoint is None:
                    print(
                        f"WebView2 startup timeout for Orion PID {proc.pid}: {startup_error}"
                    )
                    for image in (
                        "Orion.exe",
                        "OrionBackend.exe",
                        "msedgewebview2.exe",
                    ):
                        subprocess.run(
                            ["tasklist.exe", "/FI", f"IMAGENAME eq {image}"],
                            check=False,
                            timeout=10,
                        )
                    raise RuntimeError(
                        "WebView2 DevTools endpoint never appeared"
                    ) from startup_error
                with sync_playwright() as playwright:
                    browser = playwright.chromium.connect_over_cdp(
                        endpoint, timeout=12000
                    )
                    context = browser.contexts[0]
                    page = (
                        context.pages[0]
                        if context.pages
                        else context.wait_for_event("page", timeout=10000)
                    )
                    page.on(
                        "console",
                        lambda message: (
                            print(f"console {message.type}: {message.text}")
                            if message.type == "error"
                            else None
                        ),
                    )
                    page.on("pageerror", lambda error: print(f"pageerror: {error}"))
                    page.wait_for_url("**/_shell.html", timeout=12000)
                    try:
                        composer = page.get_by_role("textbox", name="Chat input")
                        composer.wait_for(timeout=20000)
                    except Exception:
                        print(page.locator("body").inner_text()[:1500])
                        print(
                            page.evaluate(
                                'window.__TAURI_INTERNALS__?.invoke("orion_host")'
                            )
                        )
                        raise
                    host = page.evaluate(
                        'window.__TAURI_INTERNALS__.invoke("orion_host")'
                    )
                    origin = host["managedOrigin"]
                    assert origin.startswith("http://127.0.0.1:")
                    managed_port = int(origin.rsplit(":", 1)[1])
                    try:
                        urlopen(origin + "/api/health", timeout=3)
                    except HTTPError as error:
                        assert error.code == 401
                    else:
                        raise AssertionError(
                            "Managed backend accepted an unauthenticated request"
                        )
                    second = subprocess.run(
                        [str(executable)],
                        env=environment,
                        startupinfo=startup,
                        stdout=log,
                        stderr=log,
                        timeout=15,
                        check=False,
                    )
                    assert second.returncode == 0 and proc.poll() is None
                    assert (
                        page.evaluate(
                            'window.__TAURI_INTERNALS__.invoke("orion_host")'
                        )["managedOrigin"]
                        == origin
                    )
                    composer.fill("Send the fixture response.")
                    page.get_by_role("button", name="Send message").click(timeout=15000)
                    page.get_by_text("Headless fixture.", exact=True).wait_for(
                        timeout=30000
                    )
                    composer.fill("Wait for SIGINT.")
                    page.get_by_role("button", name="Send message").click(timeout=15000)
                    assert provider_type.waiting.wait(20), (
                        "Hold prompt never reached the local provider"
                    )
                    page.get_by_role("button", name="Stop generating").click(
                        timeout=10000
                    )
                    page.get_by_role("button", name="Send message").wait_for(
                        timeout=15000
                    )
                    check_remote(
                        page,
                        *remote_fixture(
                            stack, Path(remote_data).resolve(strict=True) / "orion.db"
                        ),
                    )
                close_window(proc.pid)
                assert proc.wait(timeout=20) == 0
                with socket.socket() as probe:
                    probe.settimeout(2)
                    assert probe.connect_ex(("127.0.0.1", managed_port)) != 0
                db_path = data_dir / "managed/orion.db"
                with closing(
                    sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
                ) as db:
                    rows = db.execute(
                        "SELECT status FROM requests ORDER BY created_at"
                    ).fetchall()
                assert rows == [("completed",), ("cancelled",)], rows
            finally:
                if proc.poll() is None:
                    try:
                        close_window(proc.pid)
                        proc.wait(timeout=16)
                    except (AssertionError, subprocess.TimeoutExpired):
                        proc.terminate()
                        proc.wait(timeout=10)
    print(
        "Tauri WebView2 smoke passed: trusted SPA, single instance, credential IPC, chat/Stop, clean shutdown"
    )
    print("Desktop exe SHA-256:", hashlib.sha256(executable.read_bytes()).hexdigest())


if __name__ == "__main__":
    if sys.platform != "win32" or len(sys.argv) != 3:
        raise SystemExit(
            "Usage on Windows: python scripts/desktop/smoke.py Orion.exe desktop.log"
        )
    smoke(
        Path(sys.argv[1]).resolve(strict=True),
        Path(os.environ["LOCALAPPDATA"]) / "io.orion.desktop",
        Path(sys.argv[2]),
    )
