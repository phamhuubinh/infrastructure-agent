"""Opaque local blob storage for original uploaded bytes."""

from __future__ import annotations

import uuid
from pathlib import Path


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes) -> str:
        blob_id = str(uuid.uuid4())
        path = self._path(blob_id)
        path.write_bytes(content)
        return blob_id

    def get(self, blob_id: str) -> bytes:
        try:
            return self._path(blob_id).read_bytes()
        except FileNotFoundError as error:
            raise ValueError("Document blob is unavailable") from error

    def _path(self, blob_id: str) -> Path:
        if not re_full_uuid(blob_id):
            raise ValueError("Invalid blob identity")
        return self._root / blob_id


def re_full_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False
