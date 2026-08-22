from __future__ import annotations

import json
import mimetypes
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.backend.db import (
    delete_document as db_delete_document,
)
from src.backend.db import (
    get_document as db_get_document,
)
from src.backend.db import (
    insert_document as db_insert_document,
)
from src.backend.db import (
    list_documents as db_list_documents,
)

_STORAGE_DIR = Path.home() / ".orion" / "documents"
_LOCAL_INDEX_NAME = ".documents.json"
_PUBLIC_DOCUMENT_FIELDS = (
    "id",
    "filename",
    "content_type",
    "size_bytes",
    "session_id",
    "created_at",
)


def _ensure_storage_dir() -> Path:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORAGE_DIR


def _safe_filename(filename: str) -> str:
    return Path(filename).name


def public_file_metadata(document: dict) -> dict:
    """Return document metadata safe for API responses."""

    return {key: document[key] for key in _PUBLIC_DOCUMENT_FIELDS if key in document}


def _local_index_path() -> Path:
    return _ensure_storage_dir() / _LOCAL_INDEX_NAME


def _read_local_index() -> dict[str, dict]:
    try:
        data = json.loads(_local_index_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_local_index(records: dict[str, dict]) -> None:
    path = _local_index_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


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
    else:
        records = _read_local_index()
        records[doc_id] = {
            "id": doc_id,
            "filename": safe_name,
            "content_type": ct,
            "size_bytes": size,
            "storage_path": storage_path,
            "session_id": session_id,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_order": time.time_ns(),
        }
        _write_local_index(records)

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

    records = _read_local_index()
    record = records.get(doc_id)
    if isinstance(record, dict):
        return record
    storage_dir = _ensure_storage_dir()
    for p in storage_dir.iterdir():
        if p.name == _LOCAL_INDEX_NAME or p.name.endswith(".tmp"):
            continue
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

    records = _read_local_index()
    indexed = [
        dict(record)
        for record in records.values()
        if isinstance(record, dict)
        and (session_id is None or record.get("session_id") == session_id)
    ]
    indexed.sort(
        key=lambda item: (item.get("created_order", 0), item.get("id", "")),
        reverse=True,
    )
    if session_id is not None:
        return indexed[:limit]

    indexed_ids = {str(item.get("id")) for item in indexed}
    legacy = []
    storage_dir = _ensure_storage_dir()
    for path in storage_dir.iterdir():
        if (
            not path.is_file()
            or path.name == _LOCAL_INDEX_NAME
            or path.name.endswith(".tmp")
            or path.stem in indexed_ids
        ):
            continue
        legacy.append(
            {
                "id": path.stem,
                "filename": path.name,
                "content_type": mimetypes.guess_type(path.name)[0]
                or "application/octet-stream",
                "size_bytes": path.stat().st_size,
                "created_at": "",
                "created_order": path.stat().st_mtime_ns,
            }
        )
    return sorted(
        indexed + legacy,
        key=lambda item: (item.get("created_order", 0), item.get("id", "")),
        reverse=True,
    )[:limit]


def delete_file(dsn: str | None, doc_id: str) -> bool:
    if dsn:
        doc = db_get_document(dsn, doc_id)
        if doc:
            storage_path = doc.get("storage_path", "")
            p = Path(storage_path)
            if p.exists():
                p.unlink()
            return db_delete_document(dsn, doc_id)

    records = _read_local_index()
    record = records.pop(doc_id, None)
    if isinstance(record, dict):
        p = Path(str(record.get("storage_path", "")))
        if p.exists():
            p.unlink()
        _write_local_index(records)
        return True
    storage_dir = _ensure_storage_dir()
    for p in storage_dir.iterdir():
        if p.name == _LOCAL_INDEX_NAME or p.name.endswith(".tmp"):
            continue
        if p.stem == doc_id:
            p.unlink()
            return True
    return False
