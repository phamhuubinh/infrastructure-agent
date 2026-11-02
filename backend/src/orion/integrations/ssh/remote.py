"""Ephemeral stdlib-only Linux command helper over a bounded SSH stdio lease."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from .remote_protocol import MAX_MESSAGE, encode_message, parse_message
from .remote_runner import RemoteCommands


class Helper:
    def __init__(self, commands: RemoteCommands) -> None:
        self.commands = commands
        self.pending: dict[str, asyncio.Task[None]] = {}
        self.seen: set[str] = set()
        self.writer_lock = asyncio.Lock()
        self.input_transport: asyncio.ReadTransport | None = None

    async def _write(self, raw: bytes) -> None:
        loop = asyncio.get_running_loop()
        fd = sys.stdout.fileno()
        offset = 0
        while offset < len(raw):
            try:
                count = os.write(fd, raw[offset:])
                if count == 0:
                    raise OSError("SSH output closed")
                offset += count
            except BlockingIOError:
                writable = asyncio.Event()
                loop.add_writer(fd, writable.set)
                try:
                    await writable.wait()
                finally:
                    loop.remove_writer(fd)

    async def _locked_send(self, raw: bytes) -> None:
        async with self.writer_lock:
            await self._write(raw)

    async def send(self, value: dict[str, Any]) -> None:
        await asyncio.wait_for(self._locked_send(encode_message(value)), 3)

    async def execute(self, message: dict[str, Any]) -> None:
        identity, operation, arguments = (
            message["request_id"],
            message["operation"],
            message["arguments"],
        )
        result: dict[str, Any] = {"type": "result", "request_id": identity, "data": {}}
        mutation = operation != "command.status"
        try:
            if operation == "command.run":
                result["data"] = await self.commands.start(arguments)
            elif operation == "command.cancel":
                result["data"] = await self.commands.cancel(arguments["command_id"])
            else:
                result["data"] = self.commands.status(arguments)
        except asyncio.CancelledError:
            result["error"] = "outcome_unknown" if mutation else "cancelled"
        except FileExistsError:
            result["error"] = "conflict"
        except (ValueError, KeyError):
            result["error"] = "invalid_input"
        except Exception:
            result["error"] = "outcome_unknown" if mutation else "unavailable"
        try:
            await self.send(result)
        except (Exception, asyncio.CancelledError):
            if self.input_transport:
                self.input_transport.close()
        finally:
            self.pending.pop(identity, None)

    async def serve(self) -> None:
        if sys.platform != "linux":
            raise OSError("Linux helper is unavailable")
        reader = asyncio.StreamReader(limit=MAX_MESSAGE + 1)
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer
        )
        self.input_transport = transport
        os.set_blocking(sys.stdout.fileno(), False)
        try:
            await self.send(
                {
                    "type": "hello",
                    "version": 1,
                    "platform": "linux",
                    "worker_version": "ssh-stdlib-v1",
                    "capabilities": ["command.run", "command.status", "command.cancel"],
                    "command_shells": list(self.commands.shells),
                }
            )
            while True:
                raw = await asyncio.wait_for(reader.readline(), 25)
                if not raw:
                    break
                message = parse_message(raw)
                if message["type"] == "ping":
                    await self.send({"type": "pong"})
                elif message["type"] == "cancel":
                    task = self.pending.get(message["request_id"])
                    if task:
                        task.cancel()
                else:
                    identity = message["request_id"]
                    if identity in self.seen:
                        await self.send(
                            {"type": "result", "request_id": identity, "error": "conflict"}
                        )
                        continue
                    if len(self.seen) >= 65_536:
                        raise ValueError("SSH RPC lifetime bound")
                    self.seen.add(identity)
                    if len(self.pending) >= 4:
                        await self.send(
                            {"type": "result", "request_id": identity, "error": "unavailable"}
                        )
                        continue
                    self.pending[identity] = asyncio.create_task(self.execute(message))
        finally:
            transport.close()
            tasks = tuple(self.pending.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.commands.close()


def main(supervisor_source: str) -> None:
    """Bundle entry point only; never called by the control-plane process."""
    exit_code = 125
    loop: asyncio.AbstractEventLoop | None = None
    try:
        if sys.platform != "linux" or sys.version_info < (3, 10):
            raise OSError("Linux Python3.10 helper is unavailable")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        commands = RemoteCommands(supervisor_source)
        loop.run_until_complete(Helper(commands).serve())
        exit_code = 0
    except BaseException:
        pass  # No private paths, command text or stderr traceback leaves the helper.
    finally:
        if loop:
            loop.close()
        os._exit(exit_code)
