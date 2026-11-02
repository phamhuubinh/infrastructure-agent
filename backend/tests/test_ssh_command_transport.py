"""Production routing/ownership with synthetic SSH observations, no remote account."""

import asyncio
import json

import pytest
from conftest import ScriptedBackend
from test_command_service import Transport, call

from orion.application.commands import CommandService
from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, MutationMode
from orion.integrations.ssh.config import SSHConfiguration
from orion.integrations.ssh.transport import CommandRouter
from orion_endpoint.protocol import Hello


def configuration(tmp_path):
    return {
        "format_version": 1,
        "targets": [
            {
                "target_ref": "ssh:lab",
                "ssh_alias": "private-alias",
                "config_file": str(tmp_path / "private config"),
                "known_hosts_file": str(tmp_path / "private hosts"),
                "commands": True,
            }
        ],
    }


class Channel:
    """Synthetic data only; does not execute a command locally or over SSH."""

    def __init__(self, store):
        self.store = store
        self.hello = None
        self.closed = False
        self.calls = []
        self.started = 0
        self.commands = {}

    async def start(self):
        self.started += 1
        self.hello = Hello(
            platform="linux",
            worker_version="synthetic",
            command_shells=["sh"],
            capabilities=["command.run", "command.status", "command.cancel"],
        )

    async def call(self, operation, arguments):
        self.calls.append((operation, arguments))
        identity = arguments["command_id"]
        if operation == "command.run":
            assert self.store._connection.execute(
                "SELECT 1 FROM command_records WHERE command_id=?", (identity,)
            ).fetchone()
            self.commands[identity] = {
                "command_id": identity,
                "shell": "sh",
                "state": "succeeded",
                "exit_code": 0,
                "stdout": "synthetic-output",
                "stderr": "",
                "duration_seconds": 0.01,
                "process_tree_terminated": True,
                "captured_output_bytes": 16,
                "next_stdout_offset": 16,
                "next_stderr_offset": 0,
                "stdout_offset": 0,
                "stderr_offset": 0,
            }
        return self.commands[identity]

    async def close(self):
        self.closed = True


@pytest.mark.anyio
async def test_capability_prepare_commit_before_run_and_no_reconnect_on_duplicate(store, tmp_path):
    worker = Transport(store)
    channels = []

    def factory(_):
        channel = Channel(store)
        channels.append(channel)
        return channel

    router = CommandRouter(
        worker,
        SSHConfiguration.model_validate_json(json.dumps(configuration(tmp_path))),
        worker_enabled=False,
        channel_factory=factory,
    )
    service = CommandService(store, router)
    owner = call(store).model_copy(
        update={"arguments": {"target_ref": "ssh:lab", "shell": "sh", "command": "private-script"}}
    )
    try:
        first = await service.run(owner)
        assert first.state == "succeeded" and first.stdout == "synthetic-output"
        assert channels[0].started == 1
        channels[0].closed = True
        duplicate = await service.run(owner)
        assert duplicate.command_id == first.command_id and not duplicate.output_available
        assert len(channels) == 1 and len(channels[0].calls) == 1
        other = call(store).model_copy(update={"arguments": owner.arguments})
        await service.run(other)
        assert len(channels) == 2
        assert not router.configured("ssh:unknown") and not router.configured("a" * 32)
        assert "private-alias" not in repr(router.model_context())
        assert "private-script" not in "\n".join(store._connection.iterdump())
    finally:
        await service.close()
        await worker.executor.close()
    assert all(channel.closed for channel in channels)


@pytest.mark.anyio
async def test_stop_during_capability_prepare_never_creates_command_handle(store, tmp_path):
    preparing = asyncio.Event()
    stop = asyncio.Event()

    class SlowChannel(Channel):
        async def start(self):
            preparing.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.closed = True

    worker = Transport(store)
    router = CommandRouter(
        worker,
        SSHConfiguration.model_validate_json(json.dumps(configuration(tmp_path))),
        worker_enabled=False,
        channel_factory=lambda _: SlowChannel(store),
    )
    service = CommandService(store, router)
    owner = call(store).model_copy(
        update={
            "arguments": {"target_ref": "ssh:lab", "shell": "sh", "command": "never-run"},
            "cancellation_requested": stop.is_set,
        }
    )
    task = asyncio.create_task(service.run(owner))
    try:
        await asyncio.wait_for(preparing.wait(), 2)
        stop.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert store._connection.execute("SELECT count(*) FROM command_records").fetchone()[0] == 0
    finally:
        await service.close()
        await worker.executor.close()


