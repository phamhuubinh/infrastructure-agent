"""One bounded SSH stdio channel; a lost connection never replays a request."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from orion.integrations.ssh.config import SSHTarget, ssh_argv
from orion.persistence.private_files import checked_path
from orion_endpoint.protocol import (
    MAX_INFLIGHT,
    MAX_MESSAGE,
    OPERATIONS,
    Cancel,
    Hello,
    Ping,
    Request,
    Result,
    decode,
)

ProcessFactory = Callable[[Sequence[str]], Awaitable[asyncio.subprocess.Process]]


class SSHChannelError(RuntimeError):
    def __init__(self, category: str = "unavailable") -> None:
        self.category = category
        super().__init__(category)


async def _spawn(argv: Sequence[str]) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MAX_MESSAGE + 1,
    )


class SSHChannel:
    """Fixed helper source is developer-owned; user scripts only enter validated RPC."""

    def __init__(
        self,
        target: SSHTarget,
        executable: str,
        helper_source: bytes,
        *,
        process_factory: ProcessFactory = _spawn,
        rpc_timeout: float = 15,
    ) -> None:
        if not 0 < len(helper_source) <= 131_072:
            raise ValueError("SSH helper source exceeds its bound")
        helper_source.decode("utf-8", errors="strict")
        self.target, self.executable = target, executable
        self._source, self._factory = helper_source, process_factory
        self.rpc_timeout = rpc_timeout
        self.process: asyncio.subprocess.Process | None = None
        self.hello: Hello | None = None
        self.closed = False
        self._started = False
        self._start_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, tuple[asyncio.Future[dict[str, Any]], bool]] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._close_task: asyncio.Task[None] | None = None
        self._last_pong = time.monotonic()

    async def start(self) -> None:
        async with self._start_lock:
            if self.closed:
                raise SSHChannelError()
            if self._started:
                return
            self._started = True
            try:
                # Recheck explicit administrative files at use, without reading
                # private-key contents or consulting workstation defaults.
                from pathlib import Path

                checked_path(Path(self.target.config_file))
                checked_path(Path(self.target.known_hosts_file))
                self.process = await self._factory(ssh_argv(self.target, self.executable))
                assert self.process.stdin and self.process.stdout and self.process.stderr
                self._tasks.append(asyncio.create_task(self._drain_stderr()))
                self.process.stdin.write(str(len(self._source)).encode() + b"\n" + self._source)
                await asyncio.wait_for(self.process.stdin.drain(), 5)
                message = decode(await asyncio.wait_for(self._line(), 10))
                if (
                    not isinstance(message, Hello)
                    or message.platform != "linux"
                    or not message.command_shells
                    or not {"command.run", "command.status", "command.cancel"}.issubset(
                        message.capabilities
                    )
                    or any(shell not in {"sh", "bash"} for shell in message.command_shells)
                ):
                    raise SSHChannelError("unsupported")
                self.hello = message
                self._tasks.extend(
                    (asyncio.create_task(self._receive()), asyncio.create_task(self._heartbeat()))
                )
            except asyncio.CancelledError:
                await self.close()
                raise
            except Exception:
                await self.close()
                raise SSHChannelError() from None

    async def _line(self) -> str:
        assert self.process and self.process.stdout
        line = await self.process.stdout.readline()
        if not line or len(line) > MAX_MESSAGE or not line.endswith(b"\n"):
            raise SSHChannelError()
        return line.decode("utf-8", errors="strict")

    async def _send(self, message: Request | Cancel | Ping) -> None:
        async with self._send_lock:
            if self.closed or not self.process or not self.process.stdin:
                raise SSHChannelError()
            self.process.stdin.write(message.model_dump_json().encode() + b"\n")
            await asyncio.wait_for(self.process.stdin.drain(), 3)

    async def call(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation not in {"command.run", "command.status", "command.cancel"}:
            raise SSHChannelError("policy_denied")
        if self.closed or self.hello is None:
            raise SSHChannelError()
        model, kind = OPERATIONS[operation]
        values = model.model_validate(arguments).model_dump()
        if len(self._pending) >= MAX_INFLIGHT:
            raise SSHChannelError("busy")
        identity = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[identity] = future, kind == "mutation"
        try:
            await self._send(Request(request_id=identity, operation=operation, arguments=values))
            return await asyncio.wait_for(asyncio.shield(future), self.rpc_timeout)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await self._send(Cancel(request_id=identity))
            raise
        except Exception:
            raise SSHChannelError(
                "outcome_unknown" if kind == "mutation" else "unavailable"
            ) from None
        finally:
            self._pending.pop(identity, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # Consume a close/send race even if the caller stopped waiting.

    async def _receive(self) -> None:
        try:
            while True:
                message = decode(await self._line())
                if isinstance(message, Ping) and message.type == "pong":
                    self._last_pong = time.monotonic()
                elif isinstance(message, Result):
                    pending = self._pending.get(message.request_id)
                    if pending and not pending[0].done():
                        if message.error:
                            pending[0].set_exception(SSHChannelError(message.error))
                        else:
                            pending[0].set_result(message.data or {})
                else:
                    raise SSHChannelError()
        except (Exception, asyncio.CancelledError):
            self._begin_close()

    async def _heartbeat(self) -> None:
        try:
            while True:
                await asyncio.sleep(5)
                if time.monotonic() - self._last_pong > 20:
                    raise SSHChannelError()
                await self._send(Ping(type="ping"))
        except (Exception, asyncio.CancelledError):
            self._begin_close()

    async def _drain_stderr(self) -> None:
        assert self.process and self.process.stderr
        # OpenSSH/server diagnostics may contain private paths or connection data.
        # Drain without buffering, forwarding, persisting or using them as output.
        while await self.process.stderr.read(8192):
            pass

    def _begin_close(self) -> asyncio.Task[None]:
        self.closed = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        return self._close_task

    async def close(self) -> None:
        await asyncio.shield(self._begin_close())

    async def _close(self) -> None:
        for future, mutation in self._pending.values():
            if not future.done():
                future.set_exception(
                    SSHChannelError("outcome_unknown" if mutation else "unavailable")
                )
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.process.wait(), 3)
        # This verifies only local ssh-client cleanup. The command service must
        # not turn it into a claim of remote process-tree termination.
