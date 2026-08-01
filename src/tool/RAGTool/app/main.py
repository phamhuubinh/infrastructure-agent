"""FastAPI entry point for project-isolated document analysis."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile

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
from app.project_store import ProjectNotFoundError, ProjectStore
from app.schemas import (
    IngestResponse,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    QueryRequest,
    QueryResponse,
    RetrievedChunkResponse,
)
from app.sparse.bm25_index import BM25Index

app = FastAPI(title="Orion RAG Project Service", version="1.0.0")
logger = logging.getLogger(__name__)

_config = load_config()
_data_dir = Path(_config.data_dir)
_data_dir.mkdir(parents=True, exist_ok=True)
_embedder = build_embedder(_config)
_vector_store = build_vector_store(_config)
_reranker = build_reranker(_config)
_ocr = build_ocr_provider(_config)
_llm_client = build_llm_client(_config)
_parser_router = ParserRouter()
_chunker = HierarchicalSemanticChunker(embedder=_embedder)
_projects = ProjectStore(_data_dir)
_bm25_indexes: dict[str, BM25Index] = {}
_index_lock = threading.RLock()
_project_locks: dict[str, threading.RLock] = {}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _collection(project_id: str) -> str:
    return f"{_config.collection}_{project_id}"


def _bm25(project_id: str) -> BM25Index:
    with _index_lock:
        index = _bm25_indexes.get(project_id)
        if index is None:
            index = BM25Index(persist_path=_data_dir / "bm25" / f"{project_id}.json")
            _bm25_indexes[project_id] = index
        return index


def _project_lock(project_id: str) -> threading.RLock:
    with _index_lock:
        return _project_locks.setdefault(project_id, threading.RLock())


def _ingest_pipeline(project_id: str) -> IngestPipeline:
    return IngestPipeline(
        parser_router=_parser_router,
        chunker=_chunker,
        embedder=_embedder,
        vector_store=_vector_store,
        bm25_index=_bm25(project_id),
        ocr_provider=_ocr,
        collection=_collection(project_id),
        data_dir=_data_dir,
    )


def _query_pipeline(project_id: str, llm_client, final_top_k: int = 5) -> QueryPipeline:
    return QueryPipeline(
        embedder=_embedder,
        vector_store=_vector_store,
        bm25_index=_bm25(project_id),
        reranker=_reranker,
        llm_client=llm_client,
        collection=_collection(project_id),
        final_top_k=final_top_k,
    )


def _require_project(project_id: str) -> dict:
    try:
        return _projects.get(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(404, f"RAG project '{project_id}' not found") from exc


def _query_response(result) -> QueryResponse:
    return QueryResponse(
        answer=result.answer,
        retrieved=[
            RetrievedChunkResponse(
                id=chunk.id,
                text=chunk.text,
                score=chunk.score,
                payload=chunk.payload,
            )
            for chunk in result.retrieved
        ],
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "embedding_provider": _embedder.name,
        "vector_store": _vector_store.name,
        "reranker": _reranker.name,
        "llm_configured": _llm_client is not None,
        "project_count": len(_projects.list()),
    }


def _analysis_llm_client(body: QueryRequest):
    """Build a request-scoped client so concurrent projects cannot share state."""
    if body.analysis_model is None:
        return _llm_client
    from app.serving.llm_client import LlmClient

    return LlmClient(
        base_url=body.analysis_model.base_url,
        model=body.analysis_model.model,
        api_key=body.analysis_model.api_key,
        timeout=body.analysis_model.timeout,
    )


@app.post("/projects", response_model=ProjectResponse)
def create_project(body: ProjectCreateRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required")
    return _projects.create(name, body.description)


@app.get("/projects", response_model=ProjectListResponse)
def list_projects():
    return {"projects": _projects.list()}


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    return _require_project(project_id)


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    with _project_lock(project_id):
        _require_project(project_id)
        if project_id == "default":
            raise HTTPException(400, "The compatibility project cannot be deleted")
        project = _projects.get(project_id)
        chunk_ids = [
            chunk_id
            for document in project["documents"]
            for chunk_id in document.get("chunk_ids", [])
        ]
        if chunk_ids:
            _vector_store.delete(_collection(project_id), chunk_ids)
        if hasattr(_vector_store, "delete_collection"):
            _vector_store.delete_collection(_collection(project_id))
        _bm25(project_id).clear()
        with _index_lock:
            _bm25_indexes.pop(project_id, None)
        _projects.delete(project_id)
    with _index_lock:
        _project_locks.pop(project_id, None)
    return {"status": "deleted", "project_id": project_id}


@app.post(
    "/projects/{project_id}/documents",
    response_model=IngestResponse,
)
def upload_project_document(project_id: str, file: UploadFile):
    _require_project(project_id)
    filename = Path(file.filename or "upload").name
    if not filename:
        raise HTTPException(400, "filename is required")

    doc_id = uuid.uuid4().hex
    suffix = Path(filename).suffix.lower()
    with _project_lock(project_id):
        project_dir = _projects.project_documents_dir(project_id)
        stored_path = project_dir / f"{doc_id}{suffix}"
        indexed_chunk_ids: list[str] = []

        try:
            size_bytes = 0
            with stored_path.open("wb") as destination:
                while chunk := file.file.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > _MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            413, "Document exceeds the 50 MiB upload limit"
                        )
                    destination.write(chunk)

            result = _ingest_pipeline(project_id).ingest(
                stored_path,
                doc_id=doc_id,
                metadata={"project_id": project_id, "filename": filename},
            )
            indexed_chunk_ids = result.chunk_ids
            document = {
                "id": doc_id,
                "filename": filename,
                "content_type": file.content_type or "application/octet-stream",
                "size_bytes": size_bytes,
                "chunk_count": result.chunk_count,
                "chunk_ids": result.chunk_ids,
                "storage_path": str(stored_path),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            _projects.add_document(project_id, document)
        except HTTPException:
            stored_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            if indexed_chunk_ids:
                _vector_store.delete(_collection(project_id), indexed_chunk_ids)
                for chunk_id in indexed_chunk_ids:
                    _bm25(project_id).delete(chunk_id)
            stored_path.unlink(missing_ok=True)
            logger.exception("RAG document ingestion failed")
            raise HTTPException(422, f"Ingestion failed: {exc}") from exc

    return IngestResponse(
        project_id=project_id,
        doc_id=result.doc_id,
        chunk_count=result.chunk_count,
        parser_used=result.parser_used,
        warnings=result.warnings,
    )


@app.delete("/projects/{project_id}/documents/{doc_id}")
def delete_project_document(project_id: str, doc_id: str):
    with _project_lock(project_id):
        _require_project(project_id)
        document = _projects.get_document(project_id, doc_id)
        if document is None:
            raise HTTPException(404, f"Document '{doc_id}' not found")
        chunk_ids = document.get("chunk_ids", [])
        _vector_store.delete(_collection(project_id), chunk_ids)
        index = _bm25(project_id)
        for chunk_id in chunk_ids:
            index.delete(chunk_id)
        storage_path = Path(str(document.get("storage_path", "")))
        if storage_path.is_file():
            storage_path.unlink()
        _projects.remove_document(project_id, doc_id)
    return {"status": "deleted", "project_id": project_id, "doc_id": doc_id}


@app.post("/projects/{project_id}/analyses", response_model=QueryResponse)
def analyze_project(project_id: str, body: QueryRequest):
    with _project_lock(project_id):
        _require_project(project_id)
        query_text = body.query.strip()
        if not query_text:
            raise HTTPException(400, "query is required")
        project = _projects.get(project_id)
        if not project["documents"]:
            raise HTTPException(409, "Upload at least one document before analysis")

        llm_client = _analysis_llm_client(body)
        if llm_client is None:
            raise HTTPException(
                503,
                "No analysis model configured. Configure and test a model in Orion Settings.",
            )
        try:
            result = _query_pipeline(
                project_id, llm_client, final_top_k=body.top_k
            ).answer(query_text)
        except Exception as exc:
            logger.exception("RAG analysis model failed")
            raise HTTPException(502, f"Analysis model failed: {exc}") from exc
        response = _query_response(result)
        _projects.add_analysis(
            project_id,
            {
                "id": uuid.uuid4().hex,
                "query": query_text,
                "answer": response.answer,
                "retrieved": [item.model_dump() for item in response.retrieved],
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    return response


# Compatibility endpoints. They are isolated in the built-in `default` project
# and are not used by the Chat UI.
@app.post("/ingest", response_model=IngestResponse)
def ingest(file: UploadFile):
    return upload_project_document("default", file)


@app.post("/query", response_model=QueryResponse)
def query(body: QueryRequest):
    return analyze_project("default", body)
