"""Bounded trusted release metadata for the exact installed server build."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import Field

from orion._version import __version__
from orion_endpoint.protocol import Strict

RELEASE_ROOT = "https://github.com/phamhuubinh/infrastructure-agent/releases/download"
_cached: tuple[float, dict[str, Any]] | None = None


class Artifact(Strict):
    filename: str = Field(
        max_length=128, pattern=r"^OrionRemote-[0-9.a-z]+-(windows-x64\.zip|linux-x86_64\.tar\.gz)$"
    )
    platform: Literal["windows-x64", "linux-x86_64"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Metadata(Strict):
    version: str = Field(max_length=32)
    source_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifacts: list[Artifact] = Field(min_length=2, max_length=2)


async def compatible_artifacts() -> dict[str, Any]:
    global _cached
    if _cached and time.monotonic() - _cached[0] < 300:
        return _cached[1]
    result: dict[str, Any] = {
        "version": __version__,
        "available": False,
        "reason": "artifact unavailable for this build",
        "artifacts": [],
    }
    try:
        build_path = Path(sys.prefix) / ".orion-build.json"
        if build_path.stat().st_size > 4096:
            raise ValueError("build_metadata")
        build = json.loads(build_path.read_text(encoding="utf-8"))
        if build["version"] != __version__:
            raise ValueError("version")
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            async with client.stream(
                "GET", f"{RELEASE_ROOT}/v{__version__}/worker-artifacts.json"
            ) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 16384:
                        raise ValueError("metadata_size")
                    content.extend(chunk)
        metadata = Metadata.model_validate_json(content)
        if metadata.version != __version__ or metadata.source_sha != build["source_sha"]:
            raise ValueError("source_mismatch")
        if {artifact.platform for artifact in metadata.artifacts} != {
            "windows-x64",
            "linux-x86_64",
        }:
            raise ValueError("platforms")
        artifacts = []
        for artifact in metadata.artifacts:
            suffix = ".zip" if artifact.platform == "windows-x64" else ".tar.gz"
            if artifact.filename != f"OrionRemote-{__version__}-{artifact.platform}{suffix}":
                raise ValueError("filename")
            artifacts.append(
                {
                    **artifact.model_dump(),
                    "url": f"{RELEASE_ROOT}/v{__version__}/{artifact.filename}",
                }
            )
        result = {
            "version": __version__,
            "source_sha": metadata.source_sha,
            "available": True,
            "artifacts": artifacts,
        }
    except (OSError, ValueError, KeyError, httpx.HTTPError):
        pass
    _cached = (time.monotonic(), result)
    return result
