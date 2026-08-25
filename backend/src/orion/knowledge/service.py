"""Session-scoped document lifecycle and source-aware local retrieval."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from orion.contracts import (
    DocumentRef,
    KnowledgeSourceRef,
    RetrievedSegment,
    RuntimeScope,
    SourceRef,
)
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.local import (
    HashingEmbedding,
    LocalLexicalIndex,
    LocalVectorIndex,
    ParagraphChunker,
    PlainTextParser,
)
from orion.knowledge.ports import Chunker, DocumentParser, IndexedSegment, LexicalIndex, VectorIndex
from orion.persistence.sqlite import SQLiteStore


@dataclass(frozen=True)
class DocumentUpload:
    document: DocumentRef
    attachment_id: str
    status: str
    error_message: str | None = None


class KnowledgeService:
    """Coordinates local blobs, lifecycle metadata, and replaceable retrieval ports."""

    def __init__(
        self,
        store: SQLiteStore,
        blobs: LocalBlobStore,
        parser: DocumentParser | None = None,
        chunker: Chunker | None = None,
        lexical_index: LexicalIndex | None = None,
        vector_index: VectorIndex | None = None,
    ) -> None:
        self._store = store
        self._blobs = blobs
        self._parser = parser or PlainTextParser()
        self._chunker = chunker or ParagraphChunker()
        self._lexical_index = lexical_index or LocalLexicalIndex()
        self._vector_index = vector_index or LocalVectorIndex(HashingEmbedding())

    def attach(
        self, session_id: str, name: str, content: bytes, media_type: str | None = "text/plain"
    ) -> DocumentUpload:
        if not self._store.session_exists(session_id):
            raise KeyError(session_id)
        document_id, attachment_id = str(uuid.uuid4()), str(uuid.uuid4())
        blob_id = self._blobs.put(content)
        self._store.create_document(
            document_id, attachment_id, session_id, blob_id, name, media_type
        )
        try:
            self._ingest(document_id)
        except (OSError, ValueError) as error:
            self._store.set_document_state(document_id, "failed", str(error))
        row = self._require_document(document_id)
        self._store.append_timeline(
            session_id,
            None,
            "attachment",
            {
                "document": self._document_ref(row).model_dump(mode="json"),
                "attachment_id": attachment_id,
                "status": row["status"],
            },
        )
        return DocumentUpload(
            document=self._document_ref(row),
            attachment_id=attachment_id,
            status=str(row["status"]),
            error_message=row["error_message"],
        )

    def document_status(self, document_id: str) -> dict[str, Any] | None:
        row = self._store.document(document_id, include_deleted=True)
        if row is None:
            return None
        return {
            "document": self._document_ref(row).model_dump(mode="json"),
            "attachment_id": row["attachment_id"],
            "status": row["status"],
            "error_message": row["error_message"],
            "deleted": row["deleted_at"] is not None,
            "ingestion": self._store.document_ingestion_events(document_id),
        }

    def delete(self, document_id: str, scope: RuntimeScope) -> bool:
        row = self._store.document(document_id)
        if row is None:
            return False
        if not self._is_visible(row, scope):
            raise PermissionError("Document is outside the current knowledge scope")
        return self._store.delete_document(document_id)

    def list_documents(self, scope: RuntimeScope) -> list[DocumentRef]:
        return [self._document_ref(row) for row in self._visible_documents(scope)]

    def search(
        self, scope: RuntimeScope, query: str, limit: int, document_ids: tuple[str, ...] = ()
    ) -> tuple[RetrievedSegment, ...]:
        documents = self._visible_documents(scope)
        visible_by_id = {str(document["document_id"]): document for document in documents}
        if document_ids:
            unauthorized = set(document_ids) - set(visible_by_id)
            if unauthorized:
                raise PermissionError("Requested document is outside the current knowledge scope")
            documents = [visible_by_id[document_id] for document_id in document_ids]
        segments = [
            segment
            for document in documents
            for segment in self._store.document_segments(str(document["document_id"]))
        ]
        indexed = tuple(
            IndexedSegment(segment_id=str(segment["segment_id"]), text=str(segment["text"]))
            for segment in segments
        )
        lexical = self._lexical_index.search(query, indexed)
        vector = self._vector_index.search(query, indexed)
        score_by_segment = self._fuse(lexical, vector)
        by_id = {str(segment["segment_id"]): segment for segment in segments}
        ranked_ids = sorted(
            score_by_segment,
            key=lambda segment_id: (-score_by_segment[segment_id], segment_id),
        )
        return tuple(
            self._retrieved_segment(by_id[segment_id], visible_by_id, score_by_segment[segment_id])
            for segment_id in ranked_ids[:limit]
        )

    def read(
        self, scope: RuntimeScope, document_id: str, section: str | None = None
    ) -> tuple[DocumentRef, tuple[RetrievedSegment, ...]]:
        row = self._store.document(document_id)
        if row is None:
            raise LookupError("Document was not found")
        if not self._is_visible(row, scope):
            raise PermissionError("Requested document is outside the current knowledge scope")
        segments = self._store.document_segments(document_id, section)
        if section is not None and not segments:
            raise LookupError("Section was not found")
        document = self._document_ref(row)
        by_id = {document_id: row}
        return document, tuple(
            self._retrieved_segment(segment, by_id, None) for segment in segments
        )

    def source_metadata(
        self, scope: RuntimeScope, document_id: str | None = None
    ) -> list[dict[str, Any]]:
        documents = self._visible_documents(scope)
        if document_id is not None:
            documents = [row for row in documents if row["document_id"] == document_id]
            if not documents:
                raise PermissionError("Requested document is outside the current knowledge scope")
        return [
            {
                "document": self._document_ref(row).model_dump(mode="json"),
                "attachment_id": row["attachment_id"],
                "status": row["status"],
                "sections": sorted(
                    {
                        segment["section"]
                        for segment in self._store.document_segments(row["document_id"])
                    }
                    - {None}
                ),
                "segment_count": len(self._store.document_segments(row["document_id"])),
            }
            for row in documents
        ]

    def source_for_segment(self, segment: RetrievedSegment) -> SourceRef:
        return SourceRef(
            source_ref_id=self._source_ref_id(segment.document.document_id, segment.segment_id),
            source_kind=segment.document.source.kind,
            source_id=segment.document.source.source_id,
            document_id=segment.document.document_id,
            segment_id=segment.segment_id,
            page=segment.page,
            section=segment.section,
            label=segment.document.name,
        )

    def _ingest(self, document_id: str) -> None:
        row = self._require_document(document_id)
        self._store.set_document_state(document_id, "parsing")
        parsed = self._parser.parse(self._blobs.get(str(row["blob_id"])), row["media_type"])
        self._store.set_document_state(document_id, "indexing")
        chunks = self._chunker.chunk(parsed)
        if not chunks:
            raise ValueError("Document has no indexable text")
        self._store.store_parsed_document(
            document_id,
            parsed.text,
            [
                {
                    "segment_id": self._segment_id(document_id, chunk.ordinal),
                    "ordinal": chunk.ordinal,
                    "text": chunk.text,
                    "page": chunk.page,
                    "section": chunk.section,
                }
                for chunk in chunks
            ],
        )
        self._store.set_document_state(document_id, "ready")

    def _visible_documents(self, scope: RuntimeScope) -> list[dict[str, Any]]:
        # M2 deliberately exposes only the current session's application-owned attachments.
        return self._store.visible_documents(scope.session_id, scope.attachment_ids)

    @staticmethod
    def _is_visible(row: dict[str, Any], scope: RuntimeScope) -> bool:
        return (
            row["session_id"] == scope.session_id and row["attachment_id"] in scope.attachment_ids
        )

    @staticmethod
    def _segment_id(document_id: str, ordinal: int) -> str:
        value = f"orion:document:{document_id}:segment:{ordinal}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))

    @staticmethod
    def _source_ref_id(document_id: str, segment_id: str) -> str:
        return f"source:{document_id}:{segment_id}"

    def _document_ref(self, row: dict[str, Any]) -> DocumentRef:
        return DocumentRef(
            document_id=str(row["document_id"]),
            source=KnowledgeSourceRef(kind="session", source_id=str(row["session_id"])),
            name=str(row["name"]),
            media_type=row["media_type"],
        )

    def _retrieved_segment(
        self,
        row: dict[str, Any],
        documents_by_id: dict[str, dict[str, Any]],
        score: float | None,
    ) -> RetrievedSegment:
        document_id = str(row["document_id"])
        return RetrievedSegment(
            document=self._document_ref(documents_by_id[document_id]),
            segment_id=str(row["segment_id"]),
            text=str(row["text"]),
            page=row["page"],
            section=row["section"],
            score=score,
        )

    @staticmethod
    def _fuse(lexical: dict[str, float], vector: dict[str, float]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for result_set in (lexical, vector):
            ranked = sorted(
                result_set,
                key=lambda segment_id: (-result_set[segment_id], segment_id),
            )
            for rank, segment_id in enumerate(ranked, start=1):
                scores[segment_id] = scores.get(segment_id, 0.0) + 1.0 / (60 + rank)
        return scores

    def _require_document(self, document_id: str) -> dict[str, Any]:
        row = self._store.document(document_id, include_deleted=True)
        if row is None:
            raise LookupError(document_id)
        return row
