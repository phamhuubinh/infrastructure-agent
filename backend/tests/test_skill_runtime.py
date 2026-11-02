"""Product skills use the existing canonical loop without persisting guidance payloads."""

import asyncio
import json

import pytest
from conftest import ScriptedBackend

from orion.access import LocalAccessAdapter
from orion.application.command_tools import command_registrations
from orion.application.commands import CommandService
from orion.chat.runtime import ChatRuntime, RequestCancelled, RequestFailed
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn
from orion.skills.service import SkillService
from orion.skills.tools import skill_registrations
from orion.tool_runtime.registry import ToolRegistry


@pytest.mark.anyio
async def test_model_load_and_read_are_current_request_only_with_first_turn_schemas(store):
    skills = SkillService(store)
    descriptor = skills.bundled["windows-linux-ops"].descriptor
    identity = {"name": descriptor.name, "package_sha256": descriptor.package_sha256}
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="load", tool_name="skill.load", arguments=identity),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="read",
                        tool_name="skill.read",
                        arguments={**identity, "path": "references/commands.md"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Scoped guidance loaded.")),
        ]
    )
    registry = ToolRegistry(skill_registrations(skills))
    skills.capabilities = frozenset(descriptor.required_capabilities)
    runtime = ChatRuntime(
        store,
        backend,
        registry,
        LocalAccessAdapter(),
        skill_request_start=skills.begin_request,
        skill_context=skills.context,
        skill_request_end=skills.end_request,
    )
    session = store.create_session()
    await runtime.submit(session, "Load applicable guidance")
    assert {tool.name for tool in backend.calls[0][1]} == {"skill.list", "skill.load", "skill.read"}
    assert "Selected skill guidance" not in "\n".join(
        message.content for message in backend.calls[0][0]
    )
    assert "Selected skill guidance windows-linux-ops" in "\n".join(
        message.content for message in backend.calls[1][0]
    )
    resource = skills.bundled[descriptor.name].resources["references/commands.md"].decode()
    assert any(
        message.role == "tool"
        and json.loads(message.content).get("data", {}).get("text") == resource
        for message in backend.calls[2][0]
    ), [(item.kind, item.payload) for item in store.timeline(session)]
    persisted = json.dumps([item.model_dump(mode="json") for item in store.timeline(session)])
    assert resource not in persisted and descriptor.package_sha256 not in persisted
    assert "payload_omitted" in persisted
    assert not skills.requests


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["project-research", "mcp-workflows", "windows-linux-ops"])
async def test_explicit_builtin_invocation_in_existing_runtime(store, name):
    skills = SkillService(store)
    skills.capabilities = frozenset(skills.bundled[name].descriptor.required_capabilities)
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Ready."))])
    runtime = ChatRuntime(
        store,
        backend,
        ToolRegistry(skill_registrations(skills)),
        LocalAccessAdapter(),
        skill_request_start=skills.begin_request,
        skill_context=skills.context,
        skill_request_end=skills.end_request,
    )
    await runtime.submit(store.create_session(), f"/skill {name}\nFollow my current scope")
    assert f"Selected skill guidance {name}" in "\n".join(
        message.content for message in backend.calls[0][0]
    )
    assert not skills.requests


@pytest.mark.anyio
async def test_loaded_operations_skill_cannot_authorize_a_read_only_command(store):
    from test_command_service import SHELL, TARGET, Transport

    skills = SkillService(store)
    transport = Transport(store)
    commands = CommandService(store, transport)
    registry = ToolRegistry((*skill_registrations(skills), *command_registrations(commands)))
    skills.capabilities = frozenset(definition.name for definition in registry.definitions())
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="script",
                        tool_name="system.command.run",
                        arguments={
                            "target_ref": TARGET,
                            "shell": SHELL,
                            "command": "echo forbidden",
                        },
                    ),
                )
            ),
            *[
                ModelTurn(assistant=AssistantMessage(content="Blocked by read-only policy."))
                for _ in range(4)
            ],
        ]
    )
    runtime = ChatRuntime(
        store,
        backend,
        registry,
        LocalAccessAdapter(),
        skill_request_start=skills.begin_request,
        skill_context=skills.context,
        skill_request_end=skills.end_request,
    )
    session = store.create_session()
    await runtime.submit(session, "/skill windows-linux-ops\nExecute the script resource")
    assert "Selected skill guidance windows-linux-ops" in backend.calls[0][0][0].content
    assert not transport.calls
    result = next(
        item.payload["result"] for item in store.timeline(session) if item.kind == "tool_result"
    )
    assert result["error"]["code"] == "operation_blocked"
    assert not skills.requests
    await commands.close()


@pytest.mark.anyio
@pytest.mark.parametrize("stop", [False, True])
async def test_failed_or_stopped_request_releases_selected_guidance(store, stop):
    entered = asyncio.Event()

    class InterruptedBackend(ScriptedBackend):
        async def stream(self, messages, tools, settings, cancellation):
            entered.set()
            if stop:
                await asyncio.Event().wait()
            raise RuntimeError("fixture model failure")
            yield  # Make this an async stream, matching the backend contract.

    skills = SkillService(store)
    backend = InterruptedBackend([])
    skills.capabilities = frozenset(
        skills.bundled["project-research"].descriptor.required_capabilities
    )
    runtime = ChatRuntime(
        store,
        backend,
        ToolRegistry(skill_registrations(skills)),
        LocalAccessAdapter(),
        skill_request_start=skills.begin_request,
        skill_context=skills.context,
        skill_request_end=skills.end_request,
    )
    session = store.create_session()
    request = runtime.begin(session, "/skill project-research\nUse scoped guidance")
    task = asyncio.create_task(runtime.run(session, request))
    await asyncio.wait_for(entered.wait(), 5)
    if stop:
        assert skills.requests
        runtime.cancel(request)
    with pytest.raises(RequestCancelled if stop else RequestFailed):
        await asyncio.wait_for(task, 5)
    assert not skills.requests
