"""Standalone stdlib Linux command handles for the ephemeral SSH helper."""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from .remote_files import PrivateScripts, process_fields
from .remote_protocol import parse_supervisor_observation, safe_duration


@dataclass(repr=False)
class _Command:
    arguments: dict[str, Any]
    started: float = field(default_factory=time.monotonic)
    state: str = "created"
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    process: subprocess.Popen[bytes] | None = None
    task: asyncio.Task[None] | None = None
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    omitted: int = 0
    exit_code: int | None = None
    finished: float | None = None
    terminated: bool = False
    containment_complete: bool = False
    cancelled: bool = False
    descendants: dict[int, int] = field(default_factory=dict)


def process_snapshot() -> tuple[dict[int, tuple[int, int, int, int, str]], bool]:
    if sys.platform != "linux":
        raise OSError("Linux process observation is unavailable")
    result: dict[int, tuple[int, int, int, int, str]] = {}
    complete = True
    with os.scandir("/proc") as entries:
        for index, entry in enumerate(entries):
            if index > 16_384:
                complete = False
                break
            if not entry.name.isdecimal():
                continue
            try:
                text = (Path(entry.path) / "stat").read_text(encoding="utf-8", errors="replace")
                result[int(entry.name)] = process_fields(text)
            except FileNotFoundError:
                continue
            except (OSError, ValueError, IndexError):
                complete = False
    return result, complete


