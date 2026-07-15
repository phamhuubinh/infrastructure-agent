"""Hierarchical + Semantic chunking.

Two passes, matching the architecture's "Hierarchical + Semantic" chunking:

1. Hierarchical pass — walk the parsed document's headings to build a
   `heading_path` for every block (e.g. ["1. Introduction", "1.2 Scope"]).
   Tables/lists are kept as atomic blocks (never split mid-table).

2. Semantic pass — within each heading section, greedily pack paragraphs
   into a chunk up to `max_tokens`, but only merge a new paragraph into the
   running chunk if it is semantically close to it (cosine similarity of
   embeddings >= `similarity_threshold`); otherwise start a new chunk. This
   is the same idea as LlamaIndex's SemanticSplitter / RAGFlow's semantic
   chunking, implemented without an external chunking library.

Works fully offline with any `EmbeddingProvider` — including the
`HashEmbeddingProvider` fallback (app/embedding/hash_provider.py), so the
whole chunker is testable without a real model. Swap in a real embedding
provider (Qwen3 / BGE-M3 / OpenAI-compatible) for production-quality
semantic boundaries.
"""
from __future__ import annotations

import uuid

import numpy as np

from app.chunking.base import Chunk
from app.embedding.base import EmbeddingProvider
from app.parsers.base import ParsedDocument

_ATOMIC_TYPES = {"table"}


class HierarchicalSemanticChunker:
    def __init__(
        self,
        embedder: EmbeddingProvider | None = None,
        max_tokens: int = 400,
        min_tokens: int = 60,
        similarity_threshold: float = 0.55,
    ) -> None:
        self._embedder = embedder
        self._max_tokens = max_tokens
        self._min_tokens = min_tokens
        self._similarity_threshold = similarity_threshold

    def chunk(self, document: ParsedDocument, doc_id: str) -> list[Chunk]:
        sections = self._group_by_heading(document)

        chunks: list[Chunk] = []
        for heading_path, blocks in sections:
            chunks.extend(self._chunk_section(blocks, heading_path, doc_id))
        return chunks

    # -- Pass 1: hierarchical grouping -----------------------------------

    def _group_by_heading(self, document: ParsedDocument):
        stack: list[str] = []
        sections: list[tuple[list[str], list]] = []
        current_blocks: list = []

        def flush():
            if current_blocks:
                sections.append((list(stack), list(current_blocks)))

        for block in document.blocks:
            if block.block_type == "heading":
                flush()
                current_blocks.clear()
                level = max(block.level, 1)
                stack[:] = stack[: level - 1]
                stack.append(block.text.strip())
                continue
            current_blocks.append(block)

        flush()
        if not sections and document.blocks:
            sections = [([], list(document.blocks))]
        return sections

    # -- Pass 2: semantic packing within a section ------------------------

    def _chunk_section(self, blocks, heading_path: list[str], doc_id: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        buffer_texts: list[str] = []
        buffer_page: int | None = None

        def emit():
            if not buffer_texts:
                return
            text = "\n\n".join(buffer_texts)
            heading_prefix = " > ".join(heading_path)
            full_text = f"{heading_prefix}\n{text}" if heading_prefix else text
            chunks.append(
                Chunk(
                    text=full_text,
                    chunk_id=str(uuid.uuid4()),
                    doc_id=doc_id,
                    heading_path=list(heading_path),
                    page=buffer_page,
                )
            )

        prev_embedding: np.ndarray | None = None

        for block in blocks:
            if block.block_type in _ATOMIC_TYPES:
                emit()
                buffer_texts.clear()
                prev_embedding = None
                chunks.append(
                    Chunk(
                        text=block.text,
                        chunk_id=str(uuid.uuid4()),
                        doc_id=doc_id,
                        heading_path=list(heading_path),
                        page=block.page,
                        metadata={"block_type": "table"},
                    )
                )
                continue

            text = block.text.strip()
            if not text:
                continue

            buffer_page = buffer_page or block.page
            candidate_tokens = _estimate_tokens("\n\n".join(buffer_texts + [text]))

            should_split = False
            if buffer_texts and candidate_tokens > self._max_tokens:
                should_split = True
            elif buffer_texts and self._embedder is not None:
                current_tokens = _estimate_tokens("\n\n".join(buffer_texts))
                if current_tokens >= self._min_tokens:
                    sim = self._similarity(prev_embedding, text)
                    if sim is not None and sim < self._similarity_threshold:
                        should_split = True

            if should_split:
                emit()
                buffer_texts.clear()
                buffer_page = block.page

            buffer_texts.append(text)
            if self._embedder is not None:
                prev_embedding = self._embed_one(text)

        emit()
        return chunks

    def _embed_one(self, text: str) -> np.ndarray | None:
        try:
            vecs = self._embedder.embed([text])
            return np.asarray(vecs[0])
        except Exception:
            return None

    def _similarity(self, prev_embedding: np.ndarray | None, text: str) -> float | None:
        if prev_embedding is None:
            return None
        new_embedding = self._embed_one(text)
        if new_embedding is None:
            return None
        denom = (np.linalg.norm(prev_embedding) * np.linalg.norm(new_embedding)) or 1e-9
        return float(np.dot(prev_embedding, new_embedding) / denom)


def _estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) — swap for tiktoken if installed."""
    return max(1, len(text) // 4)
