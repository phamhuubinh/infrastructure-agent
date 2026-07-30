"""Ingest pipeline: file -> parse -> (OCR repair if needed) -> chunk ->
embed -> index (dense + sparse). This is the orchestrator; every stage is
a pluggable provider passed in via the constructor, so swapping e.g.
Qwen3Embedding for the hash fallback, or Qdrant for the in-memory store,
never touches this file.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.chunking.base import Chunker
from app.config import load_config
from app.embedding.base import EmbeddingProvider
from app.ocr.base import OcrProvider
from app.parsers.router import ParserRouter
from app.sparse.bm25_index import BM25Index
from app.vectordb.base import VectorRecord, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    doc_id: str
    chunk_count: int
    warnings: list[str]
    parser_used: str


class IngestPipeline:
    def __init__(
        self,
        parser_router: ParserRouter,
        chunker: Chunker,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        ocr_provider: OcrProvider | None = None,
        collection: str = "documents",
        data_dir: str | Path | None = None,
    ) -> None:
        self._parser_router = parser_router
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store
        self._bm25 = bm25_index
        self._ocr = ocr_provider
        self._collection = collection
        self._data_dir = Path(data_dir) if data_dir is not None else None

    def ingest(self, path: str | Path, doc_id: str) -> IngestResult:
        def validate_path_input(path: str) -> None:
            """Validate user-controlled path input to prevent path traversal attacks."""
            if not path:
                raise ValueError("Path cannot be empty")
            
            # Check for absolute paths
            if os.path.isabs(path):
                raise ValueError(f"Invalid path: {path}. Absolute paths are not allowed")
            
            # Check for path traversal attempts with '..'
            if ".." in path.split(os.sep):
                raise ValueError(f"Invalid path: {path}. Path traversal attempt detected")

        validate_path_input(str(path))
        path = Path(path)
        
        # Validate path against configured data directory to prevent path traversal
        # Only validate if data_dir is explicitly configured
        if self._data_dir is not None:
            data_directory = Path(self._data_dir)
            try:
                # Resolve both paths to handle symbolic links and normalize paths
                resolved_path = path.resolve()
                resolved_data_dir = data_directory.resolve()
                
                # Check if the resolved path is within the data directory
                resolved_path.relative_to(resolved_data_dir)
            except (ValueError, OSError):
                raise ValueError(f"Invalid path: {path}. Path must be within configured data directory: {data_directory}")
        
        document = self._parser_router.parse(path)
        warnings = list(document.warnings)

        if (
            self._needs_ocr(document)
            and self._ocr is not None
            and self._ocr.is_available()
        ):
            warnings.append(
                "Low/no extractable text detected — OCR repair is configured but "
                "per-page image extraction must be wired in for the specific parser "
                "in use (see app/ocr/README notes in this file's docstring)."
            )

        chunks = self._chunker.chunk(document, doc_id=doc_id)
        if not chunks:
            return IngestResult(
                doc_id=doc_id,
                chunk_count=0,
                warnings=warnings + ["No chunks produced."],
                parser_used=document.parser_name,
            )

        texts = [c.text for c in chunks]
        vectors = self._embedder.embed(texts)

        records = [
            VectorRecord(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "doc_id": chunk.doc_id,
                    "text": chunk.text,
                    "heading_path": chunk.heading_path,
                    "page": chunk.page,
                    **chunk.metadata,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]
        self._vector_store.upsert(self._collection, records)

        for chunk in chunks:
            self._bm25.add(chunk.chunk_id, chunk.text)

        return IngestResult(
            doc_id=doc_id,
            chunk_count=len(chunks),
            warnings=warnings,
            parser_used=document.parser_name,
        )

    @staticmethod
    def _needs_ocr(document) -> bool:
        total_chars = sum(len(b.text) for b in document.blocks)
        return total_chars < 20 and (document.page_count or 0) > 0
