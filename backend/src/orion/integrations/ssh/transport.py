"""Exact target routing: paired worker or explicitly configured ephemeral SSH."""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orion.application.commands import CommandTransport
from orion.integrations.ssh.channel import SSHChannel
from orion.integrations.ssh.config import SSHConfiguration, SSHTarget
from orion.integrations.ssh.payload import helper_payload

if TYPE_CHECKING:
    from orion_endpoint.commands import CommandProcesses

LOCAL_WINDOWS = "local:windows"


def _channel(target: SSHTarget) -> SSHChannel:
    executable = shutil.which("ssh")
    if executable is None and os.name == "nt":
        candidate = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/OpenSSH/ssh.exe"
        if candidate.is_file():
            executable = str(candidate)
    if executable is None:
        raise RuntimeError("SSH client is unavailable")
    return SSHChannel(target, str(Path(executable).resolve(strict=True)), helper_payload())


async def _interruptible[T](operation: Awaitable[T], stop: Callable[[], bool] | None) -> T:
    task = asyncio.ensure_future(operation)
    try:
        while not task.done():
            if stop and stop():
                raise asyncio.CancelledError
            await asyncio.wait({task}, timeout=0.05)
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class CommandRouter:
    def __init__(
        self,
        worker: CommandTransport,
        configuration: SSHConfiguration,
        *,
        worker_enabled: bool,
        local: CommandProcesses | None = None,
        channel_factory: Callable[[SSHTarget], SSHChannel] = _channel,
    ) -> None:
        self.worker, self.configuration = worker, configuration
        self.worker_enabled, self.channel_factory = worker_enabled, channel_factory
        self.channels: dict[str, SSHChannel] = {}
        self.locks = {target.target_ref: asyncio.Lock() for target in configuration.targets}
        self.closed = False
        self.local = local

    def configured(self, target: str) -> bool:
        if target.startswith("local:"):
            return target == LOCAL_WINDOWS and self.local is not None and not self.closed
        if target.startswith("ssh:"):
            return self.configuration.enabled_target(target) is not None
        return self.worker_enabled and self.worker.configured(target)

    def command_connection(self, target: str) -> object | None:
        if target.startswith("local:"):
            return self.local if self.configured(target) else None
        if target.startswith("ssh:"):
            channel = self.channels.get(target)
            return channel if channel and channel.hello is not None and not channel.closed else None
        return self.worker.command_connection(target) if self.worker_enabled else None

    def command_shells(self, target: str) -> tuple[str, ...]:
        if target.startswith("local:"):
            return tuple(self.local.shells) if self.local and self.configured(target) else ()
        if target.startswith("ssh:"):
            channel = self.channels.get(target)
            return (
                tuple(channel.hello.command_shells)
                if channel and channel.hello and not channel.closed
                else ()
            )
        return self.worker.command_shells(target) if self.worker_enabled else ()

    async def prepare_command(self, target: str, stop: Callable[[], bool] | None = None) -> None:
        if not target.startswith("ssh:"):
            return
        configuration = self.configuration.enabled_target(target)
        if configuration is None or self.closed:
            raise PermissionError("SSH command target is unavailable")
        async with self.locks[target]:
            if self.closed:
                raise RuntimeError("SSH command transport is unavailable")
            if self.command_connection(target) is not None:
                return
            previous = self.channels.get(target)
            if previous:
                await previous.close()
            channel = self.channel_factory(configuration)
            self.channels[target] = channel
            await _interruptible(channel.start(), stop)

    async def dispatch_command(
        self,
        target: str,
        operation: str,
        arguments: dict[str, Any],
        cancellation: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if self.closed or not self.configured(target):
            raise PermissionError("Command target is unavailable")
        if target == LOCAL_WINDOWS and self.local is not None:
            if operation == "command.run":
                if cancellation and cancellation():
                    raise asyncio.CancelledError
                return await self.local.start(arguments)
            if operation == "command.status":
                return self.local.status(arguments)
            if operation == "command.cancel":
                result: dict[str, Any] = await self.local.cancel(arguments["command_id"])
                return result
            raise ValueError("Unsupported local command operation")
        if not target.startswith("ssh:"):
            return await self.worker.dispatch_command(target, operation, arguments, cancellation)
        channel = self.channels.get(target)
        if channel is None or self.command_connection(target) is not channel:
            raise RuntimeError("SSH command channel is unavailable")
        # Status/cancel never open a new SSH connection or recreate a handle.
        return await _interruptible(channel.call(operation, arguments), cancellation)

    def model_context(self) -> tuple[tuple[str, str, str], ...]:
        local = (
            (("system", LOCAL_WINDOWS, "This Windows PC (Orion Desktop)"),)
            if self.configured(LOCAL_WINDOWS)
            else ()
        )
        return local + tuple(
            ("system", target.target_ref, target.target_ref)
            for target in self.configuration.targets
            if target.commands
        )

    async def close_commands(self) -> None:
        self.closed = True
        if self.local is not None:
            await self.local.close()
        await asyncio.gather(
            *(channel.close() for channel in tuple(self.channels.values())), return_exceptions=True
        )
