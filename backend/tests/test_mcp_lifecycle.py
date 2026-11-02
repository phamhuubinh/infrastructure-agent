"""Explicit reconnect preserves authority/schema snapshot and cannot replay mutations."""

import asyncio

import pytest
from test_mcp import FakeClient, config, manager_for

from orion.contracts import ModelToolCall, RuntimeScope
from orion.integrations.mcp import MCPConfig, MCPConfigurationError, MCPManager
from orion.tool_runtime.registry import ToolRegistry
from orion.tool_runtime.runner import ToolRunner

pytestmark = pytest.mark.anyio


async def test_explicit_disconnect_reconnect_keeps_frozen_registration_and_no_replay(store):
    fake = FakeClient(failure="transport")
    manager = manager_for(fake, config(tools={"read_item": {"operation_kind": "mutation"}}))
    registrations = await manager.start()
    registry = ToolRegistry(registrations)
    scope = RuntimeScope(
        session_id=store.create_session(), principal_id="local", workspace_id="local"
    )
    runner = ToolRunner(registry)
    call = ModelToolCall(
        call_id="write", tool_name="mcp.fixture.read_item", arguments={"value": "x"}
    )
    try:
        digest = manager.status()[0]["snapshot_sha256"]
        assert (await runner.run_async(call, scope)).error.code == "outcome_unknown"
        assert fake.calls == 1
        fake.failure = None
        await manager.connect("fixture")
        assert fake.enters == 2 and fake.exits == 1 and fake.calls == 1
        assert manager.status()[0]["snapshot_sha256"] == digest
        assert registry.definitions() == ToolRegistry(registrations).definitions()
        await manager.disconnect("fixture")
        assert (await runner.run_async(call, scope)).error.code == "unavailable"
        assert fake.calls == 1
        await manager.connect("fixture")
        assert fake.calls == 1
    finally:
        await manager.close()
    assert fake.enters == fake.exits == 3


@pytest.mark.parametrize("changed", ["input", "output", "description", "revision"])
async def test_changed_snapshot_refuses_reconnection_without_touching_registry(changed):
    fake = FakeClient()
    manager = manager_for(fake)
    registrations = await manager.start()
    definitions = ToolRegistry(registrations).definitions()
    try:
        await manager.disconnect("fixture")
        if changed == "revision":
            fake.protocol_version = "2026-07-28"
        else:
            key, value = {
                "input": ("input_schema", {"type": "object", "properties": {}}),
                "output": ("output_schema", {"type": "object"}),
                "description": ("description", "Changed external capability"),
            }[changed]
            fake.tools[0] = fake.tools[0].model_copy(update={key: value})
        with pytest.raises(MCPConfigurationError, match="snapshot_changed"):
            await manager.connect("fixture")
        assert fake.enters == fake.exits == 2
        assert manager.status()[0]["state"] == "failed"
        assert ToolRegistry(registrations).definitions() == definitions
    finally:
        await manager.close()


async def test_configuration_is_copied_and_unknown_protocol_rejected():
    original = MCPConfig.model_validate(config())
    fake = FakeClient()

    async def factory(*_):
        return fake

    manager = MCPManager(original, factory)
    original.servers[0].tools.clear()
    original.servers.clear()
    try:
        assert len(await manager.start()) == 1
    finally:
        await manager.close()
    fake.protocol_version = "2099-unknown"
    rejected = manager_for(fake)
    with pytest.raises(MCPConfigurationError, match="protocol_revision"):
        await rejected.start()
    assert fake.enters == fake.exits == 2
    await rejected.close()


async def test_administrative_disconnect_refuses_to_interrupt_dispatched_call(store):
    fake = FakeClient(failure="timeout")
    manager = manager_for(fake)
    registrations = await manager.start()
    scope = RuntimeScope(
        session_id=store.create_session(), principal_id="local", workspace_id="local"
    )
    task = asyncio.create_task(
        ToolRunner(ToolRegistry(registrations)).run_async(
            ModelToolCall(
                call_id="call", tool_name="mcp.fixture.read_item", arguments={"value": "x"}
            ),
            scope,
        )
    )
    try:
        while not fake.calls:
            await asyncio.sleep(0)
        for action in (manager.disconnect, manager.connect):
            with pytest.raises(MCPConfigurationError, match="busy"):
                await action("fixture")
        assert fake.calls == 1 and manager.status()[0]["inflight"] == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert manager.status()[0]["inflight"] == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await manager.close()