class RemoteCommands:
    closed: bool
    shells: dict[str, str]
    files: PrivateScripts
    supervisor_source: str
    handles: dict[str, _Command]
    used: set[str]

    def __init__(self, supervisor_source: str) -> None:
        if sys.platform != "linux" or sys.version_info < (3, 10):
            raise OSError("Linux Python3.10 commands are unavailable")
        if not supervisor_source or len(supervisor_source.encode()) > 65_536:
            raise ValueError("Supervisor source bound")
        self.supervisor_source = supervisor_source
        self.files = PrivateScripts()
        self.shells = {}
        for name in ("sh", "bash"):
            for parent in ("/bin", "/usr/bin"):
                candidate = Path(parent) / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    self.shells[name] = str(candidate)
                    break
        self.handles: dict[str, _Command] = {}
        self.used: set[str] = set()
        self.closed = False

    async def start(self, arguments: dict[str, Any]) -> dict[str, Any]:
        identity = arguments["command_id"]
        if self.closed or arguments["shell"] not in self.shells:
            raise ValueError("unavailable")
        if identity in self.used:
            raise FileExistsError("conflict")
        if (
            len(self.used) >= 4096
            or sum(
                r.state in {"created", "running"}
                or (r.process is not None and r.process.poll() is None)
                for r in self.handles.values()
            )
            >= 4
        ):
            raise RuntimeError("busy")
        for key, record in list(self.handles.items()):
            if (
                record.state != "outcome_unknown"
                and record.finished
                and (len(self.handles) >= 16 or time.monotonic() - record.finished > 300)
            ):
                del self.handles[key]
        if len(self.handles) >= 16:
            raise RuntimeError("busy")
        record = _Command(dict(arguments))
        self.used.add(identity)
        self.handles[identity] = record
        record.task = asyncio.create_task(self._run(record))
        try:
            await record.ready.wait()
            return self.status({"command_id": identity})
        except BaseException:
            await self.cancel(identity)
            raise

    @staticmethod
    def _page(raw: bytearray, offset: int, terminal: bool) -> tuple[str, int]:
        if not 0 <= offset <= len(raw):
            raise ValueError("invalid_input")
        end = min(len(raw), offset + 32_768)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        text = decoder.decode(bytes(raw[offset:end]), final=terminal and end == len(raw))
        return text, end - len(decoder.getstate()[0])

    def status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        record = self.handles.get(arguments["command_id"])
        if record is None:
            raise ValueError("unavailable")
        out_offset, err_offset = (
            arguments.get("stdout_offset", 0),
            arguments.get("stderr_offset", 0),
        )
        terminal = record.state not in {"created", "running"}
        stdout, out_next = self._page(record.stdout, out_offset, terminal)
        stderr, err_next = self._page(record.stderr, err_offset, terminal)
        return {
            "command_id": arguments["command_id"],
            "shell": record.arguments["shell"],
            "state": record.state,
            "exit_code": record.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": safe_duration(record.started, record.finished or time.monotonic()),
            "omitted_output_bytes": record.omitted,
            "process_tree_terminated": record.terminated,
            "stdout_offset": out_offset,
            "stderr_offset": err_offset,
            "next_stdout_offset": out_next,
            "next_stderr_offset": err_next,
            "captured_output_bytes": len(record.stdout) + len(record.stderr),
        }

    async def cancel(self, identity: str) -> dict[str, Any]:
        record = self.handles.get(identity)
        if record is None:
            raise ValueError("unavailable")
        if record.task and not record.task.done():
            if not record.cancelled:
                record.cancelled = True
                record.task.cancel()
            await asyncio.shield(asyncio.gather(record.task, return_exceptions=True))
            if record.state == "created":
                record.state, record.terminated, record.finished = (
                    "cancelled",
                    True,
                    time.monotonic(),
                )
                record.ready.set()
        if (
            record.state == "outcome_unknown"
            and not record.terminated
            and record.process is not None
        ):
            # Shutdown/explicit cancel gets another bounded cleanup attempt for
            # an uncertain retained handle. Never convert it to a known exit.
            observed = await self._terminate(record)
            record.terminated = observed and record.containment_complete
        return self.status({"command_id": identity})

    async def _capture(self, record: _Command, pipe: IO[bytes], output: bytearray) -> None:
        reader = asyncio.StreamReader(limit=8192)
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), pipe
        )
        try:
            while chunk := await reader.read(8192):
                remaining = (
                    record.arguments["max_output_bytes"] - len(record.stdout) - len(record.stderr)
                )
                kept = max(0, min(remaining, len(chunk)))
                output.extend(chunk[:kept])
                record.omitted += len(chunk) - kept
        finally:
            transport.close()

    async def _metadata(self, pipe: IO[bytes]) -> bytes:
        reader = asyncio.StreamReader(limit=4097)
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), pipe
        )
        try:
            data = bytearray()
            while chunk := await reader.read(4097):
                data.extend(chunk)
                if len(data) > 4096:
                    raise ValueError("Supervisor metadata bound")
            return bytes(data)
        finally:
            transport.close()

    async def _wait(self, record: _Command) -> None:
        assert record.process
        while record.process.poll() is None:
            self._observe(record)
            await asyncio.sleep(0.05)

    @staticmethod
    def _observe(record: _Command) -> None:
        assert record.process
        rows, _ = process_snapshot()
        leader = rows.get(record.process.pid)
        if leader and record.process.poll() is None:
            record.descendants.setdefault(record.process.pid, leader[3])
        changed = True
        while changed:
            changed = False
            for pid, row in rows.items():
                parent = rows.get(row[0])
                if (
                    pid not in record.descendants
                    and parent is not None
                    and record.descendants.get(row[0]) == parent[3]
                ):
                    record.descendants[pid] = row[3]
                    changed = True

    async def _terminate(self, record: _Command) -> bool:
        if sys.platform != "linux":
            return False
        process = record.process
        if process is None:
            return True
        try:
            self._observe(record)
            # A live unreaped child cannot have its PID reused. Never send a
            # group signal using a stale numeric marker after the leader exits.
            if process.poll() is None and os.getpgid(process.pid) == process.pid:
                process.send_signal(signal.SIGTERM)
            rows, _ = process_snapshot()
            for pid, ticks in record.descendants.items():
                if pid == process.pid:
                    continue  # Let the supervisor reap adopted descendants before it exits.
                if pid in rows and rows[pid][3] == ticks and rows[pid][4] != "Z":
                    with contextlib.suppress(ProcessLookupError):
                        descriptor = os.pidfd_open(pid, 0)
                        try:
                            current, _ = process_snapshot()
                            if pid in current and current[pid][3] == ticks:
                                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                        finally:
                            os.close(descriptor)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                process.poll()
                rows, complete = process_snapshot()
                alive = any(
                    row[4] != "Z"
                    and (row[1] == process.pid or record.descendants.get(pid) == row[3])
                    for pid, row in rows.items()
                )
                if complete and not alive and process.returncode is not None:
                    return True
                await asyncio.sleep(0.05)
            if process.poll() is None and os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ValueError, IndexError, AttributeError):
            return False
        return False

    async def _cleanup(
        self, record: _Command, readers: list[asyncio.Task[Any]], metadata: asyncio.Task[bytes]
    ) -> bool:
        try:
            observed = await self._terminate(record)
            await asyncio.wait_for(asyncio.gather(*readers, return_exceptions=True), 3)
            _, _, contained = parse_supervisor_observation(metadata.result())
            record.containment_complete = contained
            record.terminated = observed and contained
            return record.terminated and all(
                not task.cancelled() and task.exception() is None for task in readers
            )
        except Exception:
            return False
        finally:
            for task in readers:
                if not task.done():
                    task.cancel()
            if record.process:
                for pipe in (record.process.stdout, record.process.stderr):
                    if pipe:
                        pipe.close()

    async def _run(self, record: _Command) -> None:
        if sys.platform != "linux":
            record.state, record.finished = "outcome_unknown", time.monotonic()
            record.ready.set()
            return
        readers: list[asyncio.Task[Any]] = []
        state, exit_code = "outcome_unknown", None
        try:
            with self.files.directory(record.arguments["command_id"]) as directory:
                script = self.files.write_script(directory, record.arguments["command"])
                metadata_read, metadata_write = os.pipe()
                metadata_pipe = os.fdopen(metadata_read, "rb", buffering=0)
                try:
                    values = {
                        "shell": self.shells[record.arguments["shell"]],
                        "script": str(script),
                        "cwd": record.arguments["cwd"],
                        "timeout_seconds": record.arguments["timeout_seconds"],
                        "parent_pid": os.getpid(),
                        "metadata_fd": metadata_write,
                    }
                    record.process = subprocess.Popen(
                        [sys.executable, "-u", "-c", self.supervisor_source, json.dumps(values)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True,
                        pass_fds=(metadata_write,),
                        bufsize=0,
                    )
                except BaseException:
                    metadata_pipe.close()
                    raise
                finally:
                    os.close(metadata_write)
                try:
                    assert record.process.stdout and record.process.stderr
                    readers = [
                        asyncio.create_task(
                            self._capture(record, record.process.stdout, record.stdout)
                        ),
                        asyncio.create_task(
                            self._capture(record, record.process.stderr, record.stderr)
                        ),
                    ]
                    metadata = asyncio.create_task(self._metadata(metadata_pipe))
                    readers.append(metadata)
                    record.state = "running"
                    record.ready.set()
                    await asyncio.wait_for(
                        self._wait(record), record.arguments["timeout_seconds"] + 5
                    )
                    state, exit_code, _ = parse_supervisor_observation(
                        await asyncio.wait_for(asyncio.shield(metadata), 3)
                    )
                except asyncio.CancelledError:
                    record.cancelled = True
                    state = "cancelled"
                except TimeoutError:
                    state = "timed_out"
                except Exception:
                    state = "outcome_unknown"
                finally:
                    cleanup = asyncio.create_task(self._cleanup(record, readers, metadata))
                    while True:
                        try:
                            if not await asyncio.shield(cleanup):
                                state, exit_code = "outcome_unknown", None
                            break
                        except asyncio.CancelledError:
                            record.cancelled = True
                    metadata_pipe.close()
        except Exception:
            state, exit_code = "outcome_unknown", None
        finally:
            if record.cancelled and record.terminated:
                state, exit_code = "cancelled", None
            record.state, record.exit_code, record.finished = state, exit_code, time.monotonic()
            record.ready.set()

    async def close(self) -> None:
        self.closed = True
        await asyncio.gather(
            *(self.cancel(key) for key in tuple(self.handles)), return_exceptions=True
        )
