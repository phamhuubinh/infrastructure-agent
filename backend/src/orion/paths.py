"""Deterministic local paths shared by the CLI and application bootstrap."""

from __future__ import annotations

import os
from pathlib import Path


def data_directory() -> Path:
    """Return Orion's persistent local data directory without creating it."""
    configured = os.getenv("ORION_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    xdg_data = os.getenv("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data).expanduser() / "orion"
    return Path.home() / ".local" / "share" / "orion"


def database_path() -> Path:
    configured = os.getenv("ORION_DATABASE_PATH")
    return Path(configured).expanduser() if configured else data_directory() / "orion.db"


def log_path() -> Path:
    configured = os.getenv("ORION_LOG_PATH")
    return Path(configured).expanduser() if configured else data_directory() / "orion.log"
