"""Vector store interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict = field(default_factory=dict)


@dataclass
class ScoredRecord:
    id: str
    score: float
    payload: dict = field(default_factory=dict)


class VectorStore(Protocol):
    name: str

    def upsert(self, collection: str, records: list[VectorRecord]) -> None: ...

    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[ScoredRecord]: ...

    def delete(self, collection: str, ids: list[str]) -> None: ...
