"""Connection-owned shell processes with bounded transient output and no replay."""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import psutil

from orion_endpoint.command_scripts import ScriptCache, protect_script_path
from orion_endpoint.protocol import CommandRun, CommandStatus
from orion_endpoint.windows_job import WindowsJob

_ACTIVE = {"created", "running"}


def available_shells() -> dict[str, str]:
    names = (
        {"cmd": ("cmd.exe",), "powershell": ("pwsh.exe", "powershell.exe")}
        if (sys.platform == "win32")
        else {"sh": ("sh",), "bash": ("bash",)}
    )
    found_shells = {
        shell: found
        for shell, candidates in names.items()
        if (found := next((path for name in candidates if (path := shutil.which(name))), None))
    }
    # Frozen workers deliberately run without a host PATH. OS-provided shells
    # remain available without requiring Python/Node or altering that PATH.
    if sys.platform == "win32":
        system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        fallback = {
            "cmd": system / "cmd.exe",
            "powershell": system / "WindowsPowerShell/v1.0/powershell.exe",
        }
    else:
        fallback = {"sh": Path("/bin/sh"), "bash": Path("/bin/bash")}
    for name, candidate in fallback.items():
        if name not in found_shells and candidate.is_file() and os.access(candidate, os.X_OK):
            found_shells[name] = str(candidate)
    return found_shells


@dataclass(repr=False)
class _Command:
    input: CommandRun
    state: str = "created"
    process: subprocess.Popen[bytes] | None = None
    job: WindowsJob | None = None
    task: asyncio.Task[None] | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    omitted: int = 0
    exit_code: int | None = None
    terminated: bool = False
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    cancel_requested: bool = False
    descendants: dict[int, float] = field(default_factory=dict)


