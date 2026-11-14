"""Windows managed desktop local commands use the ordinary scoped process executor."""

import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from orion.api.app import create_app
from orion.integrations.ssh.transport import LOCAL_WINDOWS


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows command executor")
@pytest.mark.parametrize("managed", [False, True])
def test_local_target_is_only_available_in_managed_windows(tmp_path, managed):
    app = create_app(tmp_path / "test.db", managed_desktop=managed)
    try:
        with TestClient(app) as client:
            targets = client.get("/api/targets").json()
            local = [target for target in targets if target["target_ref"] == LOCAL_WINDOWS]
            if managed:
                assert len(local) == 1
                assert local[0]["kind"] == "local"
                assert local[0]["connected"]
                assert {"powershell", "cmd"} <= set(local[0]["command_shells"])
                assert client.get("/api/doctor").json()["local_command_unavailable_reason"] is None
            else:
                assert not local
            transport = app.state.application.commands.transport
            assert not transport.configured("local:other")
    finally:
        app.state.application.store.close()


@pytest.mark.anyio
@pytest.mark.skipif(sys.platform != "win32", reason="native Windows command executor")
async def test_local_transport_powershell_runs_in_background(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_TEST_PROVIDER_KEY", "fixture-not-for-child")
    app = create_app(tmp_path / "test.db", managed_desktop=True)
    application = app.state.application
    transport = application.commands.transport
    identity = uuid4().hex
    try:
        await transport.dispatch_command(
            LOCAL_WINDOWS,
            "command.run",
            {
                "command_id": identity,
                "shell": "powershell",
                "command": (
                    "if (Test-Path Env:ORION_TEST_PROVIDER_KEY) { exit 19 }; "
                    "[System.Net.Dns]::GetHostName()"
                ),
            },
        )
        import asyncio

        async with asyncio.timeout(15):
            while True:
                result = await transport.dispatch_command(
                    LOCAL_WINDOWS, "command.status", {"command_id": identity}
                )
                if result["state"] != "running":
                    break
                await asyncio.sleep(0.05)
        assert result["state"] == "succeeded", result
        assert result["stdout"].strip()
    finally:
        await application.commands.close()
        application.store.close()
