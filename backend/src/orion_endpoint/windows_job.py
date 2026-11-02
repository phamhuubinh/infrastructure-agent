"""Assign suspended command processes to a kill-on-close Windows Job Object."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

import psutil


class _Limits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _IO(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _Limits),
        ("io", _IO),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t),
        ("peak_job", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_longlong),
        ("kernel_time", ctypes.c_longlong),
        ("period_user", ctypes.c_longlong),
        ("period_kernel", ctypes.c_longlong),
        ("page_faults", wintypes.DWORD),
        ("total", wintypes.DWORD),
        ("active", wintypes.DWORD),
        ("terminated", wintypes.DWORD),
    ]


class WindowsJob:
    _kernel: Any  # Platform-loaded WinDLL; this class cannot be constructed on POSIX.
    _handle: Any

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows job objects are unavailable")
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel = self._kernel
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self._handle = kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise OSError("Cannot create command job")
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no breakaway.
        if not kernel.SetInformationJobObject(
            self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise OSError("Cannot establish command job limits")

    def attach_and_resume(self, pid: int) -> None:
        kernel = self._kernel
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        process = kernel.OpenProcess(0x0100 | 0x0001 | 0x0400, False, pid)
        if not process:
            raise OSError("Cannot own suspended command process")
        try:
            if not kernel.AssignProcessToJobObject(self._handle, process):
                raise OSError("Cannot assign suspended command to its job")
            threads = psutil.Process(pid).threads()
            if len(threads) != 1:
                raise OSError("Suspended command thread identity is invalid")
            kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenThread.restype = wintypes.HANDLE
            kernel.ResumeThread.argtypes = [wintypes.HANDLE]
            kernel.ResumeThread.restype = wintypes.DWORD
            thread = kernel.OpenThread(0x0002, False, threads[0].id)
            if not thread:
                raise OSError("Cannot resume owned command thread")
            try:
                if kernel.ResumeThread(thread) != 1:
                    raise OSError("Command thread has unexpected suspend state")
            finally:
                kernel.CloseHandle(thread)
        finally:
            kernel.CloseHandle(process)

    def terminate(self) -> None:
        self._kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._kernel.TerminateJobObject.restype = wintypes.BOOL
        if not self._kernel.TerminateJobObject(self._handle, 1):
            raise OSError("Cannot terminate command job")

    def empty(self) -> bool:
        self._kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self._kernel.QueryInformationJobObject.restype = wintypes.BOOL
        accounting = _Accounting()
        if not self._kernel.QueryInformationJobObject(
            self._handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
        ):
            raise OSError("Cannot observe command job termination")
        return bool(accounting.active == 0)

    def close(self) -> None:
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None
