"""Read-only release notices. Installing an update is a local native operation."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx
from pydantic import BaseModel

from orion._version import __version__

RELEASE_URL = "https://api.github.com/repos/phamhuubinh/infrastructure-agent/releases/latest"
_VERSION = re.compile(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})")


class UpdateNotice(BaseModel):
    host_version: str = __version__
    available_host_version: str | None = None
    check_available: bool = False


def release_version(release: Any, current: str) -> str | None:
    if not isinstance(release, dict) or release.get("draft") is not False:
        return None
    tag, assets = release.get("tag_name"), release.get("assets")
    if (
        release.get("prerelease") is not False
        or not isinstance(tag, str)
        or not tag.startswith("v")
    ):
        return None
    version = tag[1:]
    target = _VERSION.fullmatch(version)
    installed = _VERSION.fullmatch(current)
    if target is None or installed is None or not isinstance(assets, list):
        return None
    if tuple(map(int, target.groups())) <= tuple(map(int, installed.groups())):
        return None
    for asset in assets:
        if (
            isinstance(asset, dict)
            and asset.get("name") == f"Orion_{version}_x64-setup.exe"
            and isinstance(asset.get("digest"), str)
            and re.fullmatch(r"sha256:[a-f0-9]{64}", asset["digest"])
            and type(asset.get("size")) is int
            and 0 < asset["size"] <= 512 * 1024 * 1024
        ):
            return version
    return None


class ReleaseNotices:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._refresh_at = 0.0
        self._notice = UpdateNotice()

    async def get(self) -> UpdateNotice:
        async with self._lock:
            if time.monotonic() < self._refresh_at:
                return self._notice
            # Bound requests even on a stalled connection or an oversized response.
            try:
                async with (
                    asyncio.timeout(5),
                    httpx.AsyncClient(follow_redirects=False, trust_env=False) as client,
                    client.stream(
                        "GET",
                        RELEASE_URL,
                        headers={"Accept": "application/vnd.github+json", "User-Agent": "Orion"},
                    ) as response,
                ):
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > 512 * 1024:
                            raise ValueError("Release response is too large")
                release = json.loads(body)
                if not isinstance(release, dict):
                    raise ValueError("Invalid release response")
                self._notice = UpdateNotice(
                    available_host_version=release_version(release, __version__),
                    check_available=True,
                )
                delay = 900
            except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError):
                # The last confirmed notice may still be shown when GitHub is unreachable.
                self._notice = self._notice.model_copy(update={"check_available": False})
                delay = 120
            self._refresh_at = time.monotonic() + delay
            return self._notice
