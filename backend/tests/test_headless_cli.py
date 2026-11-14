"""Exercise CLI output and cancellation against the actual owner routes."""

import json
import os
import runpy
import secrets
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest
from conftest import ScriptedBackend
from fastapi.testclient import TestClient

from orion import cli
from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from orion.cli import headless
from orion.cli.managed import MANAGED_HEADER, ManagedAccess
from orion.contracts import AssistantMessage, ModelTurn


@pytest.fixture(autouse=True)
def no_ambient_bearer(monkeypatch):
    monkeypatch.delenv("ORION_CLI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ORION_SERVER", raising=False)


def _transport(monkeypatch, server, intercept=None):
    client = httpx.Client

    def handle(request):
        if intercept is not None:
            intercept(request)
        response = server.request(
            request.method,
            str(request.url),
            headers=request.headers,
            content=request.read(),
        )
        server.cookies.clear()
        return httpx.Response(
            response.status_code, headers=response.headers.multi_items(), content=response.content
        )

    monkeypatch.setattr(
        headless.httpx, "Client", lambda **kw: client(**kw, transport=httpx.MockTransport(handle))
    )


def test_serve_skips_web_build_and_browser(monkeypatch, tmp_path):
    for name in ("_run_web", "build_and_package_ui", "_open_when_healthy", "_port_is_occupied"):
        monkeypatch.setattr(cli, name, lambda *args: pytest.fail("Web-only code was invoked"))
    monkeypatch.setenv("ORION_REMOTE_ACCESS", "0")
    monkeypatch.setenv("ORION_LOG_PATH", str(tmp_path / "service.log"))
    for name in ("ORION_BIND_HOST", "ORION_PUBLIC_ORIGIN", "ORION_AUTH_PASSWORD_HASH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WEB_CONCURRENCY", "5")
    monkeypatch.setattr(sys, "argv", ["orion", "serve"])

    class Server:
        def __init__(self, config):
            self.started = False
            assert config.host == "127.0.0.1" and config.port == 61888
            assert config.factory and config.workers == 1 and config.lifespan == "on"
            assert not config.access_log and not config.proxy_headers

        def run(self):
            self.started = True

    monkeypatch.setattr(cli.uvicorn, "Server", Server)
    cli.main()


@pytest.fixture
def managed_provider():
    script = Path(__file__).resolve().parents[2] / "scripts/linux/headless_smoke.py"
    provider = runpy.run_path(str(script))["Provider"]
    with ThreadingHTTPServer(("127.0.0.1", 0), provider) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/v1"
        finally:
            server.shutdown()
            thread.join()


def test_managed_serve_requires_pipe_token_and_exits_when_parent_closes(tmp_path, managed_provider):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ORION_")}
    environment["ORION_DATA_DIR"] = str(tmp_path / "data")
    environment["ORION_REMOTE_ACCESS"] = "1"
    environment["ORION_BIND_HOST"] = "0.0.0.0"
    environment["WEB_CONCURRENCY"] = "2"
    environment["ORION_MODEL_BASE_URL"] = managed_provider
    environment["ORION_MODEL_ID"] = "headless-fixture"
    token = secrets.token_urlsafe(32)
    command = [sys.executable, "-m", "orion.cli", "serve", "--managed"]
    if executable := os.getenv("ORION_TEST_MANAGED_EXE"):
        command = [executable]
        environment.update(PATH="", PYTHONPATH="", PYTHONHOME="")
    with (tmp_path / "stderr.txt").open("w+b") as diagnostics:
        with subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=diagnostics,
        ) as process:
            assert process.stdin is not None and process.stdout is not None
            try:
                process.stdin.write((token + "\n").encode())
                process.stdin.flush()
                ready = Queue()
                threading.Thread(
                    target=lambda: ready.put(process.stdout.readline()), daemon=True
                ).start()
                line = ready.get(timeout=35)
                assert line, "Managed Orion exited before readiness"
                event = json.loads(line)
                origin = urlsplit(event["origin"])
                assert event["type"] == "ready" and origin.hostname == "127.0.0.1"
                assert origin.port
                assert token not in json.dumps(event)
                with httpx.Client(base_url=event["origin"], timeout=5, trust_env=False) as client:
                    header = ("X-Orion-Managed-Token", token)
                    for headers in ([], [(header[0], "wrong")], [header, header]):
                        assert client.get("/api/health", headers=headers).status_code == 401
                    assert client.post("/api/auth/native/enrollment-codes").status_code == 401
                    doctor = client.get("/api/doctor", headers=[header]).raise_for_status().json()
                    assert doctor["model_profile_configured"]
                    assert client.post(
                        "/api/auth/native/enrollment-codes", headers=[header]
                    ).is_success
                    session = (
                        client.post("/api/sessions", headers=[header]).raise_for_status().json()
                    )
                    request = (
                        client.post(
                            f"/api/sessions/{session['session_id']}/requests",
                            headers=[header],
                            json={"content": "Managed fixture.", "client_request_id": str(uuid4())},
                        )
                        .raise_for_status()
                        .json()
                    )
                    response = client.get(
                        f"/api/requests/{request['request_id']}/stream",
                        headers=[header],
                        timeout=20,
                    ).raise_for_status()
                    assert (
                        "Headless fixture." in response.text
                        and "request.completed" in response.text
                    )
                process.stdin.close()
                assert process.wait(timeout=15) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        diagnostics.seek(0)
        assert token.encode() not in diagnostics.read()


