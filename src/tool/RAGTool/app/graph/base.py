"""Graph-based retrieval interfaces (entity/relationship graph over the
corpus, queried alongside vector+sparse retrieval for multi-hop questions)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class GraphSearchResult:
    text: str
    source_ids: list[str]
    score: float = 1.0


class GraphIndex(Protocol):
    name: str

    def build(self, doc_id: str, text: str) -> None:
        """Extract entities/relationships from a document and add to the graph index."""
        ...

    def search(self, query: str, top_k: int = 10) -> list[GraphSearchResult]: ...
