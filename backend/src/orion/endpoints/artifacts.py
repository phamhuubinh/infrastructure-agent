"""Bounded trusted release metadata for the exact installed server build."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, BinaryIO, Literal

import httpx
from pydantic import Field

from orion._version import __version__
from orion_endpoint.protocol import Strict

RELEASE_ROOT = "https://github.com/phamhuubinh/infrastructure-agent/releases/download"
LOCAL_ROUTE = "/api/endpoints/artifacts/download"
MAX_LOCAL_ARCHIVE = 128 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
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
    artifacts: list[Artifact] = Field(min_length=1, max_length=2)


def read_small_json(path: Path) -> bytes:
    with path.open("rb") as stream:
        content = stream.read(16385)
    if len(content) > 16384:
        raise ValueError("metadata_size")
    return content


def artifact_names_match(metadata: Metadata) -> bool:
    platforms = {artifact.platform for artifact in metadata.artifacts}
    if len(platforms) != len(metadata.artifacts):
        return False
    for artifact in metadata.artifacts:
        suffix = ".zip" if artifact.platform == "windows-x64" else ".tar.gz"
        if artifact.filename != f"OrionRemote-{__version__}-{artifact.platform}{suffix}":
            return False
    return True


def local_metadata() -> tuple[Path, Metadata] | None:
    if not getattr(sys, "frozen", False):
        return None
    installation = Path(sys.executable).resolve().parent
    directory = installation / "worker-artifacts"
    try:
        if directory.resolve() != directory:
            return None
        metadata = Metadata.model_validate_json(
            read_small_json(directory / "worker-artifacts.json")
        )
        build = json.loads(read_small_json(installation / "orion-build.json"))
        if (
            build["version"] != __version__
            or metadata.version != __version__
            or metadata.source_sha != build["source_sha"]
            or not artifact_names_match(metadata)
        ):
            return None
        return directory, metadata
    except (OSError, ValueError, KeyError, TypeError):
        return None


def open_local_artifact(filename: str) -> tuple[BinaryIO, int] | None:
    local = local_metadata()
    if local is None:
        return None
    directory, metadata = local
    artifact = next((entry for entry in metadata.artifacts if entry.filename == filename), None)
    if artifact is None:
        return None
    path = directory / artifact.filename
    snapshot: BinaryIO | None = None
    try:
        if path.resolve() != path or not path.is_file():
            raise ValueError("artifact_path")
        snapshot = tempfile.TemporaryFile()
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_LOCAL_ARCHIVE:
                    raise ValueError("artifact_size")
                digest.update(chunk)
                snapshot.write(chunk)
        if digest.hexdigest() != artifact.sha256:
            raise ValueError("artifact_hash")
        snapshot.seek(0)
        return snapshot, size
    except (OSError, ValueError):
        if snapshot is not None:
            snapshot.close()
        return None


async def compatible_artifacts() -> dict[str, Any]:
    global _cached
    local = local_metadata()
    if local is not None:
        directory, metadata = local
        artifacts = [
            {
                **artifact.model_dump(),
                "local": True,
                "url": f"{LOCAL_ROUTE}/{artifact.filename}",
            }
            for artifact in metadata.artifacts
            if (directory / artifact.filename).is_file()
        ]
        if artifacts:
            return {
                "version": __version__,
                "source_sha": metadata.source_sha,
                "available": True,
                "artifacts": artifacts,
            }
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
        if not artifact_names_match(metadata) or {
            artifact.platform for artifact in metadata.artifacts
        } != {
            "windows-x64",
            "linux-x86_64",
        }:
            raise ValueError("platforms")
        artifacts = []
        for artifact in metadata.artifacts:
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