@pytest.mark.anyio
async def test_managed_websocket_guard_does_not_forward_owner_token():
    calls = []
    messages = []

    async def app(scope, receive, send):
        calls.append(scope["headers"])

    async def receive():
        raise AssertionError("No handshake body should be read")

    async def send(message):
        messages.append(message)

    guarded = ManagedAccess(app, token=b"private")
    await guarded({"type": "websocket", "headers": []}, receive, send)
    assert messages == [{"type": "websocket.close", "code": 1008}]
    assert not calls
    await guarded(
        {"type": "websocket", "headers": [(MANAGED_HEADER, b"private"), (b"host", b"fixture")]},
        receive,
        send,
    )
    assert calls == [[(b"host", b"fixture")]]


def test_admission_retry_and_resume_do_not_replay(tmp_path, monkeypatch, capsys):
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Terminal fixture."))])
    app = create_app(tmp_path / "orion.db", backend)
    store = app.state.application.store
    store.upsert_model_config("openai_compatible", "http://model.test", "fixture", None)
    session_id = store.create_session()
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Một prompt UTF-8.", encoding="utf-8")
    client_key = str(uuid4())
    admission_calls = []

    with TestClient(app) as server:

        def intercept(request):
            if request.url.path.endswith("/requests"):
                admission_calls.append(request.read())
                if len(admission_calls) == 1:
                    admitted = server.post(str(request.url), json=json.loads(request.read()))
                    assert admitted.status_code == 202
                    raise httpx.ReadError("lost admission response")

        _transport(monkeypatch, server, intercept)
        args = [
            "run",
            "--session",
            session_id,
            "--client-request-id",
            client_key,
            "--prompt-file",
            str(prompt),
            "--json",
        ]
        headless.run_client_command(args)
        records = list(map(json.loads, capsys.readouterr().out.splitlines()))
        assert records[0] == {
            "kind": "submission",
            "session_id": session_id,
            "client_request_id": client_key,
        }
        assert len(admission_calls) == 2 and admission_calls[0] == admission_calls[1]
        request_id = records[1]["request_id"]
        assert records[-1] == {"kind": "status", "request_id": request_id, "status": "completed"}
        event = next(row for row in records if row.get("type") == "assistant.message")
        assert event["payload"]["content"] == "Terminal fixture."
        headless.run_client_command(
            ["request", "watch", request_id, "--after", event["event_id"], "--json"]
        )
        resumed = list(map(json.loads, capsys.readouterr().out.splitlines()))
        assert all(row.get("event_id") != event["event_id"] for row in resumed)
        assert resumed[-1]["status"] == "completed" and len(backend.calls) == 1


def test_interrupt_reserves_cancelled_nonce_before_admission(tmp_path, monkeypatch, capsys):
    backend = ScriptedBackend([])
    app = create_app(tmp_path / "orion.db", backend)
    with TestClient(app) as server:

        def interrupt(request):
            if request.url.path.endswith("/requests"):
                raise KeyboardInterrupt

        _transport(monkeypatch, server, interrupt)
        prompt = tmp_path / "prompt.txt"
        prompt.write_text("cancel this exact prompt", encoding="utf-8")
        with pytest.raises(SystemExit) as error:
            headless.run_client_command(["chat", "--prompt-file", str(prompt), "--json"])
        assert error.value.code == 130
        submitted, cancelled = map(json.loads, capsys.readouterr().out.splitlines())
        assert cancelled["kind"] == "cancellation" and cancelled["status"] == "cancelled"
        repeated = server.post(
            f"/api/sessions/{submitted['session_id']}/requests",
            json={
                "content": prompt.read_text(encoding="utf-8"),
                "client_request_id": submitted["client_request_id"],
            },
        )
        assert repeated.json()["request_id"] == cancelled["request_id"]
        assert repeated.json()["status"] == "cancelled" and not backend.calls


