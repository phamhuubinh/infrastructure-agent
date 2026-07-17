from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from src.backend.db import (
    delete_document as db_delete_document,
    get_document as db_get_document,
    insert_document as db_insert_document,
    list_documents as db_list_documents,
)

_STORAGE_DIR = Path.home() / ".orion" / "documents"


def _ensure_storage_dir() -> Path:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORAGE_DIR


def _safe_filename(filename: str) -> str:
    return Path(filename).name


def store_file(
    dsn: str | None,
    filename: str,
    content: bytes,
    content_type: str | None = None,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    safe_name = _safe_filename(filename)
    doc_id = uuid.uuid4().hex
    ct = (
        content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    )

    storage_dir = _ensure_storage_dir()
    ext = Path(safe_name).suffix
    storage_name = f"{doc_id}{ext}"
    storage_path = str(storage_dir / storage_name)
    (storage_dir / storage_name).write_bytes(content)

    size = len(content)

    if dsn:
        db_insert_document(
            dsn=dsn,
            doc_id=doc_id,
            filename=safe_name,
            content_type=ct,
            size_bytes=size,
            storage_path=storage_path,
            session_id=session_id,
            metadata=metadata,
        )

    return {
        "id": doc_id,
        "filename": safe_name,
        "content_type": ct,
        "size_bytes": size,
        "storage_path": storage_path,
        "session_id": session_id,
    }


def get_file(dsn: str | None, doc_id: str) -> dict | None:
    if dsn:
        doc = db_get_document(dsn, doc_id)
        if doc:
            return doc

    storage_dir = _ensure_storage_dir()
    for p in storage_dir.iterdir():
        if p.stem == doc_id:
            ct = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            return {
                "id": doc_id,
                "filename": p.name,
                "content_type": ct,
                "size_bytes": p.stat().st_size,
                "storage_path": str(p),
            }
    return None


def read_file_content(storage_path: str) -> bytes | None:
    p = Path(storage_path)
    if p.exists() and p.is_file():
        return p.read_bytes()
    return None


def list_files(
    dsn: str | None,
    session_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if dsn:
        return db_list_documents(dsn, session_id=session_id, limit=limit)

    storage_dir = _ensure_storage_dir()
    files = []
    for p in sorted(
        storage_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True
    ):
        if p.is_file():
            ct = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            files.append(
                {
                    "id": p.stem,
                    "filename": p.name,
                    "content_type": ct,
                    "size_bytes": p.stat().st_size,
                    "created_at": "",
                }
            )
    return files[:limit]


def delete_file(dsn: str | None, doc_id: str) -> bool:
    if dsn:
        doc = db_get_document(dsn, doc_id)
        if doc:
            storage_path = doc.get("storage_path", "")
            p = Path(storage_path)
            if p.exists():
                p.unlink()
            return db_delete_document(dsn, doc_id)

    storage_dir = _ensure_storage_dir()
    for p in storage_dir.iterdir():
        if p.stem == doc_id:
            p.unlink()
            return True
    return False
