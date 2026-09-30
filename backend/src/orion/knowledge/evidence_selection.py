"""Pure, bounded evidence ordering experiment; not wired into production search."""

from collections.abc import Sequence

from orion.contracts import RetrievedSegment
from orion.knowledge.ranking import HYBRID_CANDIDATE_DEPTH


def select_document_balanced(
    candidates: Sequence[RetrievedSegment], limit: int
) -> tuple[RetrievedSegment, ...]:
    """Take each document's best hit once, then fill from the original ranking."""
    if limit <= 0:
        return ()
    bounded = candidates[:HYBRID_CANDIDATE_DEPTH]
    selected: list[RetrievedSegment] = []
    seen_documents: set[str] = set()
    seen_segments: set[str] = set()
    for hit in bounded:
        if hit.segment_id in seen_segments or hit.document.document_id in seen_documents:
            continue
        selected.append(hit)
        seen_segments.add(hit.segment_id)
        seen_documents.add(hit.document.document_id)
        if len(selected) == limit:
            return tuple(selected)
    for hit in bounded:
        if hit.segment_id in seen_segments:
            continue
        selected.append(hit)
        seen_segments.add(hit.segment_id)
        if len(selected) == limit:
            break
    return tuple(selected)
