"""Remote HTTP boundary invariants and the authoritative API route inventory."""

from __future__ import annotations

import getpass
import time
import warnings

import httpx
import pytest
from argon2 import PasswordHasher, Type
from conftest import ScriptedBackend
from fastapi.routing import APIRoute

from orion.access.remote import (
    MAX_SESSIONS,
    SESSION_SECONDS,
    BrowserSessions,
    RemoteAccessConfig,
    hash_password,
)
from orion.api.app import PROTECTED_API_ROUTES, PUBLIC_API_ROUTES, create_app
from orion.cli import _run_web, main
from orion.contracts import AssistantMessage, ModelTurn

ORIGIN = "https://orion.example.test"
PASSWORD = "correct horse battery staple"


def _assert_no_framing(response: httpx.Response) -> None:
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert response.headers["x-frame-options"] == "DENY"


def _remote(monkeypatch: pytest.MonkeyPatch) -> RemoteAccessConfig:
    monkeypatch.setenv("ORION_REMOTE_ACCESS", "1")
    monkeypatch.setenv("ORION_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("ORION_AUTH_PASSWORD_HASH", hash_password(PASSWORD))
    return RemoteAccessConfig.from_environment()


def test_route_policy_inventory_is_exact(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    actual = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in route.methods
    }
    assert PUBLIC_API_ROUTES.isdisjoint(PROTECTED_API_ROUTES)
    from orion.api.endpoints import DEVICE_API_ROUTES, PAIRING_API_ROUTES

    assert (
        actual == PUBLIC_API_ROUTES | PROTECTED_API_ROUTES | PAIRING_API_ROUTES | DEVICE_API_ROUTES
    )


def test_default_bind_and_fail_closed_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    assert RemoteAccessConfig.from_environment() == RemoteAccessConfig(False, "127.0.0.1")
    monkeypatch.setenv("ORION_BIND_HOST", "0.0.0.0")
    with pytest.raises(ValueError, match="incomplete"):
        RemoteAccessConfig.from_environment()
    with pytest.raises(SystemExit, match="incomplete"):
        _run_web()
    monkeypatch.setenv("ORION_REMOTE_ACCESS", "1")
    with pytest.raises(ValueError, match="requires"):
        RemoteAccessConfig.from_environment()
    configured = _remote(monkeypatch)
    assert configured.bind_host == "0.0.0.0" and configured.enabled


@pytest.mark.parametrize(
    "origin",
    [
        "http://orion.example.test",
        "https://orion.example.test/path",
        "https://user@orion.example.test",
        "https://orion.example.test?x=1",
        "https://orion.example.test#fragment",
        "https://orion.example.test:",
        "https://orion.example.test:443",
        "https://orion.example.test:08443",
    ],
)
def test_bad_origin_fails_startup(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    _remote(monkeypatch)
    monkeypatch.setenv("ORION_PUBLIC_ORIGIN", origin)
    with pytest.raises(ValueError):
        RemoteAccessConfig.from_environment()


def test_invalid_hash_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    _remote(monkeypatch)
    monkeypatch.setenv("ORION_AUTH_PASSWORD_HASH", "$argon2id$broken")
    with pytest.raises(ValueError, match="invalid"):
        RemoteAccessConfig.from_environment()


def test_hash_command_only_prints_encoded_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr("orion.cli.getpass.getpass", lambda _: next(answers))
    monkeypatch.setattr("sys.argv", ["orion", "auth", "hash-password"])
    main()
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out.startswith("$argon2id$")
    assert PASSWORD not in output.out
    assert PasswordHasher(type=Type.ID).verify(output.out.strip(), PASSWORD)


def test_hash_command_rejects_echoing_fallback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def echoing_fallback(_: str) -> str:
        warnings.warn("echoing fallback", getpass.GetPassWarning, stacklevel=2)
        return PASSWORD

    monkeypatch.setattr("orion.cli.getpass.getpass", echoing_fallback)
    monkeypatch.setattr("sys.argv", ["orion", "auth", "hash-password"])
    with pytest.raises(SystemExit, match="hides password"):
        main()
    assert capsys.readouterr().out == ""


def test_argon2id_hash_and_bounded_expiring_store() -> None:
    encoded = hash_password(PASSWORD)
    assert encoded.startswith("$argon2id$")
    assert PasswordHasher(type=Type.ID).verify(encoded, PASSWORD)
    moment = [1000.0]
    sessions = BrowserSessions(encoded, clock=lambda: moment[0])
    assert sessions.login("wrong") is None
    first = sessions.login(PASSWORD)
    assert first is not None
    token, expiry = first
    assert token not in sessions._tokens  # noqa: SLF001 - digest-only store contract.
    assert sessions.expiry(token) == expiry
    for _ in range(MAX_SESSIONS + 4):
        assert sessions.login(PASSWORD) is not None
    assert len(sessions._tokens) == MAX_SESSIONS  # noqa: SLF001
    moment[0] = expiry + 1
    assert sessions.expiry(token) is None
    assert not sessions._tokens  # noqa: SLF001


def test_login_throttle_resets_without_permanent_lockout() -> None:
    moment = [1000.0]
    sessions = BrowserSessions(hash_password(PASSWORD), clock=lambda: moment[0])
    for _ in range(10):
        assert sessions.login("wrong") is None
    assert sessions.login(PASSWORD) is None
    moment[0] += 61
    assert sessions.login(PASSWORD) is not None


@pytest.mark.anyio
async def test_remote_login_origin_cookie_protection_logout_and_restart(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    config = _remote(monkeypatch)
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]), remote_config=config)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await client.get("/api/health")).json() == {"status": "ok", "identity": "orion"}
        assert (await client.get("/api/models")).status_code == 401
        assert (await client.get("/api/projects")).status_code == 401
        assert (await client.get("/api/requests/fake/events")).status_code == 401
        assert (await client.get("/api/sessions/fake/timeline")).status_code == 401
        assert (
            await client.post(
                "/api/projects/fake/documents",
                headers={"Origin": ORIGIN},
                files={"file": ("notes.txt", b"fact", "text/plain")},
            )
        ).status_code == 401
        assert (
            await client.post(
                "/api/sessions/fake/requests/fake/tool-authorizations/fake",
                headers={"Origin": ORIGIN},
                json={"decision": "allow"},
            )
        ).status_code == 401
        assert (await client.get("/openapi.json")).status_code == 401
        assert (await client.get("/api/unknown")).status_code == 404
        assert (await client.get("/docs/oauth2-redirect")).status_code == 401
        assert (await client.post("/api/sessions", headers={"Origin": ORIGIN})).status_code == 401
        assert (
            await client.post("/api/auth/login", json={"password": PASSWORD})
        ).status_code == 403
        assert (
            await client.post(
                "/api/auth/login",
                headers={"Origin": "https://evil.test"},
                json={"password": PASSWORD},
            )
        ).status_code == 403
        forged = {
            "Origin": "https://evil.test",
            "Host": "orion.example.test",
            "X-Forwarded-Host": "orion.example.test",
            "Forwarded": "host=orion.example.test",
        }
        assert (
            await client.post("/api/auth/login", headers=forged, json={"password": PASSWORD})
        ).status_code == 403
        wrong = await client.post(
            "/api/auth/login", headers={"Origin": ORIGIN}, json={"password": "wrong"}
        )
        assert wrong.status_code == 401 and wrong.json() == {"detail": "Invalid credentials."}
        malformed = await client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            content=b'{"password":"secret","extra":1}',
        )
        assert malformed.status_code == 400 and "secret" not in malformed.text
        oversized = await client.post(
            "/api/auth/login", headers={"Origin": ORIGIN}, content=b"x" * 4096
        )
        assert oversized.status_code == 400 and "xxx" not in oversized.text
        response = await client.post(
            "/api/auth/login", headers={"Origin": ORIGIN}, json={"password": PASSWORD}
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert "Max-Age=43200" in cookie
        assert "orion_session" not in response.text and PASSWORD not in response.text
        assert response.json()["authenticated"] is True
        assert "Access-Control-Allow-Origin" not in response.headers
        assert (await client.get("/api/auth/session")).json()["authenticated"] is True
        assert (await client.get("/api/models")).status_code == 200
        assert (
            await client.get("/api/models", headers={"Cookie": "orion_session=invalid"})
        ).status_code == 401
        assert (await client.get("/api/projects")).status_code == 200
        assert app.state.application.access.current_principal().principal_id == "local"
        assert app.state.application.access.current_principal().workspace_id == "local"
        openapi = await client.get("/openapi.json")
        assert openapi.status_code == 200
        assert config.password_hash not in openapi.text
        assert PASSWORD not in openapi.text
        assert (await client.post("/api/projects", json={"name": "A"})).status_code == 403
        created = await client.post("/api/projects", headers={"Origin": ORIGIN}, json={"name": "A"})
        assert created.status_code == 201
        project_id = created.json()["project_id"]
        project_document = await client.post(
            f"/api/projects/{project_id}/documents",
            headers={"Origin": ORIGIN},
            files={"file": ("requirements.txt", b"project fact", "text/plain")},
        )
        assert project_document.status_code == 201
        other_project = await client.post(
            "/api/projects", headers={"Origin": ORIGIN}, json={"name": "B"}
        )
        assert other_project.status_code == 201
        document_id = project_document.json()["document"]["document_id"]
        other_id = other_project.json()["project_id"]
        assert (
            await client.get(f"/api/projects/{other_id}/documents/{document_id}")
        ).status_code == 404
        conversation = await client.post("/api/sessions", headers={"Origin": ORIGIN})
        assert conversation.status_code == 201
        session_id = conversation.json()["session_id"]
        assert app.state.application.store.session_identity(session_id)["principal_id"] == "local"
        assert app.state.application.store.session_identity(session_id)["workspace_id"] == "local"
        assert (
            await client.post(
                f"/api/sessions/{session_id}/attachments",
                headers={"Origin": ORIGIN},
                files={"file": ("notes.txt", b"fact", "text/plain")},
            )
        ).status_code == 201
        assert (
            await client.post(
                f"/api/sessions/{session_id}/requests/unknown/tool-authorizations/unknown",
                headers={"Origin": ORIGIN},
                json={"decision": "deny"},
            )
        ).status_code == 404
        assert (
            await client.post("/api/auth/logout", headers={"Origin": ORIGIN})
        ).status_code == 204
        assert (await client.get("/api/models")).status_code == 401
        assert (await client.get("/api/auth/session")).json()["authenticated"] is False
        await client.post(
            "/api/auth/login", headers={"Origin": ORIGIN}, json={"password": PASSWORD}
        )
        restarted = create_app(tmp_path / "orion.db", ScriptedBackend([]), remote_config=config)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted), base_url=ORIGIN, cookies=client.cookies
        ) as after:
            assert (await after.get("/api/models")).status_code == 401


