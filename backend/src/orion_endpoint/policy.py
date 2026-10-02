"""Worker-owned ceilings. Neither model nor server can widen them."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import Field

from orion_endpoint.protocol import Strict


class ApplicationAlias(Strict):
    executable: str = Field(min_length=1, max_length=2048)
    fixed_args: list[str] = Field(default_factory=list, max_length=16)
    allow_args: bool = False


class Policy(Strict):
    read_roots: list[str] = Field(default_factory=list, max_length=16)
    write_roots: list[str] = Field(default_factory=list, max_length=16)
    applications: dict[str, ApplicationAlias] = Field(default_factory=dict, max_length=16)
    terminate: bool = False
    clipboard_read: bool = False
    clipboard_write: bool = False
    browser: bool = False
    browser_download_directory: str | None = Field(default=None, max_length=2048)
    desktop_capture: bool = False
    desktop_control: bool = False
    max_fps: int = Field(default=2, ge=1, le=5)
    max_resolution: int = Field(default=1280, ge=320, le=1920)

    @classmethod
    def load(cls, path: Path) -> Policy:
        if path.stat().st_size > 64 * 1024:
            raise ValueError("policy_size")
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def path(self, raw: str, *, write: bool = False) -> Path:
        candidate = Path(raw)
        if not candidate.is_absolute() or ".." in candidate.parts:
            raise PermissionError("policy_denied")
        # Windows alternate data streams and device namespaces are never file API targets.
        if os.name == "nt" and (":" in raw[2:] or raw.startswith(("\\\\", "//"))):
            raise PermissionError("policy_denied")
        resolved = candidate.resolve()
        roots = self.write_roots if write else self.read_roots
        for root in roots:
            base = Path(root).resolve(strict=True)
            if resolved.is_relative_to(base) and (not write or resolved != base):
                return resolved
        raise PermissionError("policy_denied")
