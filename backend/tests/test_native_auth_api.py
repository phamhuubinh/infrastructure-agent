"""Native owner bearer permissions do not weaken browser/worker authority boundaries."""

import json

import httpx
import pytest
from conftest import ScriptedBackend

from orion.access import Principal
from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from orion.contracts.native_auth import NativeEnrollmentInput


@pytest.mark.anyio
async def test_browser_issued_code_native_exchange_rotation_revoke_and_no_cookie_fallback(tmp_path):
    origin = "https://native-owner.test"
    api = create_app(
        tmp_path / "orion.db",
        ScriptedBackend([]),
        remote_config=RemoteAccessConfig(
            True, "127.0.0.1", origin, hash_password("fixture-password")
        ),
    )
    transport = httpx.ASGITransport(app=api)
    try:
        async with (
            httpx.AsyncClient(transport=transport, base_url=origin) as browser,
            httpx.AsyncClient(transport=transport, base_url=origin) as native,
        ):
            assert (
                await browser.post("/api/auth/native/enrollment-codes", headers={"origin": origin})
            ).status_code == 401
            await browser.post(
                "/api/auth/login", json={"password": "fixture-password"}, headers={"origin": origin}
            )
            assert (await browser.post("/api/auth/native/enrollment-codes")).status_code == 403
            code = await browser.post(
                "/api/auth/native/enrollment-codes", headers={"origin": origin}
            )
            assert code.status_code == 200 and "no-store" in code.headers["cache-control"]
            values = {"code": code.json()["code"], "name": "Native fixture", "platform": "android"}
            wrong = await native.post(
                "/api/auth/native/enroll", json=values, headers={"origin": "https://other.test"}
            )
            assert wrong.status_code == 403
            response = await native.post("/api/auth/native/enroll", json=values)
            assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
            tokens = response.json()
            headers = {"Authorization": "Bearer " + tokens["access_token"]}
            assert (await native.get("/api/sessions", headers=headers)).status_code == 200
            created = await native.post("/api/sessions", headers=headers)
            assert created.status_code == 201
            assert (await native.post("/api/auth/native/enroll", json=values)).status_code == 401
            # A valid owner cookie cannot rescue an invalid explicit bearer.
            denied = await browser.get("/api/sessions", headers={"Authorization": "Bearer invalid"})
            assert denied.status_code == 401 and denied.headers["x-orion-auth-expired"] == "1"
            refresh = await native.post(
                "/api/auth/native/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
            assert refresh.status_code == 200
            assert (await native.get("/api/sessions", headers=headers)).status_code == 401
            updated = refresh.json()
            updated_headers = {"Authorization": "Bearer " + updated["access_token"]}
            sessions = await native.get("/api/auth/native/sessions", headers=updated_headers)
            assert sessions.status_code == 200 and sessions.json()[0]["name"] == "Native fixture"
            for secret in (
                updated["access_token"],
                updated["refresh_token"],
                tokens["refresh_token"],
            ):
                assert secret not in sessions.text
            logout = await native.post("/api/auth/native/logout", headers=updated_headers)
            assert logout.status_code == 200
            assert (await native.get("/api/sessions", headers=updated_headers)).status_code == 401
            assert (
                await native.post(
                    "/api/auth/native/refresh", json={"refresh_token": updated["refresh_token"]}
                )
            ).status_code == 401
    finally:
        api.state.application.store.close()


@pytest.mark.anyio
async def test_native_credential_body_is_bounded_closed_json_and_never_echoes_secret(tmp_path):
    api = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            secret = "orion_enroll_" + "x" * 43
            values = {"code": secret, "name": "native", "platform": "ios"}
            for body, media, status in [
                (json.dumps(values), "text/plain", 415),
                (json.dumps({**values, "principal_id": "forged"}), "application/json", 422),
                ('{"code":"one","code":"two"}', "application/json", 422),
                ("x" * 2049, "application/json", 413),
                (json.dumps(values), "application/json", 401),
            ]:
                result = await http.post(
                    "/api/auth/native/enroll", content=body, headers={"content-type": media}
                )
                assert result.status_code == status and secret not in result.text
            assert (
                await http.get("/api/sessions", headers={"Authorization": "Bearer invalid"})
            ).status_code == 401
            # Worker credentials retain their own route/validator; native owner
            # authentication must not authorize a worker's device end boundary.
            code = (await http.post("/api/auth/native/enrollment-codes")).json()["code"]
            pair = (
                await http.post("/api/auth/native/enroll", json={**values, "code": code})
            ).json()
            worker = await http.post(
                "/api/endpoints/" + "a" * 32 + "/end",
                headers={"Authorization": "Bearer " + pair["access_token"]},
            )
            assert worker.status_code in {401, 403, 404}
    finally:
        api.state.application.store.close()


@pytest.mark.anyio
async def test_native_endpoint_views_bind_session_family_and_cannot_be_used_as_worker_credentials(
    tmp_path, monkeypatch
):
    from test_endpoints import connection, paired

    monkeypatch.setenv("ORION_ENDPOINTS", "1")
    api = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    application = api.state.application
    service, manager = application.native_auth, application.endpoints
    target = paired(manager.store)["endpoint_id"]
    socket = connection(manager, target)
    manager.store.update_connection(target, socket.connection.hello, "connected")
    pairs = []
    for name in ("first", "second"):
        code = service.create_enrollment(application.access.current_principal())
        pairs.append(
            service.enroll(NativeEnrollmentInput(code=code.code, name=name, platform="windows"))
        )
    prefix = f"/api/endpoints/{target}/desktop"
    first = {"Authorization": "Bearer " + pairs[0].access_token}
    second = {"Authorization": "Bearer " + pairs[1].access_token}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            assert (await http.get("/api/endpoints", headers=first)).status_code == 200
            view = await http.post(prefix + "/session", headers=first)
            assert view.status_code == 200
            identity = view.json()["session_id"]
            assert (
                await http.post(prefix + "/stop", json={"session_id": identity}, headers=second)
            ).status_code == 403
            assert (
                await http.post(
                    prefix + "/stop",
                    json={"session_id": identity},
                    headers={"Origin": "http://test"},
                )
            ).status_code == 403
            renewed = service.refresh(pairs[0].refresh_token)
            assert (
                await http.post(
                    prefix + "/stop",
                    json={"session_id": identity},
                    headers={"Authorization": "Bearer " + renewed.access_token},
                )
            ).status_code == 200
            worker = await http.post(f"/api/endpoints/{target}/end", headers=second)
            assert worker.status_code == 401
            assert manager.store.get(target)["revoked_at"] is None
    finally:
        application.store.close()


@pytest.mark.anyio
async def test_foreign_owner_and_duplicate_bearer_headers_fail_closed(tmp_path):
    api = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    service = api.state.application.native_auth
    try:
        foreign = service.create_enrollment(Principal("foreign", "elsewhere"))
        pair = service.enroll(
            NativeEnrollmentInput(code=foreign.code, name="foreign", platform="linux")
        )
        local = service.create_enrollment(Principal("local", "local"))
        own = service.enroll(NativeEnrollmentInput(code=local.code, name="own", platform="linux"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            assert (
                await http.get(
                    "/api/sessions", headers={"Authorization": "Bearer " + pair.access_token}
                )
            ).status_code == 401
            duplicate = await http.get(
                "/api/sessions",
                headers=[
                    ("Authorization", "Bearer " + own.access_token),
                    ("Authorization", "Bearer invalid"),
                ],
            )
            assert duplicate.status_code == 401
            sessions = (
                await http.get(
                    "/api/auth/native/sessions",
                    headers={"Authorization": "Bearer " + own.access_token},
                )
            ).json()
            assert [item["name"] for item in sessions] == ["own"]
    finally:
        api.state.application.store.close()
