"""Trusted exact-version/SHA download metadata, including unavailable source builds."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from conftest import ScriptedBackend
from fastapi.testclient import TestClient

from orion._version import __version__
from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from orion.endpoints import artifacts


@pytest.mark.parametrize("mismatch", [False, True])
def test_release_metadata_exact_build_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mismatch: bool
) -> None:
    sha = "a" * 40
    (tmp_path / ".orion-build.json").write_text(
        json.dumps({"version": __version__, "source_sha": sha})
    )
    monkeypatch.setattr(artifacts.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(artifacts, "_cached", None)
    value = {
        "version": __version__,
        "source_sha": "b" * 40 if mismatch else sha,
        "artifacts": [
            {
                "platform": platform,
                "filename": f"OrionRemote-{__version__}-{platform}{suffix}",
                "sha256": "c" * 64,
            }
            for platform, suffix in (("windows-x64", ".zip"), ("linux-x86_64", ".tar.gz"))
        ],
    }
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{artifacts.RELEASE_ROOT}/v{__version__}/worker-artifacts.json"
        return httpx.Response(200, json=value)

    monkeypatch.setattr(
        artifacts.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = asyncio.run(artifacts.compatible_artifacts())
    assert result["available"] is not mismatch
    if not mismatch:
        assert result["source_sha"] == sha and len(result["artifacts"]) == 2
        assert all(
            row["url"].startswith(artifacts.RELEASE_ROOT + f"/v{__version__}/")
            for row in result["artifacts"]
        )


def test_source_build_has_no_fabricated_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifacts.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(artifacts, "_cached", None)
    result = asyncio.run(artifacts.compatible_artifacts())
    assert not result["available"] and not result["artifacts"]
    assert result["reason"] == "artifact unavailable for this build"


def test_frozen_artifact_download_checks_access_build_and_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installation = tmp_path / "installation"
    directory = installation / "worker-artifacts"
    directory.mkdir(parents=True)
    filename = f"OrionRemote-{__version__}-windows-x64.zip"
    content = b"archive fixture payload"
    sha = "a" * 40
    build = {"version": __version__, "source_sha": sha}
    build_path = installation / "orion-build.json"
    build_path.write_text(json.dumps(build))
    (directory / "worker-artifacts.json").write_text(
        json.dumps(
            {
                **build,
                "artifacts": [
                    {
                        "platform": "windows-x64",
                        "filename": filename,
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            }
        )
    )
    archive = directory / filename
    archive.write_bytes(content)
    monkeypatch.setattr(artifacts.sys, "frozen", True, raising=False)
    monkeypatch.setattr(artifacts.sys, "executable", str(installation / "OrionBackend.exe"))
    monkeypatch.setenv("ORION_ENDPOINTS", "1")
    origin = "https://127.0.0.1:61888"
    remote = RemoteAccessConfig(True, "127.0.0.1", origin, hash_password("password"))
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]), remote_config=remote)
    url = f"{artifacts.LOCAL_ROUTE}/{filename}"
    with TestClient(app, base_url=origin) as client:
        assert client.get(url).status_code == 401
        assert (
            client.post(
                "/api/auth/login", json={"password": "password"}, headers={"Origin": origin}
            ).status_code
            == 200
        )
        item = client.get("/api/endpoints/artifacts").json()["artifacts"][0]
        assert item["local"] and item["url"] == url
        response = client.get(url)
        assert response.status_code == 200 and response.content == content
        assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'
        assert client.get(artifacts.LOCAL_ROUTE + "/server.db").status_code == 404
        archive.write_bytes(b"tampered")
        assert client.get(url).status_code == 404
        archive.write_bytes(content)
        build_path.write_text(json.dumps({**build, "source_sha": "b" * 40}))
        assert client.get(url).status_code == 404
