from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from src.backend.document_service import (
    delete_file as doc_delete_file,
)
from src.backend.document_service import (
    get_file as doc_get_file,
)
from src.backend.document_service import (
    list_files as doc_list_files,
)
from src.backend.document_service import (
    read_file_content as doc_read_file_content,
)
from src.backend.document_service import (
    store_file as doc_store_file,
)

router = APIRouter(tags=["documents"])


@router.post("/api/documents/upload")
def document_upload(body: dict, request: Request):
    deps = request.app.state.deps
    content = (body.get("content") or "").encode("utf-8")
    filename = (body.get("filename") or "untitled.txt").strip()
    content_type = body.get("content_type")
    session_id = body.get("session_id")
    metadata = body.get("metadata")

    result = doc_store_file(
        dsn=deps.dsn,
        filename=filename,
        content=content,
        content_type=content_type,
        session_id=session_id,
        metadata=metadata,
    )
    return result


@router.get("/api/documents")
def document_list(request: Request, session_id: str | None = None, limit: int = 50):
    deps = request.app.state.deps
    return {
        "documents": doc_list_files(dsn=deps.dsn, session_id=session_id, limit=limit)
    }


@router.get("/api/documents/{doc_id}")
def document_get(doc_id: str, request: Request):
    deps = request.app.state.deps
    doc = doc_get_file(dsn=deps.dsn, doc_id=doc_id)
    if doc is None:
        raise HTTPException(404, f"Document '{doc_id}' not found")
    return doc


@router.get("/api/documents/{doc_id}/download")
def document_download(doc_id: str, request: Request):
    deps = request.app.state.deps
    doc = doc_get_file(dsn=deps.dsn, doc_id=doc_id)
    if doc is None:
        raise HTTPException(404, f"Document '{doc_id}' not found")
    content = doc_read_file_content(doc["storage_path"])
    if content is None:
        raise HTTPException(404, "File content not found on disk")
    return Response(
        content=content,
        media_type=doc.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'},
    )


@router.delete("/api/documents/{doc_id}")
def document_delete(doc_id: str, request: Request):
    deps = request.app.state.deps
    deleted = doc_delete_file(dsn=deps.dsn, doc_id=doc_id)
    if not deleted:
        raise HTTPException(404, f"Document '{doc_id}' not found")
    return {"status": "deleted", "doc_id": doc_id}