@pytest.mark.parametrize("auth", ["--login", "--enroll"])
def test_remote_owner_session_is_revoked_after_command(tmp_path, monkeypatch, capsys, auth):
    origin = "https://orion.example"
    password = "fixture owner password"
    app = create_app(
        tmp_path / "orion.db",
        ScriptedBackend([]),
        remote_config=RemoteAccessConfig(True, "127.0.0.1", origin, hash_password(password)),
    )
    with TestClient(app, base_url=origin) as server:
        if auth == "--enroll":
            runtime = app.state.application
            secret = runtime.native_auth.create_enrollment(runtime.access.current_principal()).code
        else:
            secret = password
        monkeypatch.setattr(headless.getpass, "getpass", lambda _: secret)
        calls = []
        _transport(monkeypatch, server, lambda request: calls.append(request))
        headless.run_client_command(["doctor", "--server", origin, auth, "--json"])
        output = capsys.readouterr()
        assert secret not in output.out + output.err
        assert json.loads(output.out)["observation"] == "configuration"
        assert calls[0].headers.get("authorization") is None
        if auth == "--enroll":
            assert calls[-1].url.path == "/api/auth/native/logout"
            header = {"Authorization": calls[-2].headers["Authorization"]}
        else:
            assert calls[-1].url.path == "/api/auth/logout"
            assert calls[-1].headers["Origin"] == origin
            header = {"Cookie": calls[-2].headers["Cookie"]}
        assert server.get("/api/doctor", headers=header).status_code == 401


@pytest.mark.parametrize(
    "origin",
    [
        "http://orion.example",
        "https://user@orion.example",
        "https://orion.example/",
        "https://orion.example?",
        "https://orion.example:443",
        "http://127.0.0.1:61888\n",
    ],
)
def test_refuses_unsafe_or_noncanonical_origins(origin):
    with pytest.raises(headless.ClientError):
        headless._origin(origin)


def test_managed_host_preserves_remote_cookie_and_owner_pipe(tmp_path):
    from fastapi.testclient import TestClient

    from orion.access.remote import RemoteAccessConfig, hash_password
    from orion.api.app import create_app

    origin = "https://orion.example.test"
    app = create_app(
        tmp_path / "host.db",
        remote_config=RemoteAccessConfig(True, "127.0.0.1", origin, hash_password("test secret")),
    )
    app.add_middleware(ManagedAccess, token=b"owner-pipe", remote_enabled=True)
    try:
        with TestClient(app, base_url=origin) as browser:
            assert browser.get("/api/sessions").status_code == 401
            assert (
                browser.post("/api/sessions", headers={"X-Orion-Managed-Token": "fake"}).status_code
                == 401
            )
            assert (
                browser.post("/api/auth/login", json={"password": "test secret"}).status_code == 403
            )
            headers = {"X-Orion-Managed-Token": "owner-pipe"}
            session = browser.post("/api/sessions", headers=headers).raise_for_status().json()
            login = browser.post(
                "/api/auth/login", headers={"Origin": origin}, json={"password": "test secret"}
            )
            assert login.status_code == 200
            assert "Secure" in login.headers["set-cookie"]
            session_id = session["session_id"]
            assert browser.get(f"/api/sessions/{session_id}").status_code == 200
            code = (
                browser.post("/api/auth/native/enrollment-codes", headers=headers)
                .raise_for_status()
                .json()["code"]
            )
            pair = (
                browser.post(
                    "/api/auth/native/enroll",
                    json={"code": code, "name": "Fixture desktop", "platform": "windows"},
                )
                .raise_for_status()
                .json()
            )
            refreshed = (
                browser.post(
                    "/api/auth/native/refresh", json={"refresh_token": pair["refresh_token"]}
                )
                .raise_for_status()
                .json()
            )
            native = {"Authorization": f"Bearer {refreshed['access_token']}"}
            assert browser.get(f"/api/sessions/{session_id}", headers=native).is_success
            assert browser.post("/api/auth/native/logout", headers=native).is_success
            assert browser.get(f"/api/sessions/{session_id}", headers=native).status_code == 401
    finally:
        app.state.application.store.close()
