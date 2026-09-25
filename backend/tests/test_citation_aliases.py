from __future__ import annotations

import json

from orion.chat.citation_aliases import (
    build_citation_aliases,
    citation_eligible_sources,
    model_visible_citation_messages,
)
from orion.chat.model_context import project_tool_result
from orion.contracts import ContextMessage, SourceRef, ToolResult


def _project(result: ToolResult) -> dict[str, object]:
    aliases = build_citation_aliases(result.sources)
    message = ContextMessage(
        role="tool",
        content=project_tool_result(result, 20_000, current_request=True),
        tool_call_id=result.call_id,
    )
    projected = model_visible_citation_messages((message,), aliases)[0]
    return json.loads(projected.content)


def test_model_projection_preserves_arbitrary_evidence_source_fields_and_uuid_text() -> None:
    canonical = "5b30120f-f311-5b1f-a6a4-7076537e9e65"
    source = SourceRef(
        source_ref_id=canonical,
        source_kind="grafana",
        source_id="grafana",
        label="Grafana",
    )
    result = ToolResult(
        call_id="generic",
        tool_name="custom.read",
        status="success",
        data={
            "source_ref_id": "external-record-123",
            "source_refs": ["ticket-a", "ticket-b"],
            "literal": canonical,
        },
        sources=(source,),
    )

    projected = _project(result)

    assert projected["data"] == result.data
    assert projected["sources"][0]["evidence_ref"] == "S1"
    assert "source_ref_id" not in projected["sources"][0]
    assert projected["_orion_provenance"]["evidence_refs"] == ["S1"]
    assert "source_refs" not in projected["_orion_provenance"]


def test_model_projection_rewrites_only_internet_owned_data_source_ref() -> None:
    canonical = "internet-canonical-source"
    source = SourceRef(
        source_ref_id=canonical,
        source_kind="internet",
        source_id="https://example.test/",
        url="https://example.test/",
    )
    result = ToolResult(
        call_id="fetch",
        tool_name="internet.fetch",
        status="success",
        data={
            "source_ref_id": canonical,
            "url": "https://example.test/",
            "title": "Example",
            "text": "Evidence text.",
        },
        sources=(source,),
    )

    projected = _project(result)

    assert projected["data"]["evidence_ref"] == "S1"
    assert "source_ref_id" not in projected["data"]
    assert projected["sources"][0]["evidence_ref"] == "S1"


def test_discovery_only_internet_search_has_no_citation_aliases() -> None:
    payload = {
        "call_id": "search",
        "tool_name": "internet.search",
        "status": "success",
        "data": {
            "results": [
                {
                    "url": "https://example.test/latest",
                    "title": "Latest release",
                    "retrieved_at": "2026-08-25T00:00:00+00:00",
                }
            ]
        },
        "sources": [],
    }
    message = ContextMessage(
        role="tool",
        tool_call_id="search",
        tool_name="internet.search",
        content=json.dumps(payload),
    )

    eligible = citation_eligible_sources((message,), ())
    assert eligible == ()
    assert build_citation_aliases(eligible) == ()


def test_internet_search_only_retained_rows_are_citation_eligible() -> None:
    first = SourceRef(
        source_ref_id="internet-source-a",
        source_kind="internet",
        source_id="https://example.test/a",
        url="https://example.test/a",
        label="A",
    )
    second = SourceRef(
        source_ref_id="internet-source-b",
        source_kind="internet",
        source_id="https://example.test/b",
        url="https://example.test/b",
        label="B",
    )
    payload = {
        "call_id": "search",
        "tool_name": "internet.search",
        "status": "success",
        "error": None,
        "data": {
            "results": [
                {
                    "source_ref_id": first.source_ref_id,
                    "url": first.url,
                    "title": first.label,
                    "snippet": "retained evidence",
                }
            ]
        },
        "sources": [
            first.model_dump(mode="json"),
            second.model_dump(mode="json"),
        ],
        "_orion_provenance": {
            "trust": "untrusted_external_content",
            "tool_name": "internet.search",
            "current_request": True,
            "source_refs": [first.source_ref_id, second.source_ref_id],
        },
    }
    message = ContextMessage(
        role="tool",
        tool_call_id="search",
        tool_name="internet.search",
        content=json.dumps(payload),
    )

    eligible = citation_eligible_sources((message,), (first, second))
    aliases = build_citation_aliases(eligible)
    projected = json.loads(model_visible_citation_messages((message,), aliases)[0].content)

    assert eligible == (first,)
    assert projected["data"]["results"][0]["evidence_ref"] == "S1"
    assert len(projected["sources"]) == 1
    assert projected["sources"][0]["evidence_ref"] == "S1"
    assert "source_ref_id" not in projected["sources"][0]
    assert projected["_orion_provenance"]["evidence_refs"] == ["S1"]
