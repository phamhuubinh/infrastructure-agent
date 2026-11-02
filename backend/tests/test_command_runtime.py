"""Canonical command tools in real runtime/auth/context paths with a local fixture port."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace

import httpx
import pytest
from conftest import ScriptedBackend
from test_command_service import SHELL, TARGET, Transport

from orion.access import LocalAccessAdapter
from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from orion.application.command_tools import command_registrations
from orion.application.commands import CommandService
from orion.bootstrap import build_application
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime, RequestCancelled
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    MutationMode,
)
from orion.tool_runtime.mutation_authorization import MutationAuthorizationPolicy
from orion.tool_runtime.registry import ToolRegistryBuilder


class TerminalTransport(Transport):
    async def dispatch_command(self, target, operation, arguments, cancellation=None):
        result = await super().dispatch_command(target, operation, arguments, cancellation)
        if operation == "command.run":
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = self.executor.commands.status({"command_id": arguments["command_id"]})
                if result["state"] not in {"created", "running"}:
                    break
                await asyncio.sleep(0.01)
        return result


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode,allowed", [("read_only", False), ("auto", True), ("confirm", True), ("confirm", False)]
)
async def test_command_model_loop_scope_confirmation_and_private_protocol(tmp_path, mode, allowed):
    script = "echo command-script-output-marker"
    model_call = ModelToolCall(
        call_id="command-call",
        tool_name="system.command.run",
        arguments={"target_ref": TARGET, "shell": SHELL, "command": script},
    )
    backend = ScriptedBackend(
        [
            ModelTurn(tool_calls=(model_call,)),
            *[
                ModelTurn(
                    assistant=AssistantMessage(
                        content="Finished fixture."
                        if allowed
                        else "The command was blocked by policy; it was not executed."
                    )
                )
                for _ in range(4)
            ],
        ]
    )
    base = build_application(tmp_path / "orion.db", backend, seed_model_from_environment=False)
    store = base.store
    store.upsert_model_config("openai_compatible", "http://model.test/v1", "fixture", None)
    transport = TerminalTransport(store)
    service = CommandService(store, transport)
    builder = ToolRegistryBuilder()
    for registration in command_registrations(service):
        builder.register(registration.definition, registration.handler)
    registry = builder.freeze()
    diagnostic = BoundedModelInputDiagnostics()
    runtime = ChatRuntime(
        store,
        backend,
        registry,
        LocalAccessAdapter(),
        diagnostic_sink=diagnostic,
        mutation_authorization=MutationAuthorizationPolicy(
            None, lambda _, target: target == TARGET
        ),
    )
    application = replace(base, commands=service, registry=registry, runtime=runtime)
    origin = "https://command.test"
    app = create_app(
        application=application,
        remote_config=RemoteAccessConfig(
            True, "127.0.0.1", origin, hash_password("fixture-password")
        ),
    )
    session = store.create_session()
    store.set_session_mutation_mode(session, MutationMode(mode))
    request = runtime.begin(session, "Run the explicit local test fixture.")
    task = asyncio.create_task(runtime.run(session, request))
    try:
        if mode == "confirm":
            deadline = time.monotonic() + 5
            while store.pending_authorization(request, "command-call") is None:
                assert time.monotonic() < deadline
                await asyncio.sleep(0.01)
            assert transport.calls == []
            url = f"/api/sessions/{session}/requests/{request}/tool-authorizations/command-call"
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=origin,
                headers={"Origin": origin},
            ) as client:
                assert (await client.get(url + "/payload")).status_code == 401
                login = await client.post("/api/auth/login", json={"password": "fixture-password"})
                assert login.status_code == 200
                payload = await client.get(url + "/payload")
                assert payload.status_code == 200
                assert "no-store" in {
                    value.strip() for value in payload.headers["cache-control"].split(",")
                }
                assert payload.json()["arguments"]["command"] == script
                assert payload.json()["arguments"]["timeout_seconds"] == 60
                other = store.create_session()
                assert (
                    await client.get(url.replace(session, other) + "/payload")
                ).status_code == 404
                assert (await client.post(url, json={"decision": "allow"})).status_code == 409
                assert (
                    await client.post(url, json={"decision": "allow", "payload_hash": "0" * 64})
                ).status_code == 409
                assert transport.calls == []
                body = {"decision": "allow" if allowed else "deny"}
                if allowed:
                    body["payload_hash"] = payload.json()["payload_hash"]
                assert (await client.post(url, json=body)).status_code == 200
                assert (await client.get(url + "/payload")).status_code == 404
        await asyncio.wait_for(task, 10)
        assert bool(transport.calls) == allowed
        assert {tool.name for tool in backend.calls[0][1]} == {
            "system.command.run",
            "system.command.status",
            "system.command.cancel",
        }
        if allowed:
            continuation = backend.calls[1][0]
            calls = [call for message in continuation for call in message.tool_calls]
            assert calls[0].arguments["command"] == script
            assert "command-script-output-marker" in " ".join(
                message.content for message in continuation
            )
        database = "\n".join(store._connection.iterdump())
        assert "command-script-output-marker" not in database
        assert "command-script-output-marker" not in json.dumps(diagnostic.records(request))
        assert not runtime._transient_tool_calls and not runtime._transient_endpoint_results
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await service.close()
        await transport.executor.close()
        store.close()


@pytest.mark.anyio
async def test_runtime_stop_while_model_waits_terminates_original_command_tree(store, tmp_path):
    from test_worker_commands import invoke

    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    waiting = asyncio.Event()

    class WaitingBackend(ScriptedBackend):
        async def stream(self, messages, tools, settings, cancellation):
            if self.calls:
                waiting.set()
                await cancellation.wait()
                return
            self.calls.append((messages, tools))
            yield ModelTurnCompleted(
                turn=ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id="stop-call",
                            tool_name="system.command.run",
                            arguments={
                                "target_ref": TARGET,
                                "shell": SHELL,
                                "command": invoke(SHELL, script),
                            },
                        ),
                    )
                )
            )

    backend = WaitingBackend([])
    transport = Transport(store)
    service = CommandService(store, transport)
    builder = ToolRegistryBuilder()
    for registration in command_registrations(service):
        builder.register(registration.definition, registration.handler)
    runtime = ChatRuntime(
        store,
        backend,
        builder.freeze(),
        LocalAccessAdapter(),
        mutation_authorization=MutationAuthorizationPolicy(
            None, lambda _, target: target == TARGET
        ),
        on_request_interrupt=service.cancel_request,
    )
    session = store.create_session()
    store.set_session_mutation_mode(session, MutationMode.AUTO)
    request = runtime.begin(session, "Run the local long process fixture.")
    task = asyncio.create_task(runtime.run(session, request))
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        process = next(iter(transport.executor.commands.handles.values())).process
        assert process.poll() is None
        assert runtime.cancel(request)
        with pytest.raises(RequestCancelled):
            await asyncio.wait_for(task, 10)
        assert store.request(request)["status"] == "cancelled"
        record = store._connection.execute(
            "SELECT * FROM command_records WHERE request_id=?", (request,)
        ).fetchone()
        assert record["state"] == "cancelled"
        assert json.loads(record["observation_json"])["process_tree_terminated"]
        assert process.poll() is not None
        assert len([op for op, _ in transport.calls if op == "command.run"]) == 1
        assert not runtime._transient_tool_calls and not runtime._transient_endpoint_results
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await service.close()
        await transport.executor.close()
