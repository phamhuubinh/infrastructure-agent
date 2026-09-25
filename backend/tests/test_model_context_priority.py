from __future__ import annotations

from orion.chat.model_context import project_tool_result
from orion.contracts import SourceRef, ToolResult


def test_tight_project_search_projection_preserves_segment_text_and_source_identity() -> None:
    source = SourceRef(
        source_ref_id="026dcdc0-f387-5d2a-893e-2da53a61b163",
        source_kind="project",
        source_id="project-a",
        document_id="document-a",
        segment_id="segment-a",
        label="orion-qa-sentinel.txt",
    )
    result = ToolResult(
        call_id="search-a",
        tool_name="knowledge.search",
        status="success",
        data={
            "segments": [
                {
                    "document": {
                        "document_id": "document-a",
                        "source": {"kind": "project", "source_id": "project-a"},
                        "name": "orion-qa-sentinel.txt",
                        "media_type": "text/plain",
                    },
                    "segment_id": "segment-a",
                    "text": "Project fact: ORION_QA_PROJECT_A_7711",
                    "page": None,
                    "section": None,
                    "score": 0.03278688524590164,
                }
            ]
        },
        sources=(source,),
    )

    projection = project_tool_result(result, 1221, current_request=True)

    assert "ORION_QA_PROJECT_A_7711" in projection
    assert "026dcdc0-f387-5d2a-893e-2da53a61b163" in projection