class CommandProcesses:
    def __init__(self) -> None:
        self.handles: dict[str, _Command] = {}
        self.shells = available_shells()
        self.closed = False
        self._script_cache: ScriptCache | None = None

    async def start(self, arguments: dict[str, Any]) -> dict[str, Any]:
        values = CommandRun.model_validate(arguments)
        if self.closed or values.shell not in self.shells:
            raise ValueError("unavailable")
        if values.command_id in self.handles:
            raise FileExistsError("conflict")
        if (
            sum(
                value.state in _ACTIVE
                or (value.process is not None and value.process.poll() is None)
                for value in self.handles.values()
            )
            >= 4
        ):
            raise RuntimeError("busy")
        for identity, old in list(self.handles.items()):
            if (
                old.finished
                and (old.process is None or old.process.poll() is not None)
                and (time.monotonic() - old.finished > 300 or len(self.handles) >= 16)
            ):
                del self.handles[identity]
        if len(self.handles) >= 16:
            raise RuntimeError("busy")
        record = _Command(values)
        self.handles[values.command_id] = record
        record.task = asyncio.create_task(self._run(record))
        try:
            await record.ready.wait()
            return self.status({"command_id": values.command_id})
        except BaseException:
            await self.cancel(values.command_id)
            raise

    def status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        values = CommandStatus.model_validate(arguments)
        record = self.handles.get(values.command_id)
        if record is None:
            raise ValueError("unavailable")
        terminal = record.state not in _ACTIVE
        stdout, stdout_next = self._page(record.stdout, values.stdout_offset, terminal)
        stderr, stderr_next = self._page(record.stderr, values.stderr_offset, terminal)
        return {
            "command_id": values.command_id,
            "shell": record.input.shell,
            "state": record.state,
            "exit_code": record.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": max(0, (record.finished or time.monotonic()) - record.started),
            "omitted_output_bytes": record.omitted,
            "process_tree_terminated": record.terminated,
            "stdout_offset": values.stdout_offset,
            "stderr_offset": values.stderr_offset,
            "next_stdout_offset": stdout_next,
            "next_stderr_offset": stderr_next,
            "captured_output_bytes": len(record.stdout) + len(record.stderr),
        }

    @staticmethod
    def _page(raw: bytearray, offset: int, terminal: bool) -> tuple[str, int]:
        if offset > len(raw):
            raise ValueError("invalid_input")
        end = min(len(raw), offset + 32_768)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        output = decoder.decode(bytes(raw[offset:end]), final=terminal and end == len(raw))
        pending, _ = decoder.getstate()
        return output, end - len(pending)

    async def cancel(self, identity: str) -> dict[str, Any]:
        record = self.handles.get(identity)
        if record is None:
            raise ValueError("unavailable")
        if record.task and not record.task.done():
            if not record.cancel_requested:
                record.cancel_requested = True
                record.task.cancel()
            await asyncio.shield(asyncio.gather(record.task, return_exceptions=True))
            if record.state == "created":
                record.state, record.terminated, record.finished = (
                    "cancelled",
                    True,
                    time.monotonic(),
                )
                record.ready.set()
        return self.status({"command_id": identity})

    async def _read(self, record: _Command, pipe: IO[bytes], output: bytearray) -> None:
        while block := await asyncio.to_thread(pipe.read, 8192):
            remaining = record.input.max_output_bytes - len(record.stdout) - len(record.stderr)
            kept = max(0, min(remaining, len(block)))
            output.extend(block[:kept])
            record.omitted += len(block) - kept

    async def _track(self, record: _Command) -> None:
        if record.process is None:
            return
        while True:
            try:
                children = psutil.Process(record.process.pid).children(recursive=True)
                for child in children:
                    record.descendants[child.pid] = child.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            await asyncio.sleep(0.05)

    def _spawn(self, record: _Command, directory: Path) -> None:
        shell = record.input.shell
        suffix = ".ps1" if shell == "powershell" else ".cmd" if shell == "cmd" else ".sh"
        script = directory / ("command" + suffix)
        descriptor = os.open(script, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            protect_script_path(script)
            prefix = (
                "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
                if shell == "powershell"
                else "@echo off\r\n@chcp 65001 >nul\r\n"
                if shell == "cmd"
                else ""
            )
            with os.fdopen(descriptor, "wb", closefd=False) as output:
                output.write(
                    (prefix + record.input.command).encode(
                        "utf-8-sig" if shell == "powershell" else "utf-8"
                    )
                )
        finally:
            os.close(descriptor)
        executable = self.shells[shell]
        environment = os.environ.copy()
        if shell == "cmd":
            environment["ORION_COMMAND_SCRIPT"] = str(script)
            args: str | list[str] = f'"{executable}" /d /s /c ""%ORION_COMMAND_SCRIPT%""'
        elif shell == "powershell":
            args = [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)]
        else:
            args = [
                executable,
                *(["--noprofile", "--norc"] if shell == "bash" else []),
                str(script),
            ]
        if sys.platform == "win32":
            record.job = WindowsJob()
        record.process = subprocess.Popen(
            args,
            executable=executable,
            cwd=record.input.cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            shell=False,
            start_new_session=sys.platform != "win32",
            creationflags=0x00000004 | 0x08000000 if sys.platform == "win32" else 0,
        )
        if record.job:
            try:
                record.job.attach_and_resume(record.process.pid)
            except BaseException:
                # Assignment failure must not strand an unowned suspended process.
                record.process.kill()
                record.process.wait(timeout=3)
                raise

    async def _terminate(self, record: _Command) -> bool:
        process = record.process
        if process is None:
            return True
        try:
            if record.job:
                record.job.terminate()
            elif sys.platform != "win32":
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                for pid, created in record.descendants.items():
                    try:
                        child = psutil.Process(pid)
                        if child.create_time() == created:
                            child.kill()
                    except psutil.NoSuchProcess:
                        pass
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if record.job:
                    if record.job.empty():
                        return True
                elif sys.platform != "win32":
                    remaining = []
                    for item in psutil.process_iter(["pid", "status", "create_time"]):
                        if item.info["status"] == psutil.STATUS_ZOMBIE:
                            continue
                        try:
                            if os.getpgid(item.pid) == process.pid or (
                                record.descendants.get(item.pid) == item.info["create_time"]
                            ):
                                remaining.append(item.pid)
                        except ProcessLookupError:
                            pass
                    if not remaining:
                        return True
                await asyncio.sleep(0.05)
        except (OSError, psutil.Error):
            return False
        return False

    async def _run(self, record: _Command) -> None:
        readers: list[asyncio.Task[None]] = []
        tracker: asyncio.Task[None] | None = None
        waiter: asyncio.Task[int] | None = None
        state = "outcome_unknown"
        try:
            if self._script_cache is None:
                self._script_cache = ScriptCache()
            with self._script_cache.directory(record.input.shell) as directory:
                try:
                    self._spawn(record, directory)
                    process = record.process
                    assert process is not None and process.stdout and process.stderr
                    readers = [
                        asyncio.create_task(self._read(record, process.stdout, record.stdout)),
                        asyncio.create_task(self._read(record, process.stderr, record.stderr)),
                    ]
                    if sys.platform != "win32":
                        tracker = asyncio.create_task(self._track(record))
                    record.state = "running"
                    record.ready.set()
                    waiter = asyncio.create_task(asyncio.to_thread(process.wait))
                    code = await asyncio.wait_for(
                        asyncio.shield(waiter), record.input.timeout_seconds
                    )
                    state = "succeeded" if code == 0 else "failed"
                    record.exit_code = code
                except TimeoutError:
                    state = "timed_out"
                except asyncio.CancelledError:
                    state = "cancelled"
                except Exception:
                    state = "outcome_unknown"
                finally:
                    cleanup = asyncio.create_task(self._cleanup(record, readers, tracker, waiter))
                    # Stop/disconnect may arrive during normal-exit cleanup. Keep
                    # cleanup bounded but do not abandon it on a second cancellation.
                    while True:
                        try:
                            if not await asyncio.shield(cleanup):
                                state, record.exit_code = "outcome_unknown", None
                            break
                        except asyncio.CancelledError:
                            record.cancel_requested = True
        except Exception:
            state = "outcome_unknown"
        finally:
            record.state, record.finished = state, time.monotonic()
            record.ready.set()

    async def _cleanup(
        self,
        record: _Command,
        readers: list[asyncio.Task[None]],
        tracker: asyncio.Task[None] | None,
        waiter: asyncio.Task[int] | None,
    ) -> bool:
        try:
            record.terminated = await self._terminate(record)
            if tracker:
                tracker.cancel()
                await asyncio.gather(tracker, return_exceptions=True)
            if waiter:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(waiter), 3)
            try:
                await asyncio.wait_for(asyncio.gather(*readers), 3)
            except (TimeoutError, OSError):
                return False
            return record.terminated
        except Exception:
            return False
        finally:
            if record.process:
                for pipe in (record.process.stdout, record.process.stderr):
                    if pipe:
                        pipe.close()
            if record.job:
                record.job.close()

    async def close(self) -> None:
        self.closed = True
        await asyncio.gather(
            *(self.cancel(identity) for identity in tuple(self.handles)), return_exceptions=True
        )
