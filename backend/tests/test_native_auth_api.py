"""Native owner bearer permissions do not weaken browser/worker authority boundaries."""

import base64
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from conftest import ScriptedBackend

from orion.access import Principal
from orion.access.owner import OwnerAuth, totp_code
from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from orion.cli.managed import ManagedAccess
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


@pytest.mark.anyio
async def test_managed_owner_mfa_enrollment_and_remote_session_revocation(tmp_path, monkeypatch):
    origin = "https://orion.example.test"
    same_origin = {"Origin": origin}
    password = "fixture password for single owner"
    moment = [1_800_000_000]

    def owner_at_fixture_time(store):
        return OwnerAuth(store, clock=lambda: moment[0])

    monkeypatch.setattr("orion.api.app.OwnerAuth", owner_at_fixture_time)
    api = create_app(
        tmp_path / "orion.db",
        ScriptedBackend([]),
        managed_desktop=True,
        remote_config=RemoteAccessConfig(True, "127.0.0.1", origin),
    )
    legacy = api.state.application.native_auth
    old_grant = legacy.create_enrollment(api.state.application.access.current_principal())
    old_tokens = legacy.enroll(
        NativeEnrollmentInput(code=old_grant.code, name="Legacy client", platform="android")
    )
    old_bearer = {"Authorization": "Bearer " + old_tokens.access_token}
    legacy_refresh = {"refresh_token": old_tokens.refresh_token}
    transport = httpx.ASGITransport(
        app=ManagedAccess(api, token=b"fixture-local-token", remote_enabled=True)
    )
    try:
        async with (
            httpx.AsyncClient(transport=transport, base_url=origin) as browser,
            httpx.AsyncClient(transport=transport, base_url=origin) as native,
            httpx.AsyncClient(
                transport=transport,
                base_url="http://127.0.0.1",
                headers={"X-Orion-Managed-Token": "fixture-local-token"},
            ) as desktop,
        ):
            owner_path = "/api/auth/owner"
            login_path = "/api/auth/login"
            enroll_path = "/api/auth/native/enroll"
            codes_path = "/api/auth/native/enrollment-codes"
            assert (await browser.get(owner_path)).status_code == 403
            assert (await browser.get("/api/sessions")).status_code == 401
            assert (await desktop.post(codes_path)).status_code == 403
            assert (await native.get("/api/sessions", headers=old_bearer)).status_code == 401
            assert (
                await native.post("/api/auth/native/refresh", json=legacy_refresh)
            ).status_code == 401
            setup = await desktop.post(owner_path + "/setup/start", json={"password": password})
            assert setup.status_code == 200 and "no-store" in setup.headers["cache-control"]
            payload = setup.json()
            secret = base64.b32decode(parse_qs(urlsplit(payload["otpauth_uri"]).query)["secret"][0])
            code = totp_code(secret, moment[0] // 30)
            confirmation = {"setup_id": payload["setup_id"], "code": code}
            assert (await desktop.get(owner_path)).json() == {"configured": False}
            assert (
                await desktop.post(
                    owner_path + "/setup/confirm", json=confirmation | {"code": "invalid"}
                )
            ).status_code == 422
            confirmed = await desktop.post(owner_path + "/setup/confirm", json=confirmation)
            assert confirmed.status_code == 200
            recovery = confirmed.json()["recovery_codes"]
            assert (await desktop.get(owner_path)).json() == {"configured": True}
            assert (await native.get("/api/sessions", headers=old_bearer)).status_code == 401

            assert (await browser.get("/api/auth/session")).json()["mfa_required"] is True
            assert (
                await browser.post(login_path, headers=same_origin, json={"password": password})
            ).status_code == 401
            assert (
                await browser.post(
                    login_path, headers=same_origin, json={"password": password, "code": code}
                )
            ).status_code == 401
            moment[0] += 30
            login = {"password": password, "code": totp_code(secret, moment[0] // 30)}
            assert (await browser.post(login_path, json=login)).status_code == 403
            assert (
                await browser.post(login_path, headers=same_origin, json=login)
            ).status_code == 200
            assert (await browser.get("/api/sessions")).status_code == 200
            assert (await browser.get(owner_path)).status_code == 403
            assert (await browser.post(codes_path, headers=same_origin)).status_code == 403

            grant = await desktop.post(codes_path)
            assert grant.status_code == 200
            values = {
                "code": grant.json()["code"],
                "name": "Android fixture",
                "platform": "android",
            }
            assert (await native.post(enroll_path, json=values)).status_code == 401
            verified = values | {"password": password, "totp_code": recovery[0]}
            response = await native.post(enroll_path, json=verified)
            assert response.status_code == 200
            assert (await native.post(enroll_path, json=verified)).status_code == 401
            assert (
                await browser.post(
                    login_path,
                    headers=same_origin,
                    json={"password": password, "code": recovery[0]},
                )
            ).status_code == 401
            tokens = response.json()
            bearer = {"Authorization": "Bearer " + tokens["access_token"]}
            assert (await native.get("/api/sessions", headers=bearer)).status_code == 200
            assert (await native.get(owner_path, headers=bearer)).status_code == 403

            revoked = await desktop.post(
                owner_path + "/revoke-all", json={"password": password, "code": recovery[1]}
            )
            assert revoked.status_code == 200
            new_password = "new fixture password for single owner"
            updated = await desktop.post(
                owner_path + "/password",
                json={
                    "current_password": password,
                    "new_password": new_password,
                    "code": recovery[2],
                },
            )
            assert updated.status_code == 200
            rotation = await desktop.post(
                owner_path + "/totp/start", json={"password": new_password, "code": recovery[3]}
            )
            assert rotation.status_code == 200
            rotated = rotation.json()
            secret = base64.b32decode(parse_qs(urlsplit(rotated["otpauth_uri"]).query)["secret"][0])
            confirmation = {
                "setup_id": rotated["setup_id"],
                "code": totp_code(secret, moment[0] // 30),
            }
            confirmed = await desktop.post(owner_path + "/totp/confirm", json=confirmation)
            assert confirmed.status_code == 200
            new_recovery = confirmed.json()["recovery_codes"][0]
            assert new_recovery not in recovery
            assert (
                await browser.post(
                    login_path,
                    headers=same_origin,
                    json={"password": new_password, "code": recovery[4]},
                )
            ).status_code == 401
            assert (
                await browser.post(
                    login_path,
                    headers=same_origin,
                    json={"password": password, "code": new_recovery},
                )
            ).status_code == 401
            assert (await browser.get("/api/sessions")).status_code == 401
            assert (await native.get("/api/sessions", headers=bearer)).status_code == 401
            assert (
                await native.post(
                    "/api/auth/native/refresh", json={"refresh_token": tokens["refresh_token"]}
                )
            ).status_code == 401
    finally:
        api.state.application.store.close()
