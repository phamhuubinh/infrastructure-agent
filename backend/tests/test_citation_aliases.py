from __future__ import annotations

import json

from orion.chat.citation_aliases import (
    build_citation_aliases,
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
