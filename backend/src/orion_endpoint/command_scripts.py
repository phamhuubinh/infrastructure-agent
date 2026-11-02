"""Private, provenanced temporary scripts; prune only this worker's orphan artifacts."""

from __future__ import annotations

import ctypes
import getpass
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any

import psutil


def protect_script_path(path: Path, *, directory: bool = False) -> None:
    """Fresh owned paths only; establish privacy before writing script bytes."""
    if sys.platform != "win32":
        path.chmod(0o700 if directory else 0o600)
        return
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    descriptor = ctypes.c_void_p()
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    inherit = "OICI" if directory else ""
    sddl = f"D:P(A;{inherit};FA;;;OW)(A;{inherit};FA;;;SY)"
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        raise OSError("Cannot prepare private command artifact")
    try:
        advapi.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
        advapi.SetFileSecurityW.restype = wintypes.BOOL
        if not advapi.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise OSError("Cannot protect command artifact")
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(descriptor)
    _owner(path, private=True, directory=directory)


def _owner(path: Path, *, private: bool = False, directory: bool = False) -> str:
    if sys.platform != "win32":
        return f"uid:{path.lstat().st_uid}"
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    code = advapi.GetNamedSecurityInfoW(
        str(path),
        1,
        5 if private else 1,
        ctypes.byref(owner),
        None,
        None,
        None,
        ctypes.byref(descriptor),
    )
    if code:
        raise OSError("Cannot inspect command artifact owner")
    value = wintypes.LPWSTR()
    acl = wintypes.LPWSTR()
    try:
        if private:
            advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.LPWSTR),
                ctypes.c_void_p,
            ]
            advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
            if (
                not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    descriptor, 1, 4, ctypes.byref(acl), None
                )
                or acl.value is None
            ):
                raise OSError("Cannot inspect command artifact privacy")
            inherit = "OICI" if directory else ""
            expected = f"D:P(A;{inherit};FA;;;OW)(A;{inherit};FA;;;SY)"
            if acl.value.replace("D:PAI(", "D:P(", 1) != expected:
                raise OSError("Command artifact permissions are not private")
        advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
        if not advapi.ConvertSidToStringSidW(owner, ctypes.byref(value)) or value.value is None:
            raise OSError("Cannot identify command artifact owner")
        return value.value
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        if value.value:
            kernel.LocalFree(ctypes.cast(value, ctypes.c_void_p))
        if acl.value:
            kernel.LocalFree(ctypes.cast(acl, ctypes.c_void_p))
        kernel.LocalFree(descriptor)


def _ordinary(path: Path, owner: str, *, directory: bool = False) -> None:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
        or _owner(path, private=True, directory=directory) != owner
        or (sys.platform != "win32" and info.st_mode & 0o077)
    ):
        raise OSError("Command artifact ownership is invalid")


def _write_marker(path: Path, record: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        protect_script_path(path)
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(json.dumps(record, sort_keys=True).encode())
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)


def _read_marker(path: Path, owner: str) -> dict[str, Any]:
    _ordinary(path, owner)
    if path.stat().st_size > 4096:
        raise ValueError("Command artifact marker is invalid")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Command artifact marker is invalid")
    return value


class ScriptCache:
    def __init__(self, temporary_root: Path | None = None) -> None:
        temporary_root = (temporary_root or Path(tempfile.gettempdir())).resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix=".orion-owner-", dir=temporary_root) as probe:
            self.owner = _owner(Path(probe))
        identity = hashlib.sha256((self.owner + ":" + getpass.getuser()).encode()).hexdigest()[:20]
        self.root = temporary_root / ("orion-worker-commands-" + identity)
        marker = {"format": "orion-command-cache", "version": 1, "owner": self.owner}
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            _ordinary(self.root, self.owner, directory=True)
            existing = _read_marker(self.root / "owner.json", self.owner)
            if type(existing.get("version")) is not int or existing != marker:
                raise OSError("Command cache is not owned by this worker account") from None
        else:
            protect_script_path(self.root, directory=True)
            _write_marker(self.root / "owner.json", marker)
        self.cleanup_orphans()

    def _record(self, path: Path) -> dict[str, Any]:
        if path.parent != self.root or not re.fullmatch(r"[0-9a-f]{32}", path.name):
            raise ValueError("Command artifact directory is invalid")
        _ordinary(path, self.owner, directory=True)
        record = _read_marker(path / "owner.json", self.owner)
        if (
            set(record) != {"format", "version", "owner", "id", "pid", "started", "script"}
            or record["format"] != "orion-command-script"
            or type(record["version"]) is not int
            or record["version"] != 1
            or record["owner"] != self.owner
            or record["id"] != path.name
            or type(record["pid"]) is not int
            or record["pid"] < 1
            or type(record["started"]) not in (float, int)
            or record["started"] <= 0
            or not math.isfinite(record["started"])
            or not isinstance(record["script"], str)
            or record["script"] not in {"command.ps1", "command.cmd", "command.sh"}
        ):
            raise ValueError("Command artifact provenance is invalid")
        return record

    def _remove(self, path: Path, record: dict[str, Any]) -> None:
        # Never recurse or delete data a shell script created beside its own source.
        script = path / record["script"]
        if script.exists() or script.is_symlink():
            _ordinary(script, self.owner)
            script.unlink()
        marker = path / "owner.json"
        _ordinary(marker, self.owner)
        marker.unlink()
        try:
            path.rmdir()
        except OSError:
            pass  # Unknown command-created files are preserved, never pruned as artifacts.

    def cleanup_orphans(self) -> None:
        _ordinary(self.root, self.owner, directory=True)
        with os.scandir(self.root) as entries:
            for index, entry in enumerate(entries):
                if index >= 512:
                    break
                try:
                    path = Path(entry.path)
                    record = self._record(path)
                    try:
                        live = psutil.Process(record["pid"]).create_time() == record["started"]
                    except psutil.NoSuchProcess:
                        live = False
                    if not live:
                        self._remove(path, record)
                except (OSError, ValueError, psutil.AccessDenied):
                    continue  # Unknown/linked/live/unreadable paths grant no cleanup authority.

    @contextmanager
    def directory(self, shell: str) -> Iterator[Path]:
        _ordinary(self.root, self.owner, directory=True)
        if _read_marker(self.root / "owner.json", self.owner) != {
            "format": "orion-command-cache",
            "version": 1,
            "owner": self.owner,
        }:
            raise OSError("Command cache provenance changed")
        path = self.root / uuid.uuid4().hex
        path.mkdir(mode=0o700)
        protect_script_path(path, directory=True)
        suffix = "ps1" if shell == "powershell" else "cmd" if shell == "cmd" else "sh"
        record = {
            "format": "orion-command-script",
            "version": 1,
            "owner": self.owner,
            "id": path.name,
            "pid": os.getpid(),
            "started": psutil.Process().create_time(),
            "script": "command." + suffix,
        }
        _write_marker(path / "owner.json", record)
        try:
            yield path
        finally:
            try:
                if self._record(path) == record:
                    self._remove(path, record)
            except (OSError, ValueError):
                pass  # Fail closed; only proven orphan artifacts may be retried on next startup.
