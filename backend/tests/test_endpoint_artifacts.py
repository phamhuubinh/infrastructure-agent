"""Trusted exact-version/SHA download metadata, including unavailable source builds."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from orion._version import __version__
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
