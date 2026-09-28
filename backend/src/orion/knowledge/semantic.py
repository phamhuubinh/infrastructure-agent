"""Opt-in dense indexing/search services; production search does not use them yet."""

from __future__ import annotations

import math
from dataclasses import dataclass

from orion.contracts import RuntimeScope
from orion.embeddings import EmbeddingProfile, decode_vector, text_digest, validate_vector
from orion.knowledge.ports import EmbeddingPort
from orion.persistence.sqlite import SQLiteStore


@dataclass(frozen=True)
class SemanticHit:
    segment_id: str
    score: float


class SemanticIndexService:
    """Builds and reads one isolated embedding profile without changing KnowledgeService.search."""

    def __init__(self, store: SQLiteStore, embeddings: EmbeddingPort) -> None:
        if embeddings.dimension != embeddings.profile.dimension:
            raise ValueError("Embedding adapter dimension differs from its profile")
        if embeddings.maximum_input_tokens != embeddings.profile.maximum_input_tokens:
            raise ValueError("Embedding adapter token limit differs from its profile")
        self._store = store
        self._embeddings = embeddings
        self._profile = embeddings.profile
        self._store.register_embedding_profile(self._profile)

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    def index_document(self, document_id: str, *, batch_size: int = 16) -> None:
        if batch_size <= 0:
            raise ValueError("Embedding batch size must be positive")
        document = self._store.document(document_id)
        if document is None or document["status"] != "ready":
            raise LookupError("Document is not ready for semantic indexing")
        all_segments = self._store.document_segments(document_id)
        missing = self._store.segments_needing_embeddings(document_id, self._profile)
        total = len(all_segments)
        completed = total - len(missing)
        self._store.set_semantic_index_state(
            document_id, self._profile.profile_id, "indexing", completed, total
        )
        try:
            for start in range(0, len(missing), batch_size):
                batch = missing[start : start + batch_size]
                vectors = self._embeddings.embed_passages(tuple(str(row["text"]) for row in batch))
                if len(vectors) != len(batch):
                    raise ValueError("Embedding adapter returned the wrong passage count")
                for row, vector in zip(batch, vectors, strict=True):
                    validated = validate_vector(vector, self._profile.dimension)
                    self._store.put_segment_embeddings(
                        str(row["segment_id"]),
                        self._profile,
                        text_digest(str(row["text"])),
                        (validated,),
                    )
                    completed += 1
                self._store.set_semantic_index_state(
                    document_id, self._profile.profile_id, "indexing", completed, total
                )
        except Exception as error:
            try:
                self._store.set_semantic_index_state(
                    document_id, self._profile.profile_id, "failed", completed, total, str(error)
                )
            except LookupError:
                # A concurrent tombstone remains authoritative.
                pass
            raise
        self._store.set_semantic_index_state(
            document_id, self._profile.profile_id, "ready", total, total
        )

    def reconcile_missing(self, *, batch_size: int = 16) -> None:
        """Explicit resumable backfill; Phase 3 may schedule this in a bounded worker."""
        for document in self._store.ready_documents_for_semantic_backfill():
            document_id = str(document["document_id"])
            state = self._store.semantic_index_state(document_id, self._profile.profile_id)
            if state["status"] == "failed":
                continue
            if self._store.segments_needing_embeddings(document_id, self._profile):
                self.index_document(document_id, batch_size=batch_size)
            elif state["status"] != "ready":
                total = len(self._store.document_segments(document_id))
                self._store.set_semantic_index_state(
                    document_id, self._profile.profile_id, "ready", total, total
                )

    def search(
        self,
        scope: RuntimeScope,
        query: str,
        limit: int,
        document_ids: tuple[str, ...] = (),
    ) -> tuple[SemanticHit, ...]:
        if limit <= 0:
            raise ValueError("Semantic result limit must be positive")
        self._store.validate_visible_document_ids(scope, document_ids)
        vectors = self._embeddings.embed_queries((query,))
        if len(vectors) != 1:
            raise ValueError("Embedding adapter returned the wrong query count")
        query_vector = validate_vector(vectors[0], self._profile.dimension)
        query_norm = math.sqrt(sum(value * value for value in query_vector))
        if query_norm == 0:
            return ()
        best: dict[str, float] = {}
        offset = 0
        while True:
            rows = self._store.visible_embedding_rows(
                scope, self._profile, document_ids, limit=256, offset=offset
            )
            if not rows:
                break
            for row in rows:
                if row["dimension"] != self._profile.dimension or row[
                    "source_text_digest"
                ] != text_digest(str(row["text"])):
                    continue
                try:
                    passage = decode_vector(row["vector_blob"], self._profile.dimension)
                except ValueError:
                    continue
                norm = math.sqrt(sum(value * value for value in passage))
                if norm == 0:
                    continue
                score = sum(a * b for a, b in zip(query_vector, passage, strict=True)) / (
                    query_norm * norm
                )
                segment_id = str(row["segment_id"])
                best[segment_id] = max(score, best.get(segment_id, -math.inf))
            offset += len(rows)
        return tuple(
            SemanticHit(segment_id, score)
            for segment_id, score in sorted(best.items(), key=lambda item: (-item[1], item[0]))[
                :limit
            ]
        )
