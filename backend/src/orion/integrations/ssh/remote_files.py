"""Standalone Linux stdlib script artifacts for the ephemeral SSH helper.

Never kill a PID or recursively delete a directory while pruning artifacts.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def _linux() -> None:
    if sys.platform != "linux":
        raise OSError("Linux script cache is unavailable")


def _uid() -> int:
    if sys.platform != "linux":
        raise OSError("Linux ownership is unavailable")
    return os.geteuid()


def _nofollow() -> int:
    if sys.platform != "linux":
        raise OSError("Linux no-follow flag is unavailable")
    return os.O_NOFOLLOW


def process_fields(text: str) -> tuple[int, int, int, int, str]:
    """Parse numeric stat fields after comm, which may contain Unicode or ')'."""
    try:
        fields = text.rsplit(")", 1)[1].split()
        return int(fields[1]), int(fields[2]), int(fields[3]), int(fields[19]), fields[0]
    except (ValueError, IndexError):
        raise ValueError("Linux process identity is unavailable") from None


def process_identity(pid: int) -> tuple[str, int] | None:
    """Boot identity and proc start ticks; unreadable is not proof of death."""
    _linux()
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    # comm may contain spaces and ')'; numeric fields follow its final ')'.
    return boot, process_fields(text)[3]


def _ordinary(path: Path, *, directory: bool = False) -> None:
    _linux()
    if path != path.resolve(strict=True):
        raise OSError("Linked command artifact")
    info = path.lstat()
    if (
        not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or info.st_uid != _uid()
        or info.st_mode & 0o077
        or (not directory and info.st_nlink != 1)
    ):
        raise OSError("Command artifact is not private and owned")


def _write_marker(path: Path, record: dict[str, Any]) -> None:
    _linux()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _nofollow(), 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(json.dumps(record, sort_keys=True).encode("ascii"))
            output.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_marker(path: Path) -> dict[str, Any]:
    _ordinary(path)
    _linux()
    descriptor = os.open(path, os.O_RDONLY | _nofollow())
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != _uid()
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_size > 4096
        ):
            raise OSError("Command provenance is not private")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            data = source.read(4097)
        if len(data) > 4096:
            raise ValueError("Command provenance size")
        record = json.loads(data)
        if not isinstance(record, dict):
            raise ValueError("Command provenance schema")
        return record
    finally:
        os.close(descriptor)


def validate_record(record: object, identity: str, uid: int) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", identity) or not isinstance(record, dict):
        raise ValueError("Command provenance identity")
    if (
        set(record)
        != {
            "format",
            "version",
            "uid",
            "command_id",
            "helper_pid",
            "boot_id",
            "start_ticks",
            "script",
        }
        or record["format"] != "orion-ssh-script"
        or type(record["version"]) is not int
        or record["version"] != 1
        or type(record["uid"]) is not int
        or record["uid"] != uid
        or record["command_id"] != identity
        or type(record["helper_pid"]) is not int
        or not 1 <= record["helper_pid"] <= 2_147_483_647
        or type(record["start_ticks"]) is not int
        or record["start_ticks"] < 1
        or not isinstance(record["boot_id"], str)
        or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", record["boot_id"])
        or not isinstance(record["script"], str)
        or record["script"] != "command.sh"
    ):
        raise ValueError("Command provenance schema")
    return record


class PrivateScripts:
    def __init__(self, temporary_root: Path | None = None) -> None:
        _linux()
        self.uid = _uid()
        identity = process_identity(os.getpid())
        if identity is None:
            raise OSError("Helper process identity is unavailable")
        self.identity: tuple[str, int] = identity
        parent = (temporary_root or Path(tempfile.gettempdir())).resolve(strict=True)
        self.root = parent / f"orion-ssh-command-cache-{self.uid}"
        marker = {"format": "orion-ssh-command-cache", "version": 1, "uid": self.uid}
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            _ordinary(self.root, directory=True)
            existing = _read_marker(self.root / "owner.json")
            if (
                type(existing.get("version")) is not int
                or type(existing.get("uid")) is not int
                or existing != marker
            ):
                raise OSError("Unknown SSH command cache") from None
        else:
            _write_marker(self.root / "owner.json", marker)
        self.prune()

    def _record(self, path: Path) -> dict[str, Any]:
        if path.parent != self.root:
            raise ValueError("Command artifact parent")
        _ordinary(path, directory=True)
        return validate_record(_read_marker(path / "owner.json"), path.name, self.uid)

    @staticmethod
    def _remove(path: Path, record: dict[str, Any]) -> None:
        script = path / record["script"]
        if script.exists() or script.is_symlink():
            _ordinary(script)
            script.unlink()
        marker = path / "owner.json"
        _ordinary(marker)
        marker.unlink()
        try:
            path.rmdir()
        except OSError:
            pass  # Preserve every unknown command-created neighboring file.

    def prune(self) -> None:
        _ordinary(self.root, directory=True)
        with os.scandir(self.root) as entries:
            for index, entry in enumerate(entries):
                if index >= 512:
                    break
                try:
                    path = Path(entry.path)
                    record = self._record(path)
                    expected = record["boot_id"], record["start_ticks"]
                    if process_identity(record["helper_pid"]) != expected:
                        self._remove(path, record)
                except (OSError, ValueError, IndexError):
                    continue  # Unknown/linked/unreadable is not cleanup authority.

    @contextmanager
    def directory(self, command_id: str) -> Iterator[Path]:
        if not re.fullmatch(r"[0-9a-f]{32}", command_id):
            raise ValueError("Command identity")
        _ordinary(self.root, directory=True)
        if _read_marker(self.root / "owner.json") != {
            "format": "orion-ssh-command-cache",
            "version": 1,
            "uid": self.uid,
        }:
            raise OSError("SSH cache provenance changed")
        path = self.root / command_id
        path.mkdir(mode=0o700)
        record = {
            "format": "orion-ssh-script",
            "version": 1,
            "uid": self.uid,
            "command_id": command_id,
            "helper_pid": os.getpid(),
            "boot_id": self.identity[0],
            "start_ticks": self.identity[1],
            "script": "command.sh",
        }
        _write_marker(path / "owner.json", record)
        try:
            yield path
        finally:
            try:
                if self._record(path) == record:
                    self._remove(path, record)
            except (OSError, ValueError):
                pass

    @staticmethod
    def write_script(directory: Path, script: str) -> Path:
        _ordinary(directory, directory=True)
        content = script.encode("utf-8")
        if not 0 < len(content) <= 65_536 or "\0" in script:
            raise ValueError("Command script bound")
        _linux()
        path = directory / "command.sh"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _nofollow(), 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as output:
                output.write(content)
                output.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path
