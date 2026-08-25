from __future__ import annotations

import pytest
from conftest import ScriptedBackend

from orion.access import LocalAccessAdapter
from orion.chat.runtime import ChatRuntime
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, RuntimeScope
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.service import KnowledgeService
from orion.knowledge.tools import knowledge_registrations
from orion.projects import ProjectService
from orion.tool_runtime.calculator import calculate, calculator_definition
from orion.tool_runtime.registry import ToolRegistryBuilder
from orion.tool_runtime.runner import ToolRunner


def _scope(session_id: str, project_id: str | None) -> RuntimeScope:
    return RuntimeScope(
        session_id=session_id,
        project_id=project_id,
        principal_id="local",
        workspace_id="local",
    )


def _registry(knowledge: KnowledgeService):  # type: ignore[no-untyped-def]
    builder = ToolRegistryBuilder()
    builder.register(calculator_definition(), calculate)
    for registration in knowledge_registrations(knowledge):
        builder.register(registration.definition, registration.handler)
    return builder.freeze()


@pytest.fixture
def project_knowledge(store, tmp_path):  # type: ignore[no-untyped-def]
    return ProjectService(store), KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))


def test_project_sessions_are_fixed_and_project_knowledge_is_isolated(
    store, project_knowledge
) -> None:  # type: ignore[no-untyped-def]
    projects, knowledge = project_knowledge
    project_a = projects.create("Project A", instructions="Keep answers concise.")
    project_b = projects.create("Project B")
    session_a = projects.create_session(project_a["project_id"], "local", "local")
    normal_session = store.create_session()
    document_a = knowledge.attach_project(
        project_a["project_id"], "a.txt", b"A-only retention: 30 days."
    )
    document_b = knowledge.attach_project(
        project_b["project_id"], "b.txt", b"B-only retention: 90 days."
    )
    runner = ToolRunner(_registry(knowledge))

    scope_a = _scope(session_a, project_a["project_id"])
    assert store.session_identity(session_a) is not None
    assert store.session_identity(session_a)["project_id"] == project_a["project_id"]
    assert knowledge.search(scope_a, "retention", 5)[0].document == document_a.document
    assert knowledge.search(_scope(normal_session, None), "retention", 5) == ()

    forged = runner.run(
        ModelToolCall(
            call_id="forged-b",
            tool_name="knowledge.read",
            arguments={"document_id": document_b.document.document_id},
        ),
        scope_a,
    )
    assert forged.status == "error"
    assert forged.error is not None and forged.error.code == "scope_violation"

    model_override = runner.run(
        ModelToolCall(
            call_id="override-project",
            tool_name="knowledge.search",
            arguments={"query": "retention", "project_id": project_b["project_id"]},
        ),
        scope_a,
    )
    assert model_override.status == "error"
    assert model_override.error is not None and model_override.error.code == "invalid_input"

    assert knowledge.delete(document_a.document.document_id, scope_a)
    assert knowledge.search(scope_a, "retention", 5) == ()
    assert knowledge.document_status(document_a.document.document_id, scope_a) is None


@pytest.mark.anyio
async def test_project_uses_the_same_chat_runtime_for_knowledge_then_calculator(
    store, project_knowledge
) -> None:  # type: ignore[no-untyped-def]
    projects, knowledge = project_knowledge
    project = projects.create(
        "Capacity", description="Sizing work", instructions="Use the project facts precisely."
    )
    session = projects.create_session(project["project_id"], "local", "local")
    document = knowledge.attach_project(
        project["project_id"], "requirements.txt", b"Each node needs 12 GB RAM."
    )
    source = knowledge.source_for_segment(
        knowledge.search(_scope(session, project["project_id"]), "node RAM", 1)[0]
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="project-search",
                        tool_name="knowledge.search",
                        arguments={"query": "node RAM"},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="capacity-calc",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "12 * 3"},
                    ),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(
                    content="Three nodes need 36 GB RAM.",
                    citation_source_ref_ids=(source.source_ref_id,),
                )
            ),
        ]
    )
    runtime = ChatRuntime(store, backend, _registry(knowledge), LocalAccessAdapter())

    outcome = await runtime.submit(session, "Size three nodes")

    assert outcome.assistant_content == "Three nodes need 36 GB RAM."
    assert len(backend.calls) == 3
    assert {tool.name for tool in backend.calls[0][1]} >= {
        "knowledge.search",
        "calculator.evaluate",
    }
    assert any("Active Project" in message.content for message in backend.calls[0][0])
    assert any("Capacity" in message.content for message in backend.calls[0][0])
    assert [item.tool_name for item in store.timeline(session) if item.kind == "tool_call"] == [
        "knowledge.search",
        "calculator.evaluate",
    ]
    assert document.document.source.kind == "project"