@pytest.mark.anyio
async def test_bootstrap_ssh_tools_work_without_enabling_paired_endpoints(tmp_path, monkeypatch):
    config = tmp_path / "ssh.json"
    config.write_text(json.dumps(configuration(tmp_path)))
    monkeypatch.setenv("ORION_SSH_COMMAND_CONFIG", str(config))
    model_call = ModelToolCall(
        call_id="ssh-call",
        tool_name="system.command.run",
        arguments={"target_ref": "ssh:lab", "shell": "sh", "command": "private-model-script"},
    )
    backend = ScriptedBackend(
        [
            ModelTurn(tool_calls=(model_call,)),
            *[ModelTurn(assistant=AssistantMessage(content="Fixture complete.")) for _ in range(4)],
        ]
    )
    app = build_application(
        tmp_path / "orion.db", backend, endpoint_enabled=False, seed_model_from_environment=False
    )
    app.store.upsert_model_config("openai_compatible", "http://model.test/v1", "fixture", None)
    channel = Channel(app.store)
    app.commands.transport.channel_factory = lambda _: channel
    session = app.store.create_session()
    app.store.set_session_mutation_mode(session, MutationMode.AUTO)
    request = app.runtime.begin(session, "Run the synthetic SSH contract fixture.")
    try:
        await app.runtime.run(session, request)
        names = {tool.name for tool in backend.calls[0][1]}
        assert {"system.command.run", "system.command.status", "system.command.cancel"} <= names
        assert not any(name.startswith("endpoint.") for name in names)
        assert channel.started == 1 and channel.calls[0][0] == "command.run"
        assert "private-model-script" in str(backend.calls[1][0])
        assert "private-model-script" not in "\n".join(app.store._connection.iterdump())
        assert not app.endpoint_enabled
    finally:
        await app.commands.close()
        await app.endpoints.close()
        app.store.close()


@pytest.mark.anyio
async def test_device_scope_cannot_prepare_ssh_and_context_does_not_offer_other_targets(
    store, tmp_path
):
    from orion.chat.context_builder import ContextBuilder
    from orion.contracts import RuntimeScope, ToolCall, ToolDefinition, ToolResult
    from orion.endpoints.persistence import EndpointStore
    from orion.tool_runtime.registry import ToolRegistryBuilder
    from orion.tool_runtime.runner import ToolRunner

    endpoints = EndpointStore(store)
    identity = endpoints.pair(endpoints.token()["token"], "Device scope fixture")
    session = store.create_session(endpoint_id=identity["endpoint_id"])
    scope = RuntimeScope(
        session_id=session,
        principal_id="local",
        workspace_id="local",
        endpoint_id=identity["endpoint_id"],
    )
    worker = Transport(store)

    def forbidden(_):
        raise AssertionError("Device Chat must not prepare another SSH target")

    router = CommandRouter(
        worker,
        SSHConfiguration.model_validate_json(json.dumps(configuration(tmp_path))),
        worker_enabled=False,
        channel_factory=forbidden,
    )
    service = CommandService(store, router)
    try:
        with pytest.raises(PermissionError):
            await service.run(
                ToolCall(
                    call_id="blocked",
                    tool_name="system.command.run",
                    arguments={"target_ref": "ssh:lab", "shell": "sh", "command": "never-run"},
                    request_id=store.create_request(session),
                    runtime_scope=scope,
                )
            )
        context = ContextBuilder(store, (("system", "ssh:lab", "SSH fixture"),))
        assert "ssh:lab" not in str(context.build(session))
        chat = store.create_session()
        assert "string unchanged" in str(context.build(chat)) and "ssh:lab" in str(
            context.build(chat)
        )
        builder = ToolRegistryBuilder()
        builder.register(
            ToolDefinition(
                name="linux.system.inspect",
                handler_key="fixture",
                description="Existing Linux read",
                operation_kind="read",
                input_schema={
                    "type": "object",
                    "properties": {"target_ref": {"type": "string"}},
                    "required": ["target_ref"],
                },
            ),
            lambda _: pytest.fail("Legacy read cannot escape Device Chat target binding"),
        )
        blocked = ToolRunner(builder.freeze()).prepare(
            ModelToolCall(
                call_id="legacy-read",
                tool_name="linux.system.inspect",
                arguments={"target_ref": "legacy-other-host"},
            ),
            scope,
        )
        assert isinstance(blocked, ToolResult) and blocked.error.code == "operation_blocked"
    finally:
        await service.close()
        await worker.executor.close()
