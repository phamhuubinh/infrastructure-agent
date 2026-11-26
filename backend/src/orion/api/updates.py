"""Read-only release notices. Installing an update is a local native operation."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

import httpx
from pydantic import BaseModel

from orion._version import __version__

RELEASE_URL = "https://api.github.com/repos/phamhuubinh/infrastructure-agent/releases/latest"
PREVIEW_URL = "https://api.github.com/repos/phamhuubinh/infrastructure-agent/releases?per_page=50"
_VERSION = re.compile(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})")


class UpdateNotice(BaseModel):
    host_version: str = __version__
    available_host_version: str | None = None
    check_available: bool = False


def release_version(release: Any, current: str, *, preview: bool = False) -> str | None:
    if not isinstance(release, dict) or release.get("draft") is not False:
        return None
    tag, assets = release.get("tag_name"), release.get("assets")
    prefix = "orion-preview-v" if preview else "v"
    if (
        release.get("prerelease") is not preview
        or not isinstance(tag, str)
        or not tag.startswith(prefix)
    ):
        return None
    version = tag[len(prefix) :]
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
        current = os.getenv("ORION_DESKTOP_RELEASE_VERSION", __version__)
        self._preview = os.getenv("ORION_DESKTOP_RELEASE_CHANNEL") == "preview"
        self._notice = UpdateNotice(
            host_version=current if _VERSION.fullmatch(current) else __version__
        )

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
                        PREVIEW_URL if self._preview else RELEASE_URL,
                        headers={"Accept": "application/vnd.github+json", "User-Agent": "Orion"},
                    ) as response,
                ):
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > 512 * 1024:
                            raise ValueError("Release response is too large")
                payload = json.loads(body)
                if not isinstance(payload, list if self._preview else dict):
                    raise ValueError("Invalid release response")
                releases = payload if self._preview else [payload]
                current = self._notice.host_version
                versions = (
                    release_version(release, current, preview=self._preview) for release in releases
                )
                self._notice = UpdateNotice(
                    host_version=current,
                    available_host_version=max(
                        (version for version in versions if version is not None),
                        key=lambda version: tuple(map(int, version.split("."))),
                        default=None,
                    ),
                    check_available=True,
                )
                delay = 900
            except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError):
                # The last confirmed notice may still be shown when GitHub is unreachable.
                self._notice = self._notice.model_copy(update={"check_available": False})
                delay = 120
            self._refresh_at = time.monotonic() + delay
            return self._notice
