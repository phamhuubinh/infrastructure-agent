"""Sanitized, append-only local application diagnostics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orion.security import redact_public


class ApplicationLog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write(self, event_type: str, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": redact_public(payload),
        }
        with self._path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(entry, sort_keys=True) + "\n")
