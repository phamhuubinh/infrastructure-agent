"""Bounded capability execution without a model, shell or Orion authority metadata."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import platform
import subprocess
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import psutil

from orion_endpoint.browser import Browser
from orion_endpoint.desktop import Desktop
from orion_endpoint.policy import Policy
from orion_endpoint.protocol import CHUNK_SIZE, MAX_TRANSFER, OPERATIONS, TRANSFERS, Hello


class Executor:
    def __init__(
        self,
        policy: Policy,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.policy = policy
        self.clock = clock
        self.sleeper = sleeper
        self.capture_lock = asyncio.Lock()
        self.last_capture = float("-inf")
        self.desktop = Desktop(policy)
        self.browser = Browser(policy)
        self.staging: dict[str, tuple[Path, Path, bool, int, float]] = {}
        self.mutation_lock = asyncio.Lock()
        self.browser_lock = asyncio.Lock()
        self.read_slots = asyncio.Semaphore(3)
        self.children: list[subprocess.Popen[bytes]] = []

    async def hello(self) -> Hello:
        from orion_endpoint import __version__

        enabled = {"system.inspect", "process.list"}
        if self.policy.read_roots:
            enabled |= {"file.list", "file.read"}
        if self.policy.write_roots:
            enabled |= {"file.write", "file.mkdir", "file.delete", "file.move"}
        if self.policy.applications:
            enabled.add("process.start")
        if self.policy.terminate:
            enabled.add("process.terminate")
        for name in ("clipboard_read", "clipboard_write"):
            if getattr(self.policy, name):
                enabled.add(name.replace("_", "."))
        geometry: list[dict[str, int]] = []
        try:
            geometry = await asyncio.to_thread(self.desktop.geometry)
        except Exception:
            pass
        if geometry:
            if self.policy.desktop_capture:
                enabled.add("screen.capture")
            if self.policy.desktop_control:
                enabled |= {name for name in OPERATIONS if name.startswith("desktop.")}
        if await self.browser.available():
            enabled |= {name for name in OPERATIONS if name.startswith("browser.")}
        return Hello.model_validate(
            {
                "type": "hello",
                "version": 1,
                "platform": "windows" if os.name == "nt" else "linux",
                "worker_version": __version__,
                "capabilities": sorted(enabled),
                "geometry": geometry,
            }
        )

    async def execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        entry = (OPERATIONS | TRANSFERS).get(operation)
        if entry is None:
            raise ValueError("invalid_input")
        model, kind = entry
        values = model.model_validate(args).model_dump()
        queued = self.clock()
        async with self.mutation_lock if kind == "mutation" else self.read_slots:
            if operation.startswith("desktop.") and self.clock() - queued > 2:
                raise ValueError("invalid_input")
            if operation.startswith("browser."):
                async with self.browser_lock:
                    return await self.browser.execute(operation.split(".")[1], values)
            if operation.startswith("screen."):
                async with self.capture_lock:
                    delay = self.last_capture + 1 / self.policy.max_fps - self.clock()
                    if delay > 0:
                        await self.sleeper(delay)
                    self.last_capture = self.clock()
                    return await asyncio.to_thread(self.desktop.capture, values["monitor"])
            # Mutations run synchronously once admitted: cancellation cannot claim rollback.
            if kind == "read":
                return await asyncio.to_thread(self._execute, operation, values)
            return self._execute(operation, values)

    def _execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        if operation == "system.inspect":
            memory = psutil.virtual_memory()
            disks = []
            for partition in psutil.disk_partitions()[:16]:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append(
                        {"mount": partition.mountpoint, "total": usage.total, "free": usage.free}
                    )
                except OSError:
                    continue
            return {
                "os": platform.system(),
                "release": platform.release()[:100],
                "cpu_count": psutil.cpu_count(),
                "cpu_percent": psutil.cpu_percent(),
                "memory_total": memory.total,
                "memory_available": memory.available,
                "uptime_seconds": int(time.time() - psutil.boot_time()),
                "disks": disks,
                "network": {
                    "sent": psutil.net_io_counters().bytes_sent,
                    "received": psutil.net_io_counters().bytes_recv,
                },
            }
        if operation == "process.list":
            rows = []
            # No command lines or environments. Bounded result, cursor by PID.
            for process in psutil.process_iter(["pid", "name", "create_time"]):
                try:
                    info = process.info
                    if (
                        info["pid"] >= args["offset"]
                        and args["filter"].lower() in (info["name"] or "").lower()
                    ):
                        rows.append(
                            {
                                "pid": info["pid"],
                                "name": (info["name"] or "")[:256],
                                "created_at": info["create_time"],
                            }
                        )
                        if len(rows) >= args["limit"]:
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return {"processes": rows, "next_offset": rows[-1]["pid"] + 1 if rows else None}
        if operation == "process.start":
            alias = self.policy.applications.get(args["alias"])
            if alias is None or (args["args"] and not alias.allow_args):
                raise PermissionError("policy_denied")
            executable = Path(alias.executable).resolve(strict=True)
            if executable.suffix.lower() in {".bat", ".cmd", ".ps1", ".sh", ".py"}:
                raise PermissionError("policy_denied")
            if executable.stem.lower() in {
                "sh",
                "bash",
                "zsh",
                "cmd",
                "powershell",
                "pwsh",
                "python",
                "python3",
                "pythonw",
                "py",
                "env",
                "busybox",
                "wscript",
                "cscript",
                "mshta",
                "rundll32",
                "reg",
                "regsvr32",
                "node",
                "perl",
                "ruby",
            }:
                raise PermissionError("policy_denied")
            argv = [*alias.fixed_args, *args["args"]]
            if any(len(arg) > 512 or "\x00" in arg for arg in argv):
                raise ValueError("invalid_input")
            if len(self.children) >= 32:
                self.children = [child for child in self.children if child.poll() is None]
                if len(self.children) >= 32:
                    raise RuntimeError("unavailable")
            child = subprocess.Popen(
                [str(executable), *argv],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            self.children.append(child)
            process = psutil.Process(child.pid)
            return {
                "pid": child.pid,
                "name": process.name()[:256],
                "created_at": process.create_time(),
            }
        if operation == "process.terminate":
            if not self.policy.terminate or args["pid"] == os.getpid():
                raise PermissionError("policy_denied")
            process = psutil.Process(args["pid"])
            if (
                process.name() != args["expected_name"]
                or process.create_time() != args["expected_created_at"]
            ):
                raise FileExistsError("conflict")
            process.terminate()
            try:
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                raise RuntimeError("outcome_unknown") from None
            return {"terminated": True}
        if operation.startswith("clipboard."):
            import pyperclip

            if operation.endswith("read"):
                if not self.policy.clipboard_read:
                    raise PermissionError("policy_denied")
                return {"text": str(pyperclip.paste())[:4096]}
            if not self.policy.clipboard_write:
                raise PermissionError("policy_denied")
            pyperclip.copy(args["text"])
            return {"written": True}
        if operation.startswith("desktop."):
            return self.desktop.input(operation.split(".")[1], args)
        if operation.startswith("transfer."):
            return self._transfer(operation, args)
        path = self.policy.path(args["path"], write=OPERATIONS[operation][1] == "mutation")
        if operation == "file.list":
            entries: list[dict[str, Any]] = []
            with os.scandir(path) as iterator:
                for index, item in enumerate(iterator):
                    if index > args["offset"] + 10_000:
                        return {"entries": entries, "next_offset": index}
                    if index < args["offset"]:
                        continue
                    if args["filter"].lower() not in item.name.lower():
                        continue
                    info = item.stat(follow_symlinks=False)
                    entries.append(
                        {
                            "name": item.name[:256],
                            "directory": item.is_dir(follow_symlinks=False),
                            "symlink": item.is_symlink(),
                            "size": info.st_size,
                        }
                    )
                    if len(entries) >= args["limit"]:
                        return {"entries": entries, "next_offset": index + 1}
            return {"entries": entries, "next_offset": None}
        if operation == "file.read":
            if not path.is_file():
                raise ValueError("invalid_input")
            with path.open("rb") as stream:
                stream.seek(args["offset"])
                raw = stream.read(args["length"])
                info = os.fstat(stream.fileno())
                size = info.st_size
            return {
                "content_b64": base64.b64encode(raw).decode(),
                "text": raw.decode("utf-8", errors="replace"),
                "offset": args["offset"],
                "size": size,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "file_identity": f"{info.st_ino}:{info.st_mtime_ns}:{info.st_size}",
            }
        if operation == "file.write":
            raw = args["content"].encode()
            if len(raw) > CHUNK_SIZE:
                raise ValueError("invalid_input")
            self._publish(path, raw, args["overwrite"])
        elif operation == "file.mkdir":
            path.mkdir()
        elif operation == "file.delete":
            path.rmdir() if path.is_dir() else path.unlink()
        elif operation == "file.move":
            destination = self.policy.path(args["destination"], write=True)
            if path.is_dir():
                raise ValueError("invalid_input")
            if args["overwrite"]:
                os.replace(path, destination)
            else:
                os.link(path, destination)
                path.unlink()
        return {"verified": True, "exists": path.exists()}

    def _publish(self, path: Path, raw: bytes, overwrite: bool) -> None:
        descriptor, temp = tempfile.mkstemp(prefix=".orion-upload-", dir=path.parent)
        staging = Path(temp)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._commit(staging, path, overwrite)
        finally:
            staging.unlink(missing_ok=True)

    def _commit(self, staging: Path, path: Path, overwrite: bool) -> None:
        if self.policy.path(str(path), write=True) != path:
            raise PermissionError("policy_denied")
        if overwrite:
            os.replace(staging, path)
        else:
            # Hard-link publish is atomic and fails if the final file already exists.
            os.link(staging, path)
            staging.unlink()

    def _transfer(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        for key, (stage, _, _, _, expiry) in list(self.staging.items()):
            if expiry < now:
                stage.unlink(missing_ok=True)
                del self.staging[key]
        key = args["transfer_id"]
        if operation == "transfer.begin":
            if key in self.staging or len(self.staging) >= 2:
                raise FileExistsError("conflict")
            path = self.policy.path(args["path"], write=True)
            if path.exists() and not args["overwrite"]:
                raise FileExistsError("conflict")
            descriptor, temp = tempfile.mkstemp(prefix=".orion-upload-", dir=path.parent)
            os.close(descriptor)
            self.staging[key] = (Path(temp), path, args["overwrite"], 0, now + 60)
            return {"started": True}
        if key not in self.staging:
            if operation == "transfer.abort":
                return {"aborted": True}
            raise ValueError("invalid_input")
        stage, path, overwrite, size, _ = self.staging[key]
        if operation == "transfer.chunk":
            raw = base64.b64decode(args["content_b64"], validate=True)
            if len(raw) > CHUNK_SIZE or size + len(raw) > MAX_TRANSFER or size != args["offset"]:
                raise ValueError("invalid_input")
            with stage.open("ab") as stream:
                stream.write(raw)
            self.staging[key] = (stage, path, overwrite, size + len(raw), now + 60)
            return {"size": size + len(raw)}
        try:
            if operation == "transfer.finish":
                self._commit(stage, path, overwrite)
                return {"size": path.stat().st_size, "published": True}
            return {"aborted": True}
        finally:
            stage.unlink(missing_ok=True)
            del self.staging[key]

    async def close(self) -> None:
        await self.browser.close()
        for stage, *_ in self.staging.values():
            stage.unlink(missing_ok=True)
        self.staging.clear()
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                try:
                    await asyncio.to_thread(child.wait, timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    await asyncio.to_thread(child.wait, timeout=3)
        self.children.clear()
