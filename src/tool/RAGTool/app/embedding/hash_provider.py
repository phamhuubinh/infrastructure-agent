"""Deterministic hash-based embedding — offline dev/test fallback only.

NOT semantically meaningful (it's a bag-of-character-ngrams hashed into a
fixed-size vector, not a trained model) — do not use in production. Its
only job is to let the rest of the pipeline (chunker, vector store, BM25
fusion, reranker interfaces) be built and unit-tested end-to-end without
any network access or GPU, in this sandbox and in CI. Swap for
Qwen3EmbeddingProvider / BgeM3EmbeddingProvider / an OpenAI-compatible
provider hitting vLLM before going to production.
"""

from __future__ import annotations

import hashlib

import numpy as np


class HashEmbeddingProvider:
    name = "hash-fallback (NOT for production — no semantic meaning)"

    def __init__(self, dimension: int = 384, ngram: int = 3) -> None:
        self.dimension = dimension
        self._ngram = ngram

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        vec = np.zeros(self.dimension, dtype=np.float64)
        normalized = text.lower().strip()
        if not normalized:
            return vec.tolist()

        for i in range(len(normalized) - self._ngram + 1):
            gram = normalized[i : i + self._ngram]
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()
