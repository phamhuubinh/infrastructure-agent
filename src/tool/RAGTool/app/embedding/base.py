"""Embedding provider interface. All providers return list[list[float]],
same order as input texts, L2-normalized (callers may assume unit vectors
for cosine-via-dot-product)."""
from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        """Some models use a different prefix/instruction for queries vs
        documents (Qwen3-Embedding and BGE-M3 both do this) — default
        implementation just calls embed()."""
        return self.embed([text])[0]
