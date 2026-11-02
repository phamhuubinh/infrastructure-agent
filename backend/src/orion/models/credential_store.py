"""Provider credentials outside model configuration and public serialization.

Windows uses current-user DPAPI with no UI/machine-wide fallback. Linux uses an
owned 0700 directory and 0600 files; it does not claim keyring encryption. Callers
rotate by creating a new reference, committing configuration, then retiring old
references. Reads never create directories or modify configuration.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import re
import stat
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

from pydantic import SecretStr

from orion.models.credentials import CredentialResolutionError, EnvironmentCredentialResolver

MAX_RECORD_BYTES = 131_072


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise CredentialResolutionError("Windows credential protection is unavailable.")
    load = ctypes.WinDLL
    crypt = load("crypt32", use_last_error=True)
    kernel = load("kernel32", use_last_error=True)
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    operation.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    incoming = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = _Blob()
    try:
        # CRYPTPROTECT_UI_FORBIDDEN; never CRYPTPROTECT_LOCAL_MACHINE.
        if not operation(ctypes.byref(incoming), None, None, None, None, 4, ctypes.byref(outgoing)):
            raise CredentialResolutionError("Protected credential operation failed.")
        if not 0 < outgoing.cbData <= MAX_RECORD_BYTES:
            raise CredentialResolutionError("Protected credential record is invalid.")
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.memset(buffer, 0, len(buffer))
        if outgoing.pbData:
            ctypes.memset(outgoing.pbData, 0, outgoing.cbData)
            kernel.LocalFree(ctypes.cast(outgoing.pbData, ctypes.c_void_p))


def _valid_key(value: str) -> None:
    if not value or len(value) > 16_384 or any(not 33 <= ord(char) <= 126 for char in value):
        raise CredentialResolutionError("Provider credential is invalid.")


def _linked(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _owned_private(info: os.stat_result) -> bool:
    if sys.platform == "win32":
        return True  # DPAPI protects contents under the current Windows account.
    return info.st_uid == os.geteuid() and not info.st_mode & 0o077


class ProtectedFileCredentialStore:
    def __init__(self, root: Path) -> None:
        self._root = root.absolute()

    def _directory(self, *, create: bool) -> None:
        if create:
            self._root.mkdir(mode=0o700, exist_ok=True)
        info = self._root.lstat()
        if _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise CredentialResolutionError("Credential directory is invalid.")
        if not _owned_private(info):
            raise CredentialResolutionError("Credential directory permissions are unsafe.")

    def _path(self, reference: str) -> Path:
        if not re.fullmatch(r"secret:[0-9a-f]{32}", reference):
            raise CredentialResolutionError("Credential reference is invalid.")
        return self._root / (reference[7:] + ".json")

    @staticmethod
    def _file(info: os.stat_result) -> None:
        if _linked(info) or not stat.S_ISREG(info.st_mode):
            raise CredentialResolutionError("Credential record is invalid.")
        if not _owned_private(info):
            raise CredentialResolutionError("Credential file permissions are unsafe.")

    def put(self, value: SecretStr) -> str:
        key = value.get_secret_value()
        _valid_key(key)
        inner = json.dumps(
            {"v": 1, "key": key, "sha256": hashlib.sha256(key.encode()).hexdigest()},
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            payload = _dpapi(inner, decrypt=False) if os.name == "nt" else inner
            kind = "windows-dpapi-v1" if os.name == "nt" else "posix-owned-file-v1"
            encoded = json.dumps(
                {"v": 1, "kind": kind, "payload": base64.b64encode(payload).decode("ascii")},
                separators=(",", ":"),
            ).encode("utf-8")
            self._directory(create=True)
            reference = "secret:" + uuid.uuid4().hex
            path = self._path(reference)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    self._file(os.fstat(output.fileno()))
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
            except BaseException:
                # Only this newly created opaque record; never a directory tree.
                path.unlink(missing_ok=True)
                raise
            return reference
        except (OSError, ValueError):
            raise CredentialResolutionError("Provider credential could not be stored.") from None

    def resolve(self, reference: str) -> SecretStr:
        path = self._path(reference)
        try:
            self._directory(create=False)
            self._file(path.lstat())
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as source:
                self._file(os.fstat(source.fileno()))
                encoded = source.read(MAX_RECORD_BYTES + 1)
            if len(encoded) > MAX_RECORD_BYTES:
                raise ValueError("record bound")
            record = json.loads(encoded)
            expected = "windows-dpapi-v1" if os.name == "nt" else "posix-owned-file-v1"
            if (
                not isinstance(record, dict)
                or set(record) != {"v", "kind", "payload"}
                or type(record["v"]) is not int
                or record["v"] != 1
                or record["kind"] != expected
                or not isinstance(record["payload"], str)
            ):
                raise ValueError("record format")
            payload = base64.b64decode(record["payload"], validate=True)
            inner = _dpapi(payload, decrypt=True) if os.name == "nt" else payload
            data = json.loads(inner)
            if (
                not isinstance(data, dict)
                or set(data) != {"v", "key", "sha256"}
                or type(data["v"]) is not int
                or data["v"] != 1
                or not isinstance(data["key"], str)
                or not isinstance(data["sha256"], str)
            ):
                raise ValueError("protected record format")
            key = data["key"]
            _valid_key(key)
            if not hmac.compare_digest(data["sha256"], hashlib.sha256(key.encode()).hexdigest()):
                raise ValueError("protected record integrity")
            return SecretStr(key)
        except (OSError, ValueError, TypeError, KeyError):
            raise CredentialResolutionError("Stored provider credential is unavailable.") from None

    def delete(self, reference: str) -> None:
        self.resolve(reference)
        try:
            self._path(reference).unlink()
        except OSError:
            raise CredentialResolutionError(
                "Stored provider credential could not be removed."
            ) from None

    def references(self) -> tuple[str, ...]:
        try:
            self._directory(create=False)
        except FileNotFoundError:
            return ()
        except (OSError, ValueError):
            raise CredentialResolutionError("Stored credential catalog is unavailable.") from None
        try:
            found = []
            for path in self._root.iterdir():
                if re.fullmatch(r"[0-9a-f]{32}\.json", path.name):
                    self._file(path.lstat())
                    found.append("secret:" + path.stem)
            return tuple(sorted(found))
        except (OSError, ValueError):
            raise CredentialResolutionError("Stored credential catalog is unavailable.") from None


class StoredCredentialResolver:
    def __init__(self, store: ProtectedFileCredentialStore) -> None:
        self.store = store
        self._environment = EnvironmentCredentialResolver()

    def resolve(self, reference: str) -> SecretStr:
        if reference.startswith("env:"):
            return self._environment.resolve(reference)
        return self.store.resolve(reference)


def credentials_for_database(path: Path) -> StoredCredentialResolver:
    return StoredCredentialResolver(
        ProtectedFileCredentialStore(path.parent / "provider-credentials")
    )
