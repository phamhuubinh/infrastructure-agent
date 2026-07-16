"""Reranker interfaces. A reranker re-scores (query, document) pairs after
initial retrieval + fusion — much more accurate than embedding similarity
alone, but too expensive to run over the whole corpus, so it only sees the
fusion stage's top-N candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RerankedResult:
    id: str
    score: float
    text: str


class Reranker(Protocol):
    name: str

    def rerank(
        self, query: str, candidates: list[tuple[str, str]], top_k: int = 10
    ) -> list[RerankedResult]:
        """candidates: list of (id, text) pairs from the fusion stage."""
        ...
