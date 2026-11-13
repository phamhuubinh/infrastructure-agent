"""Create private data artifacts before any secret-bearing bytes are written."""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from ctypes import wintypes
from pathlib import Path


def checked_path(path: Path, *, directory: bool = False) -> os.stat_result:
    """Reject redirected ancestors, reparse points, special files and hard links."""
    if path.absolute() != path.resolve(strict=True):
        raise OSError("Linked data paths are not supported")
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise OSError("Data path is not an ordinary owned path")
    if sys.platform != "win32" and info.st_uid != os.geteuid():
        raise OSError("Data path belongs to another account")
    return info


def protect_private_path(path: Path, *, directory: bool = False) -> None:
    """Upgrade an existing owned artifact without following links or changing bytes."""
    before = checked_path(path, directory=directory)
    if sys.platform == "win32":
        _windows_private_acl(path, directory=directory)
    else:
        path.chmod(0o700 if directory else 0o600)
    after = checked_path(path, directory=directory)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise OSError("Data path changed during protection")


def open_checked_file(path: Path) -> int:
    """Read through a validated descriptor, with identity checked after open."""
    before = checked_path(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        after = checked_path(path)
        if (
            (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_nlink != 1
        ):
            raise OSError("Data file changed during open")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def require_private_path(path: Path, *, directory: bool = False) -> None:
    info = checked_path(path, directory=directory)
    if sys.platform == "win32":
        _windows_private_acl(path, directory=directory, validate_only=True)
    elif info.st_mode & 0o077:
        raise OSError("Data artifact permissions are not private")


def _windows_acl_text(path: Path) -> str:
    if sys.platform != "win32":
        raise OSError("Windows ACLs are unavailable")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    code = advapi.GetNamedSecurityInfoW(
        str(path), 1, 4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
    )
    if code:
        raise OSError(code, "Cannot inspect private Windows ACL")
    try:
        return _windows_dacl_sddl(descriptor)
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(descriptor)


def _windows_dacl_sddl(descriptor: ctypes.c_void_p) -> str:
    if sys.platform != "win32":
        raise OSError("Windows ACLs are unavailable")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    string = wintypes.LPWSTR()
    try:
        advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
        if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, 4, ctypes.byref(string), None
        ):
            raise OSError("Cannot inspect private Windows ACL")
        # Windows may retain SE_DACL_AUTO_INHERITED on a protected DACL. ACEs
        # must still exactly match our explicit grants; inherited ACEs fail.
        if string.value is None:
            raise OSError("Windows ACL text is unavailable")
        return string.value.replace("D:PAI(", "D:P(", 1)
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        if string.value:
            kernel.LocalFree(ctypes.cast(string, ctypes.c_void_p))


def _windows_private_acl(path: Path, *, directory: bool, validate_only: bool = False) -> None:
    """Protect a newly created path for the current user and LocalSystem."""
    if sys.platform != "win32":
        return
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    token = wintypes.HANDLE()
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise OSError("Cannot read current Windows identity")
    sid_string = wintypes.LPWSTR()
    descriptor = ctypes.c_void_p()
    try:
        advapi.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.GetTokenInformation.restype = wintypes.BOOL
        length = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(length))
        if not 0 < length.value <= 65536:
            raise OSError("Invalid Windows identity record")
        buffer = ctypes.create_string_buffer(length.value)
        if not advapi.GetTokenInformation(token, 1, buffer, length, ctypes.byref(length)):
            raise OSError("Cannot read Windows identity")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
        advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_string)):
            raise OSError("Cannot identify Windows account")
        inherit = "OICI" if directory else ""
        sddl = f"D:P(A;{inherit};FA;;;{sid_string.value})(A;{inherit};FA;;;SY)"
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None
        ):
            raise OSError("Cannot build private Windows ACL")
        # Windows may render a well-known trustee as an SDDL alias. Format
        # both descriptors with the same API before comparing their DACLs.
        expected_dacl = _windows_dacl_sddl(descriptor)
        if validate_only:
            if _windows_acl_text(path) != expected_dacl:
                raise OSError("Data artifact Windows ACL is not private")
            return
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        advapi.GetSecurityDescriptorDacl.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
        if (
            not advapi.GetSecurityDescriptorDacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
            )
            or not present.value
            or not dacl.value
        ):
            raise OSError("Private Windows ACL is unavailable")
        advapi.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
        result = advapi.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None)
        if result:
            raise OSError(result, "Cannot protect private Windows path")
        if _windows_acl_text(path) != expected_dacl:
            raise OSError("Private Windows ACL verification failed")
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        if descriptor.value:
            kernel.LocalFree(descriptor)
        if sid_string.value:
            kernel.LocalFree(ctypes.cast(sid_string, ctypes.c_void_p))
        kernel.CloseHandle(token)


def create_private_directory(path: Path) -> None:
    """Create one new directory; never change permissions of an existing path."""
    checked_path(path.parent, directory=True)
    path.mkdir(mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink() or path.is_junction():
        raise OSError("Private directory is invalid")
    if sys.platform == "win32":
        _windows_private_acl(path, directory=True)
    elif info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise OSError("Private directory permissions are unsafe")


def open_private_file(path: Path) -> int:
    """Open a new private file for writing; the caller owns its descriptor."""
    checked_path(path.parent, directory=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        named = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino)
            or path.is_symlink()
            or path.is_junction()
        ):
            raise OSError("Private file is invalid")
        if sys.platform == "win32":
            _windows_private_acl(path, directory=False)
        elif info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise OSError("Private file permissions are unsafe")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def create_private_file(path: Path) -> None:
    """Reserve a new 0600 file and protect its DACL before data is written."""
    os.close(open_private_file(path))
