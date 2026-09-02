"""Deterministic local paths and process configuration shared by Orion."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGED_UI_SHELL = "_shell.html"
ORION_HOST = "127.0.0.1"
ORION_PORT = 61888
ORION_HEALTH_IDENTITY = "orion"
DEFAULT_MAX_DOCUMENT_UPLOAD_BYTES = 4 * 1024 * 1024


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


def document_upload_limit() -> int:
    """Return the configured raw document upload bound in bytes."""
    configured = os.getenv("ORION_MAX_DOCUMENT_UPLOAD_BYTES")
    if configured is None:
        return DEFAULT_MAX_DOCUMENT_UPLOAD_BYTES
    try:
        value = int(configured)
    except ValueError as error:
        raise ValueError("ORION_MAX_DOCUMENT_UPLOAD_BYTES must be an integer") from error
    if value < 1:
        raise ValueError("ORION_MAX_DOCUMENT_UPLOAD_BYTES must be positive")
    return value


def packaged_ui_directory() -> Path:
    """Return the install-owned production UI bundle location without creating it."""
    configured = os.getenv("ORION_UI_DIR")
    if configured:
        return Path(configured).expanduser()
    # The installer owns ``<prefix>/.orion-ui`` while the Python package lives in
    # ``<prefix>/.venv``. This also makes an editable repository installation use
    # its own packaged bundle rather than a development Vite server.
    return Path(sys.prefix).parent / ".orion-ui"
