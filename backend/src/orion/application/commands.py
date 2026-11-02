"""Scope-owned command handles; the control plane never executes shell text."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

from orion.contracts import RuntimeScope, ToolCall
from orion.contracts.commands import CommandPage, CommandRunInput
from orion.persistence.sqlite import SQLiteStore


class CommandTransport(Protocol):
    def configured(self, target_ref: str) -> bool: ...
    def command_connection(self, target_ref: str) -> object | None: ...
    def command_shells(self, target_ref: str) -> tuple[str, ...]: ...
    async def dispatch_command(
        self,
        endpoint_id: str,
        operation: str,
        arguments: dict[str, Any],
        cancellation: Callable[[], bool] | None = None,
    ) -> dict[str, Any]: ...


class CommandService:
    def __init__(self, store: SQLiteStore, transport: CommandTransport) -> None:
        self.store, self.transport = store, transport
        self._epochs: OrderedDict[str, object] = OrderedDict()
        self._monitors: dict[str, asyncio.Task[None]] = {}
        self._cancellations: dict[str, asyncio.Task[CommandPage]] = {}
        self.closed = False

    def _scope(self, scope: RuntimeScope, target: str) -> None:
        identity = self.store.session_identity(scope.session_id)
        if (
            identity is None
            or any(
                identity[key] != getattr(scope, key)
                for key in ("principal_id", "workspace_id", "project_id", "endpoint_id")
            )
            or (scope.endpoint_id is not None and scope.endpoint_id != target)
        ):
            raise PermissionError("Command scope does not match session identity")
        if not self.transport.configured(target):
            raise PermissionError("Command target is unavailable")

    @staticmethod
    def _unknown(record: dict[str, Any]) -> CommandPage:
        previous = json.loads(record["observation_json"])
        if previous["state"] in {"created", "running", "outcome_unknown"}:
            previous.update(state="outcome_unknown", exit_code=None, process_tree_terminated=False)
        previous.update(stdout="", stderr="", output_available=False)
        return CommandPage.model_validate(previous)

    def _accept(
        self,
        record: dict[str, Any],
        data: dict[str, Any],
        offsets: tuple[int, int] = (0, 0),
    ) -> CommandPage:
        page = CommandPage.model_validate({**data, "target_ref": record["target_ref"]})
        if (
            page.command_id != record["command_id"]
            or page.shell != record["shell"]
            or page.captured_output_bytes > record["max_output_bytes"]
            or (page.stdout_offset, page.stderr_offset) != offsets
        ):
            raise ValueError("Command observation identity or bounds mismatch")
        self.store.save_command_observation(page)
        return page

    def _remember(self, identity: str, epoch: object) -> None:
        self._epochs[identity] = epoch
        self._epochs.move_to_end(identity)
        while len(self._epochs) > 256:
            candidate = next(key for key in self._epochs if key not in self._monitors)
            del self._epochs[candidate]

    def _same_connection(self, record: dict[str, Any]) -> bool:
        epoch = self._epochs.get(record["command_id"])
        return (
            epoch is not None and self.transport.command_connection(record["target_ref"]) is epoch
        )

    async def run(self, call: ToolCall) -> CommandPage:
        values = CommandRunInput.model_validate(call.arguments)
        self._scope(call.runtime_scope, values.target_ref)
        if self.closed or len(self._monitors) >= 64:
            raise RuntimeError("Command service is unavailable")
        request = self.store.request(call.request_id or "")
        if request is None or request["session_id"] != call.runtime_scope.session_id:
            raise PermissionError("Command run requires an Orion-owned request")
        if call.cancellation_requested and call.cancellation_requested():
            raise PermissionError("Command was cancelled before dispatch")
        if self.store.previous_command_call(request["request_id"], call.call_id):
            previous, _ = self.store.create_command(
                call.runtime_scope, values, request["request_id"], call.call_id
            )
            return await self.status(call.runtime_scope, values.target_ref, previous["command_id"])
        prepare = getattr(self.transport, "prepare_command", None)
        if prepare is not None:
            await prepare(values.target_ref, call.cancellation_requested)
            self._scope(call.runtime_scope, values.target_ref)
            if self.closed or (call.cancellation_requested and call.cancellation_requested()):
                raise PermissionError("Command was cancelled before dispatch")
        epoch = self.transport.command_connection(values.target_ref)
        if epoch is not None and values.shell not in self.transport.command_shells(
            values.target_ref
        ):
            raise ValueError("unsupported_shell")
        record, created = self.store.create_command(
            call.runtime_scope, values, request["request_id"], call.call_id
        )
        identity = record["command_id"]
        if not created:
            return await self.status(call.runtime_scope, values.target_ref, identity)
        if epoch is None:
            page = self._unknown(record)
            self.store.save_command_observation(page)
            return page
        self._remember(identity, epoch)
        arguments = values.model_dump(exclude={"target_ref"})
        arguments["command_id"] = identity
        try:
            data = await self.transport.dispatch_command(
                values.target_ref, "command.run", arguments, call.cancellation_requested
            )
            if not self._same_connection(record):
                raise RuntimeError("Command connection changed during dispatch")
            page = self._accept(record, data)
        except asyncio.CancelledError:
            await asyncio.shield(self._cancel_record(record))
            raise
        except Exception:
            page = self._unknown(record)
            self.store.save_command_observation(page)
        if page.state in {"created", "running", "outcome_unknown"} and self._same_connection(
            record
        ):
            self._monitors[identity] = asyncio.create_task(
                self._monitor(record, call.stop_requested)
            )
        return page

    async def status(
        self,
        scope: RuntimeScope,
        target: str,
        identity: str,
        stdout_offset: int = 0,
        stderr_offset: int = 0,
    ) -> CommandPage:
        self._scope(scope, target)
        record = self.store.command_record(scope, identity, target)
        if not self._same_connection(record):
            if record["state"] in {"created", "running", "outcome_unknown"}:
                page = self._unknown(record)
                self.store.save_command_observation(page)
                return page
            return CommandPage.model_validate_json(record["observation_json"])
        try:
            data = await self.transport.dispatch_command(
                target,
                "command.status",
                {
                    "command_id": identity,
                    "stdout_offset": stdout_offset,
                    "stderr_offset": stderr_offset,
                },
            )
            if not self._same_connection(record):
                raise RuntimeError("Command connection changed during status")
            return self._accept(record, data, (stdout_offset, stderr_offset))
        except Exception:
            page = self._unknown(record)
            self.store.save_command_observation(page)
            return page

    async def _cancel_record(self, record: dict[str, Any]) -> CommandPage:
        identity = record["command_id"]
        task = self._cancellations.get(identity)
        if task is None:
            task = asyncio.create_task(self._send_cancel(record))
            self._cancellations[identity] = task
            task.add_done_callback(lambda done: self._cancellations.pop(identity, None))
        return await asyncio.shield(task)

    async def _send_cancel(self, record: dict[str, Any]) -> CommandPage:
        if not self._same_connection(record):
            page = self._unknown(record)
        else:
            try:
                data = await self.transport.dispatch_command(
                    record["target_ref"], "command.cancel", {"command_id": record["command_id"]}
                )
                if not self._same_connection(record):
                    raise RuntimeError("Command connection changed during cancel")
                return self._accept(record, data)
            except Exception:
                page = self._unknown(record)
        self.store.save_command_observation(page)
        return page

    async def cancel(self, scope: RuntimeScope, target: str, identity: str) -> CommandPage:
        self._scope(scope, target)
        record = self.store.command_record(scope, identity, target)
        if record["state"] not in {"created", "running", "outcome_unknown"}:
            return CommandPage.model_validate_json(record["observation_json"])
        return await self._cancel_record(record)

    async def _monitor(self, record: dict[str, Any], stop: Callable[[], bool] | None) -> None:
        identity, target = record["command_id"], record["target_ref"]
        try:
            while True:
                request = self.store.request(record["request_id"])
                if (
                    self.closed
                    or (stop and stop())
                    or request is None
                    or request["status"] in {"failed", "cancelled"}
                    or not self.store.session_exists(record["session_id"])
                ):
                    await self._cancel_record(record)
                    return
                if not self._same_connection(record):
                    self.store.save_command_observation(self._unknown(record))
                    return
                data = await self.transport.dispatch_command(
                    target, "command.status", {"command_id": identity}
                )
                if not self._same_connection(record):
                    raise RuntimeError("Command connection changed")
                if self._accept(record, data).state not in {"created", "running"}:
                    return
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            await asyncio.shield(self._cancel_record(record))
        except Exception:
            self.store.save_command_observation(self._unknown(record))
        finally:
            self._monitors.pop(identity, None)

    async def close(self) -> None:
        self.closed = True
        tasks = tuple(self._monitors.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*tuple(self._cancellations.values()), return_exceptions=True)
        close_transport = getattr(self.transport, "close_commands", None)
        if close_transport is not None:
            await close_transport()

    async def cancel_request(self, request_id: str) -> None:
        """Trusted runtime Stop/failure hook, never model-supplied authority."""
        with self.store._lock:
            rows = self.store._connection.execute(
                "SELECT * FROM command_records WHERE request_id=? "
                "AND state IN ('created','running','outcome_unknown')",
                (request_id,),
            ).fetchall()
        for row in rows:
            await self._cancel_record(dict(row))