@pytest.mark.anyio
async def test_remote_static_bootstrap_and_server_expiry(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    frontend = tmp_path / "ui"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "_shell.html").write_text("<html>Orion login shell</html>")
    (assets / "app.js").write_text("login-ui")
    (frontend / "secret.txt").write_text("private-marker")
    config = _remote(monkeypatch)
    app = create_app(
        tmp_path / "orion.db", ScriptedBackend([]), ui_directory=frontend, remote_config=config
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        root = await client.get("/")
        assert "Orion login shell" in root.text
        _assert_no_framing(root)
        login_shell = await client.get("/projects/example")
        assert "Orion login shell" in login_shell.text
        _assert_no_framing(login_shell)
        assert (await client.get("/assets/app.js")).text == "login-ui"
        assert (await client.get("/secret.txt")).status_code == 404
        assert (await client.get("/assets/../secret.txt")).status_code == 404
        assert "Orion login shell" not in (await client.get("/api/does-not-exist")).text
        protected = await client.get("/api/models")
        assert protected.status_code == 401
        _assert_no_framing(protected)
        rejected_origin = await client.post("/api/auth/login", json={"password": PASSWORD})
        assert rejected_origin.status_code == 403
        _assert_no_framing(rejected_origin)
        login_response = await client.post(
            "/api/auth/login", headers={"Origin": ORIGIN}, json={"password": PASSWORD}
        )
        assert login_response.status_code == 200
        _assert_no_framing(login_response)
        protected = await client.get("/api/models")
        assert protected.status_code == 200
        _assert_no_framing(protected)
        app.state.browser_sessions._clock = lambda: time.time() + SESSION_SECONDS + 1
        assert (await client.get("/api/models")).status_code == 401
        assert (await client.get("/api/auth/session")).json()["authenticated"] is False


@pytest.mark.anyio
async def test_authenticated_stream_is_available(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    config = _remote(monkeypatch)
    backend = ScriptedBackend(
        [ModelTurn(assistant=AssistantMessage(content="Streamed."))], deltas=[["Stream", "ed."]]
    )
    app = create_app(tmp_path / "orion.db", backend, remote_config=config)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        await client.post(
            "/api/auth/login", headers={"Origin": ORIGIN}, json={"password": PASSWORD}
        )
        configured = await client.post(
            "/api/models",
            headers={"Origin": ORIGIN},
            json={
                "provider_type": "openai_compatible",
                "base_url": "http://model.test/v1",
                "model_id": "fake",
            },
        )
        assert configured.status_code == 201
        session = (await client.post("/api/sessions", headers={"Origin": ORIGIN})).json()[
            "session_id"
        ]
        stream = await client.post(
            f"/api/sessions/{session}/messages/stream",
            headers={"Origin": ORIGIN},
            json={"content": "Hello"},
        )
        assert stream.status_code == 200
        assert '"type": "assistant.message"' in stream.text


@pytest.mark.anyio
async def test_local_mode_requires_no_login(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/models")).status_code == 200
        assert (await client.get("/api/auth/session")).json() == {
            "remote_access": False,
            "authenticated": True,
            "expires_at": None,
        }
        assert app.state.application.access.current_principal().principal_id == "local"
        assert app.state.application.access.current_principal().workspace_id == "local"
