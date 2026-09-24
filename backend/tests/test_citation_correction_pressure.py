from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from conftest import ScriptedBackend

from orion.access import LocalAccessAdapter
from orion.chat.runtime import ChatRuntime, RequestFailed
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    SourceRef,
    ToolDefinition,
    ToolResult,
)
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.tool_runtime.registry import ToolRegistryBuilder


def _internet_search_result() -> ToolResult:
    sources = tuple(
        SourceRef(
            source_ref_id=f"0dc70037-9511-5d15-a9e5-{index:012d}",
            source_kind="internet",
            source_id=f"https://example.test/python-{index}/",
            label=f"Python release result {index}",
            url=f"https://example.test/python-{index}/",
            retrieved_at=datetime(2026, 9, 24, tzinfo=UTC),
        )
        for index in range(8)
    )
    return ToolResult(
        call_id="search",
        tool_name="internet.search",
        status="success",
        data={
            "results": [
                {
                    "source_ref_id": source.source_ref_id,
                    "url": source.url,
                    "title": source.label,
                    "snippet": "Python release evidence " + str(index) + ": " + "x" * 1_000,
                    "retrieved_at": source.retrieved_at.isoformat(),
                }
                for index, source in enumerate(sources)
            ]
        },
        sources=sources,
    )


def _search_registry(result: ToolResult):  # type: ignore[no-untyped-def]
    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="internet.search",
            handler_key="internet.search",
            description="Search current Internet information.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        lambda call: result.model_copy(update={"call_id": call.call_id}),
    )
    return builder.freeze()


@pytest.mark.anyio
async def test_eight_source_internet_citation_correction_retains_surviving_evidence(
    store,
) -> None:  # type: ignore[no-untyped-def]
    result = _internet_search_result()
    repaired = OpenAICompatibleBackend._build_turn(
        ["Python release evidence. [[source:S1]]"],
        {},
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="search",
                        tool_name="internet.search",
                        arguments={"query": "current Python release", "limit": 8},
                    ),
                )
            ),
            ModelTurn(
                assistant=AssistantMessage(content="Python release evidence without a citation.")
            ),
            repaired,
        ]
    )
    chat = ChatRuntime(
        store,
        backend,
        _search_registry(result),
        LocalAccessAdapter(),
    )
    session = store.create_session()

    outcome = await chat.submit(
        session,
        "Search the web for the current Python release and cite the source.",
    )

    assert outcome.status == "completed"
    assert outcome.assistant_content == (
        f"Python release evidence. [[source:{result.sources[0].source_ref_id}]]"
    )
    assert len(backend.calls) == 3

    correction_messages, _ = backend.calls[-1]
    correction = correction_messages[-1]
    assert correction.role == "user"
    assert "Allowed evidence_ref aliases" not in correction.content
    assert "without a citation" not in "\n".join(message.content for message in correction_messages)

    tool_message = next(message for message in correction_messages if message.role == "tool")
    projected = json.loads(tool_message.content)
    rows = projected["data"]["results"]

    assert rows
    assert rows[0]["evidence_ref"] == "S1"
    assert "source_ref_id" not in tool_message.content

    row_aliases = {
        row["evidence_ref"]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("evidence_ref"), str)
    }
    source_aliases = {
        source["evidence_ref"]
        for source in projected["sources"]
        if isinstance(source, dict) and isinstance(source.get("evidence_ref"), str)
    }
    assert source_aliases == row_aliases
    assert set(projected["_orion_provenance"]["evidence_refs"]) == row_aliases


@pytest.mark.anyio
async def test_citation_obligation_does_not_disappear_when_correction_loses_sources(
    store, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    source = SourceRef(
        source_ref_id="sticky-source",
        source_kind="grafana",
        source_id="grafana",
    )
    result = ToolResult(
        call_id="read",
        tool_name="fake.read",
        status="success",
        data={"value": "observed"},
        sources=(source,),
    )
    builder = ToolRegistryBuilder()
    builder.register(
        ToolDefinition(
            name="fake.read",
            handler_key="fake.read",
            description="Read one sourced value.",
            input_schema={"type": "object", "properties": {}},
        ),
        lambda call: result.model_copy(update={"call_id": call.call_id}),
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="read",
                        tool_name="fake.read",
                        arguments={},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Observed value.")),
            ModelTurn(assistant=AssistantMessage(content="Still uncited.")),
        ]
    )
    chat = ChatRuntime(
        store,
        backend,
        builder.freeze(),
        LocalAccessAdapter(),
    )

    original_build = chat._context_builder.build_with_metadata
    build_count = 0

    def build_with_lost_correction_sources(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal build_count
        build_count += 1
        built = original_build(*args, **kwargs)
        if build_count == 3:
            return replace(
                built,
                visible_sources=(),
                current_visible_sources=(),
                historical_visible_sources=(),
            )
        return built

    monkeypatch.setattr(
        chat._context_builder,
        "build_with_metadata",
        build_with_lost_correction_sources,
    )
    session = store.create_session()

    with pytest.raises(RequestFailed, match="required source citation"):
        await chat.submit(session, "Read the value and cite the source.")

    assert len(backend.calls) == 3
    timeline = store.timeline(session)
    notice = next(item.payload for item in timeline if item.kind == "runtime_notice")
    assert notice["error_kind"] == "missing_citation"
    assert notice["citation_correction_attempted"] is True
    assert notice["visible_source_ref_ids"] == []
    assert not [
        item
        for item in timeline
        if item.kind == "assistant_message" and item.payload.get("content") == "Still uncited."
    ]
