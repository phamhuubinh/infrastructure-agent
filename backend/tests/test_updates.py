"""Release metadata and private maintenance admission regressions."""

import asyncio

import httpx
import pytest
from starlette.responses import Response

from orion.api import updates
from orion.cli.managed import ManagedAccess


def release(**changes):
    candidate = {
        "draft": False,
        "prerelease": False,
        "tag_name": "v0.1.10",
        "assets": [
            {"name": "Orion_0.1.10_x64-setup.exe", "size": 120, "digest": "sha256:" + "a" * 64}
        ],
    }
    candidate.update(changes)
    return candidate


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, "0.1.10"),
        ({"draft": True}, None),
        ({"prerelease": True}, None),
        ({"tag_name": "v0.1.10-preview"}, None),
        ({"assets": [{"name": "Orion_0.1.10_x64-setup.exe", "size": 120}]}, None),
        ({"assets": [{"name": "Orion_0.1.10_x64-setup.exe", "size": True}]}, None),
    ],
)
def test_selects_only_newer_stable_installer_with_digest(changes, expected):
    assert updates.release_version(release(**changes), "0.1.5") == expected
    assert updates.release_version(release(**changes), "0.1.11") is None


@pytest.mark.anyio
async def test_release_notices_share_one_bounded_fetch_and_preserve_last_notice(monkeypatch):
    calls = []

    def respond(request):
        assert str(request.url) == updates.RELEASE_URL
        assert "authorization" not in request.headers
        calls.append(request)
        return (
            httpx.Response(200, json=release())
            if len(calls) == 1
            else httpx.Response(200, content=b"z" * (512 * 1024 + 1))
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        updates.httpx,
        "AsyncClient",
        lambda **options: client(transport=httpx.MockTransport(respond), **options),
    )
    notices = updates.ReleaseNotices()
    web, mobile = await asyncio.gather(notices.get(), notices.get())
    assert web == mobile and web.available_host_version == "0.1.10" and web.check_available
    assert len(calls) == 1
    monkeypatch.setattr(notices, "_refresh_at", 0)
    failed = await notices.get()
    assert failed.available_host_version == "0.1.10" and not failed.check_available


@pytest.mark.anyio
async def test_maintenance_requires_local_transport_and_idle_host():
    release_request = asyncio.Event()
    entered = asyncio.Event()
    paused = []
    busy = False

    async def app(scope, receive, send):
        if scope["path"] == "/slow":
            entered.set()
            await release_request.wait()
        await Response(status_code=200)(scope, receive, send)

    def scheduler(value):
        paused.append(value)
        return True

    managed = ManagedAccess(
        app,
        token=b"private",
        remote_enabled=True,
        work_active=lambda: busy,
        pause_scheduler=scheduler,
    )
    async with httpx.AsyncClient(
        base_url="http://loopback", transport=httpx.ASGITransport(app=managed)
    ) as client:
        path = "/api/internal/prepare-update"
        owner = {"X-Orion-Managed-Token": "private"}
        local = {"X-Orion-Local-Maintenance": "1"}
        assert (await client.post(path, headers=owner)).status_code == 403
        assert (await client.post(path, headers=local)).status_code == 403
        assert (await client.get(path, headers=owner | local)).status_code == 403
        pending = asyncio.create_task(client.get("/slow"))
        await entered.wait()
        assert (await client.post(path, headers=owner | local)).status_code == 409
        release_request.set()
        assert (await pending).status_code == 200
        busy = True
        assert (await client.post(path, headers=owner | local)).status_code == 409
        busy = False
        assert (await client.post(path, headers=owner | local)).status_code == 204
        assert paused == [True]
        assert (await client.post("/api/sessions")).status_code == 503
        assert (await client.get("/api/health")).status_code == 503
        assert (await client.post(path, headers=owner | local)).status_code == 409
        managed._resume()
        assert paused == [True, False]
        assert (await client.get("/api/health")).status_code == 200
