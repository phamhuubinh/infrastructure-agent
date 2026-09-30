"""Opt-in dense indexing/search services; production search does not use them yet."""

from __future__ import annotations

import math
from dataclasses import dataclass

from orion.contracts import RuntimeScope
from orion.embeddings import EmbeddingProfile, Vector, decode_vector, text_digest, validate_vector
from orion.knowledge.ports import EmbeddingPort
from orion.persistence.sqlite import SQLiteStore


@dataclass(frozen=True)
class SemanticHit:
    segment_id: str
    score: float


@dataclass(frozen=True)
class BackfillProgress:
    inspected: int
    reindexed: int
    failed: int
    wrapped: bool
    cursor_document_id: str | None


class SemanticIndexingError(RuntimeError):
    """A document-local embedding failure whose failed state was persisted."""


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
            try:
                windows = {
                    str(row["segment_id"]): self._embeddings.passage_windows(str(row["text"]))
                    for row in missing
                }
                if any(not window for window in windows.values()):
                    raise ValueError("Embedding adapter returned no passage windows")
            except (RuntimeError, ValueError) as error:
                raise SemanticIndexingError(str(error)) from error
            for start in range(0, len(missing), batch_size):
                batch = missing[start : start + batch_size]
                try:
                    passage_texts = tuple(
                        text for row in batch for text in windows[str(row["segment_id"])]
                    )
                    vectors: list[Vector] = []
                    for offset in range(0, len(passage_texts), batch_size):
                        texts = passage_texts[offset : offset + batch_size]
                        embedded = self._embeddings.embed_passages(texts)
                        if len(embedded) != len(texts):
                            raise ValueError("Embedding adapter returned the wrong passage count")
                        vectors.extend(embedded)
                    position = 0
                    validated_batches: list[tuple[str, str, tuple[Vector, ...]]] = []
                    for row in batch:
                        count = len(windows[str(row["segment_id"])])
                        validated = tuple(
                            validate_vector(vector, self._profile.dimension)
                            for vector in vectors[position : position + count]
                        )
                        position += count
                        validated_batches.append(
                            (str(row["segment_id"]), str(row["text"]), validated)
                        )
                except (RuntimeError, ValueError) as error:
                    raise SemanticIndexingError(str(error)) from error
                for segment_id, text, validated in validated_batches:
                    self._store.put_segment_embeddings(
                        segment_id,
                        self._profile,
                        text_digest(text),
                        validated,
                    )
                    completed += 1
                self._store.set_semantic_index_state(
                    document_id, self._profile.profile_id, "indexing", completed, total
                )
        except SemanticIndexingError as error:
            try:
                self._store.set_semantic_index_state(
                    document_id, self._profile.profile_id, "failed", completed, total, str(error)
                )
            except LookupError:
                # A concurrent tombstone remains authoritative.
                raise
            raise
        self._store.set_semantic_index_state(
            document_id, self._profile.profile_id, "ready", total, total
        )

    def reconcile_missing(
        self, *, batch_size: int = 16, max_documents: int = 100
    ) -> BackfillProgress:
        """Inspect one bounded profile cursor page and persist progress per document."""
        if max_documents <= 0:
            raise ValueError("Backfill document limit must be positive")
        if batch_size <= 0:
            raise ValueError("Embedding batch size must be positive")
        page, wrapped = self._store.semantic_backfill_page(self._profile.profile_id, max_documents)
        inspected = 0
        reindexed = 0
        failed = 0
        last_id: str | None = None
        for document in page:
            document_id = str(document["document_id"])
            inspected += 1
            try:
                missing = self._store.segments_needing_embeddings(document_id, self._profile)
                if missing:
                    self.index_document(document_id, batch_size=batch_size)
                    reindexed += 1
                else:
                    state = self._store.semantic_index_state(document_id, self._profile.profile_id)
                    if state["status"] != "ready":
                        total = len(self._store.document_segments(document_id))
                        self._store.set_semantic_index_state(
                            document_id, self._profile.profile_id, "ready", total, total
                        )
            except SemanticIndexingError:
                # The document's failed state is persisted; a later cursor pass retries it.
                failed += 1
            except LookupError:
                # A concurrent tombstone is final; an unexpected lookup failure is not.
                if self._store.document(document_id) is not None:
                    raise
            self._store.advance_semantic_backfill_cursor(
                self._profile.profile_id, str(document["created_at"]), document_id
            )
            last_id = document_id
        return BackfillProgress(inspected, reindexed, failed, wrapped, last_id)

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
