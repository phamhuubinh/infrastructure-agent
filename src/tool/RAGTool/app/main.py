"""RAG microservice entry point.

    uvicorn app.main:app --host 0.0.0.0 --port 8080

Endpoints:
    GET  /health
    POST /ingest   (multipart file upload)
    POST /query

Provider selection is entirely env-var driven (see app/config.py) — no
code change needed to go from the offline-testable default stack
(hash embedding + in-memory store + no-op rerank) to production
(Qwen3/BGE-M3 + Qdrant + BGE-reranker-v2 + vLLM).
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.chunking.hierarchical_semantic_chunker import HierarchicalSemanticChunker
from app.config import (
    build_embedder,
    build_llm_client,
    build_ocr_provider,
    build_reranker,
    build_vector_store,
    load_config,
)
from app.parsers.router import ParserRouter
from app.pipeline.ingest_pipeline import IngestPipeline
from app.pipeline.query_pipeline import QueryPipeline
from app.schemas import IngestResponse, QueryRequest, QueryResponse, RetrievedChunkResponse
from app.sparse.bm25_index import BM25Index

app = FastAPI(title="RAG Service", version="0.1.0")

_config = load_config()
_embedder = build_embedder(_config)
_vector_store = build_vector_store(_config)
_bm25 = BM25Index()
_reranker = build_reranker(_config)
_ocr = build_ocr_provider(_config)
_llm_client = build_llm_client(_config)
_parser_router = ParserRouter()
_chunker = HierarchicalSemanticChunker(embedder=_embedder)

_ingest_pipeline = IngestPipeline(
    parser_router=_parser_router,
    chunker=_chunker,
    embedder=_embedder,
    vector_store=_vector_store,
    bm25_index=_bm25,
    ocr_provider=_ocr,
    collection=_config.collection,
)

_query_pipeline = QueryPipeline(
    embedder=_embedder,
    vector_store=_vector_store,
    bm25_index=_bm25,
    reranker=_reranker,
    llm_client=_llm_client,
    collection=_config.collection,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "embedding_provider": _embedder.name,
        "vector_store": _vector_store.name,
        "reranker": _reranker.name,
        "llm_configured": _llm_client is not None,
    }


@app.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile = File(...)):
    doc_id = str(uuid.uuid4())
    suffix = Path(file.filename or "upload").suffix

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = _ingest_pipeline.ingest(tmp_path, doc_id=doc_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return IngestResponse(
        doc_id=result.doc_id,
        chunk_count=result.chunk_count,
        parser_used=result.parser_used,
        warnings=result.warnings,
    )


@app.post("/query", response_model=QueryResponse)
def query(body: QueryRequest):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    result = _query_pipeline.answer(body.query)
    return QueryResponse(
        answer=result.answer,
        retrieved=[
            RetrievedChunkResponse(id=c.id, text=c.text, score=c.score, payload=c.payload)
            for c in result.retrieved[: body.top_k]
        ],
    )
