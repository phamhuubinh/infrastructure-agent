"""Opaque local blob storage for original uploaded bytes."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from orion.persistence.private_files import (
    checked_path,
    create_private_directory,
    open_checked_file,
    open_private_file,
    protect_private_path,
)


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self._root = root.absolute()
        self._root.parent.mkdir(parents=True, exist_ok=True)
        if self._root.exists() or self._root.is_symlink():
            protect_private_path(self._root, directory=True)
        else:
            checked_path(self._root.parent, directory=True)
            create_private_directory(self._root)
        info = checked_path(self._root, directory=True)
        self._identity = (info.st_dev, info.st_ino)
        # Protect legacy bytes as well as future uploads. A private directory alone
        # does not revoke explicit Windows grants on its existing child files.
        for path in self._root.iterdir():
            if re_full_uuid(path.name):
                protect_private_path(path)
        self._check_root()

    def _check_root(self) -> None:
        info = checked_path(self._root, directory=True)
        if (info.st_dev, info.st_ino) != self._identity:
            raise OSError("Blob directory changed")

    def put(self, content: bytes) -> str:
        blob_id = str(uuid.uuid4())
        path = self._path(blob_id)
        with os.fdopen(open_private_file(path), "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        return blob_id

    def get(self, blob_id: str) -> bytes:
        try:
            path = self._path(blob_id)
            protect_private_path(path)
            with os.fdopen(open_checked_file(path), "rb") as source:
                return source.read()
        except FileNotFoundError as error:
            raise ValueError("Document blob is unavailable") from error

    def delete(self, blob_id: str) -> None:
        """Remove an opaque blob if it still exists."""
        try:
            path = self._path(blob_id)
            checked_path(path)
            path.unlink()
        except FileNotFoundError:
            pass

    def _path(self, blob_id: str) -> Path:
        self._check_root()
        if not re_full_uuid(blob_id):
            raise ValueError("Invalid blob identity")
        return self._root / blob_id


def re_full_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False
