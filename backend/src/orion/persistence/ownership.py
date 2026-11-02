"""OS-backed exclusive runtime ownership; metadata readers do not take this lease."""

from __future__ import annotations

import os
import stat
import sys
import weakref
from pathlib import Path


class RuntimeLease:
    def __init__(self, database_path: Path) -> None:
        database = database_path.resolve()
        self._database = database
        path = database.with_name(database.name + ".runtime.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._descriptor: int | None = None
        self._finalizer: weakref.finalize[[int], RuntimeLease] | None = None
        descriptor: int | None = None
        try:
            if path.is_symlink():
                raise OSError("linked ownership file")
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            information, opened = path.lstat(), os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or stat.S_ISLNK(information.st_mode)
                or getattr(information, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                or (information.st_dev, information.st_ino) != (opened.st_dev, opened.st_ino)
                or opened.st_size > 16
            ):
                raise OSError("invalid ownership file")
        except OSError:
            if descriptor is not None:
                os.close(descriptor)
            raise RuntimeError("Orion runtime ownership file is unavailable.") from None
        try:
            self._lock(descriptor)
        except OSError:
            os.close(descriptor)
            raise RuntimeError("Application data is owned by another Orion runtime.") from None
        try:
            if opened.st_size == 0:
                os.write(descriptor, b"\0")
            self._descriptor = descriptor
            self._finalizer = weakref.finalize(self, os.close, descriptor)
        except BaseException:
            try:
                self._unlock(descriptor)
            finally:
                os.close(descriptor)
            raise

    @staticmethod
    def _lock(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            if self._finalizer is not None:
                self._finalizer.detach()
                self._finalizer = None
            try:
                self._unlock(descriptor)
            finally:
                os.close(descriptor)
        # Never unlink the inode while another process may be opening it.

    def owns(self, database_path: Path) -> bool:
        return self._descriptor is not None and database_path.resolve() == self._database
