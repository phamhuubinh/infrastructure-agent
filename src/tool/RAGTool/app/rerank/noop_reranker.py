"""Passthrough reranker — default until BGE-reranker-v2 is deployed.
Preserves the fusion-stage order (already scored), just adapts the shape."""

from __future__ import annotations

from app.rerank.base import RerankedResult


class NoOpReranker:
    name = "noop"

    def rerank(
        self, query: str, candidates: list[tuple[str, str]], top_k: int = 10
    ) -> list[RerankedResult]:
        return [
            RerankedResult(id=cid, score=1.0 - (i / max(len(candidates), 1)), text=text)
            for i, (cid, text) in enumerate(candidates[:top_k])
        ]
