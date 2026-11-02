"""Server ownership, no replay, restart recovery and transient command evidence."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

import pytest

from orion.application.commands import CommandService
from orion.contracts import RuntimeScope, ToolCall
from orion_endpoint.executor import Executor
from orion_endpoint.policy import Policy

TARGET = "a" * 32
SHELL = "cmd" if os.name == "nt" else "sh"


class Transport:
    def __init__(self, store):
        self.store = store
        self.executor = Executor(Policy(commands=True))
        self.epoch = object()
        self.calls = []
        self.drop_ack = False

    def configured(self, target):
        return target == TARGET

    def command_connection(self, target):
        return self.epoch

    def command_shells(self, target):
        return tuple(self.executor.commands.shells)

    async def dispatch_command(self, target, operation, arguments, cancellation=None):
        # The committed server record must exist before any worker run is attempted.
        assert self.store._connection.execute(
            "SELECT command_id FROM command_records WHERE command_id=?",
            (arguments["command_id"],),
        ).fetchone()
        self.calls.append((operation, dict(arguments)))
        result = await self.executor.execute(operation, arguments)
        if operation == "command.run" and self.drop_ack:
            raise OSError("lost acknowledgement")
        return result


def call(store, *, script="echo private-output-marker", stop=None):
    session = store.create_session()
    request = store.create_request(session)
    scope = RuntimeScope(session_id=session, principal_id="local", workspace_id="local")
    return ToolCall(
        call_id="once",
        tool_name="system.command.run",
        arguments={"target_ref": TARGET, "shell": SHELL, "command": script},
        runtime_scope=scope,
        request_id=request,
        stop_requested=stop,
    )


async def terminal(service, owner, identity):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = await service.status(owner.runtime_scope, TARGET, identity)
        if result.state not in {"created", "running"}:
            return result
        await asyncio.sleep(0.02)
    pytest.fail("Command service did not terminate")


@pytest.mark.anyio
async def test_handle_before_dispatch_duplicate_and_safe_metadata(store):
    transport = Transport(store)
    service = CommandService(store, transport)
    owner = call(store)
    try:
        first = await service.run(owner)
        result = await terminal(service, owner, first.command_id)
        assert result.state == "succeeded" and "private-output-marker" in result.stdout
        duplicate = await service.run(owner)
        assert duplicate.command_id == first.command_id
        assert len([op for op, _ in transport.calls if op == "command.run"]) == 1
        changed = owner.model_copy(
            update={"arguments": {**owner.arguments, "command": "echo changed"}}
        )
        with pytest.raises(PermissionError):
            await service.run(changed)
        serialized = "\n".join(store._connection.iterdump())
        assert owner.arguments["command"] not in serialized
        assert "private-output-marker" not in serialized
        assert (
            json.loads(
                store.command_record(owner.runtime_scope, first.command_id, TARGET)[
                    "observation_json"
                ]
            )["output_available"]
            is False
        )
    finally:
        await service.close()
        await transport.executor.close()


@pytest.mark.anyio
async def test_forged_handle_scopes_and_target_never_reach_worker(store):
    transport = Transport(store)
    service = CommandService(store, transport)
    owner = call(store)
    try:
        first = await service.run(owner)
        await terminal(service, owner, first.command_id)
        for override in (
            {"principal_id": "other"},
            {"workspace_id": "other"},
            {"session_id": store.create_session()},
            {"project_id": "other"},
            {"endpoint_id": "b" * 32},
        ):
            scope = owner.runtime_scope.model_copy(update=override)
            before = len(transport.calls)
            with pytest.raises(PermissionError):
                await service.status(scope, TARGET, first.command_id)
            with pytest.raises(PermissionError):
                await service.cancel(scope, TARGET, first.command_id)
            assert len(transport.calls) == before
        with pytest.raises(PermissionError):
            await service.status(owner.runtime_scope, "b" * 32, first.command_id)
    finally:
        await service.close()
        await transport.executor.close()


@pytest.mark.anyio
async def test_lost_ack_reconciles_same_connection_without_mutation_replay(store):
    transport = Transport(store)
    transport.drop_ack = True
    service = CommandService(store, transport)
    owner = call(store)
    try:
        initial = await service.run(owner)
        assert initial.state == "outcome_unknown"
        resolved = await terminal(service, owner, initial.command_id)
        assert resolved.state == "succeeded"
        assert len([op for op, _ in transport.calls if op == "command.run"]) == 1
        transport.epoch = object()
        unavailable = await service.status(owner.runtime_scope, TARGET, initial.command_id)
        assert unavailable.output_available is False and unavailable.stdout == ""
    finally:
        await service.close()
        await transport.executor.close()


@pytest.mark.anyio
async def test_stop_cancels_original_request_command_without_reapproval(store, tmp_path):

    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    from test_worker_commands import invoke

    stopped = asyncio.Event()
    transport = Transport(store)
    service = CommandService(store, transport)
    owner = call(store, script=invoke(SHELL, script), stop=stopped.is_set)
    try:
        initial = await service.run(owner)
        assert initial.state == "running"
        stopped.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            record = store.command_record(owner.runtime_scope, initial.command_id, TARGET)
            if record["state"] == "cancelled":
                break
            await asyncio.sleep(0.02)
        assert record["state"] == "cancelled"
        assert json.loads(record["observation_json"])["process_tree_terminated"] is True
        assert "command.cancel" in [op for op, _ in transport.calls]
    finally:
        await service.close()
        await transport.executor.close()


@pytest.mark.anyio
async def test_disconnected_active_handle_stays_unknown_and_is_not_relaunched(store, tmp_path):
    from test_worker_commands import invoke

    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    transport = Transport(store)
    service = CommandService(store, transport)
    owner = call(store, script=invoke(SHELL, script))
    try:
        initial = await service.run(owner)
        await transport.executor.close()
        transport.epoch = object()
        before = len(transport.calls)
        result = await service.status(owner.runtime_scope, TARGET, initial.command_id)
        assert result.state == "outcome_unknown" and not result.output_available
        assert len(transport.calls) == before
        assert len([op for op, _ in transport.calls if op == "command.run"]) == 1
    finally:
        await service.close()
        await transport.executor.close()


@pytest.mark.anyio
async def test_run_rejects_unowned_request_or_unsupported_shell(store):
    transport = Transport(store)
    service = CommandService(store, transport)
    owner = call(store)
    try:
        with pytest.raises(PermissionError):
            await service.run(owner.model_copy(update={"request_id": uuid.uuid4().hex}))
        other = "sh" if os.name == "nt" else "powershell"
        with pytest.raises(ValueError, match="unsupported_shell"):
            await service.run(
                owner.model_copy(update={"arguments": {**owner.arguments, "shell": other}})
            )
        assert transport.calls == []
    finally:
        await service.close()
        await transport.executor.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "override",
    [
        {"command_id": "f" * 32},
        {"shell": "bash"},
        {"captured_output_bytes": 4_194_304},
        {"stdout_offset": 1},
        {"stdout": "injected", "next_stdout_offset": 0},
        {"state": "cancelled", "process_tree_terminated": False},
    ],
)
async def test_malformed_worker_observation_cannot_become_verified_evidence(store, override):
    class MalformedTransport(Transport):
        async def dispatch_command(self, target, operation, arguments, cancellation=None):
            data = await super().dispatch_command(target, operation, arguments, cancellation)
            return {**data, **override}

    transport = MalformedTransport(store)
    service = CommandService(store, transport)
    owner = call(store)
    try:
        result = await service.run(owner)
        assert result.state == "outcome_unknown"
        assert result.stdout == result.stderr == "" and not result.output_available
        assert len([op for op, _ in transport.calls if op == "command.run"]) == 1
    finally:
        await service.close()
        await transport.executor.close()


@pytest.mark.anyio
async def test_manager_wire_contract_and_public_endpoint_bypass_denial(store):
    from orion.endpoints.manager import Connection, EndpointError, EndpointManager
    from orion.endpoints.persistence import EndpointStore
    from orion_endpoint.protocol import Request, Result, decode

    identities = EndpointStore(store)
    paired = identities.pair(identities.token()["token"], "Command wire fixture")
    target = paired["endpoint_id"]
    executor = Executor(Policy(commands=True))
    manager = EndpointManager(identities)

    class WireSocket:
        async def send_text(self, text):
            request = decode(text)
            if not isinstance(request, Request):
                return
            data = await executor.execute(request.operation, request.arguments)
            response = decode(Result(request_id=request.request_id, data=data).model_dump_json())
            connection.pending[request.request_id][0].set_result(response)

        async def close(self, code=1000):
            pass

    connection = Connection(WireSocket(), await executor.hello())
    manager.connections[target] = connection
    service = CommandService(store, manager)
    owner = call(store)
    owner = owner.model_copy(update={"arguments": {**owner.arguments, "target_ref": target}})
    try:
        with pytest.raises(EndpointError, match="policy_denied"):
            await manager.dispatch(target, "command.run", {})
        initial = await service.run(owner)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            page = await service.status(owner.runtime_scope, target, initial.command_id)
            if page.state not in {"created", "running"}:
                break
            await asyncio.sleep(0.02)
        assert page.state == "succeeded" and "private-output-marker" in page.stdout
        assert manager.command_connection(target) is connection
        assert SHELL in manager.command_shells(target)
        await manager.detach(target, connection)
        lost = await service.status(owner.runtime_scope, target, initial.command_id)
        assert lost.state == "succeeded" and not lost.output_available
    finally:
        await service.close()
        await executor.close()
        await manager.close()
