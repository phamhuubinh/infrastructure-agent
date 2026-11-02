"""MCP operator actions stay behind owner authentication and exact Origin checks."""

import json

import httpx
import pytest
from conftest import ScriptedBackend
from test_mcp import FakeClient, config, manager_for

from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.cli.mcp import run_mcp_command


@pytest.mark.anyio
async def test_owner_api_actions_preserve_snapshot_and_require_authentication(tmp_path):
    fake = FakeClient()
    manager = manager_for(fake)
    registrations = await manager.start()
    app = build_application(
        tmp_path / "orion.db",
        ScriptedBackend([]),
        mcp_manager=manager,
        mcp_registrations=registrations,
    )
    origin = "https://mcp-owner.test"
    api = create_app(
        application=app,
        remote_config=RemoteAccessConfig(
            True, "127.0.0.1", origin, hash_password("fixture-password")
        ),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url=origin
        ) as http:
            for action in ("test", "connect", "disconnect"):
                assert (
                    await http.post(
                        f"/api/mcp/servers/fixture/{action}", headers={"origin": origin}
                    )
                ).status_code == 401
            assert (await http.get("/api/mcp/doctor")).status_code == 401
            assert (
                await http.post(
                    "/api/auth/login",
                    json={"password": "fixture-password"},
                    headers={"origin": origin},
                )
            ).status_code == 200
            assert (await http.post("/api/mcp/servers/fixture/disconnect")).status_code == 403
            before = app.registry.definitions()
            digest = manager.status()[0]["snapshot_sha256"]
            for action, state in (
                ("test", "connected"),
                ("disconnect", "closed"),
                ("connect", "connected"),
            ):
                result = await http.post(
                    f"/api/mcp/servers/fixture/{action}", headers={"origin": origin}
                )
                assert result.status_code == 200 and result.json()["state"] == state
                assert result.json()["snapshot_sha256"] == digest
            assert app.registry.definitions() == before and fake.calls == 0
            assert (await http.get("/api/mcp/doctor")).json()["healthy"]
            assert (
                await http.post("/api/mcp/servers/missing/test", headers={"origin": origin})
            ).status_code == 404
    finally:
        await manager.close()
        app.store.close()


def test_offline_mcp_list_does_not_resolve_or_print_credentials(tmp_path, monkeypatch, capsys):
    path = tmp_path / "mcp.json"
    raw = config(env_from={"SECRET_VALUE": "PRIVATE_MCP_TEST_VALUE"})
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("ORION_MCP_CONFIG", str(path))
    monkeypatch.delenv("PRIVATE_MCP_TEST_VALUE", raising=False)
    run_mcp_command(["list"])
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "servers": [{"server_id": "fixture", "transport": "stdio", "tools": ["read_item"]}]
    }
    with pytest.raises(SystemExit, match="MCP operation failed"):
        run_mcp_command(["doctor"])


def test_offline_mcp_test_opens_and_closes_real_stdio_without_invoking_tools(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(config()), encoding="utf-8")
    monkeypatch.setenv("ORION_MCP_CONFIG", str(path))
    run_mcp_command(["test", "fixture"])
    result = json.loads(capsys.readouterr().out)
    assert result["healthy"] and result["servers"][0]["state"] == "connected"
    assert "closed on completion" in result["scope"]
