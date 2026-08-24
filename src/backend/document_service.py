from __future__ import annotations

import json
import mimetypes
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

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


class DocumentPersistenceError(RuntimeError):
    """Document metadata cannot be safely read or mutated."""


def _ensure_storage_dir() -> Path:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORAGE_DIR


def _safe_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise ValueError("filename must be text")
    name = Path(filename).name.strip()
    if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("filename contains unsafe control characters")
    return name


def content_disposition_attachment(filename: str) -> str:
    """Build a CR/LF-safe RFC 5987 attachment header from stored metadata."""
    name = _safe_filename(filename)
    fallback = (
        "".join(
            char if 32 <= ord(char) < 127 and char not in {'"', "\\"} else "_"
            for char in name
        ).strip()
        or "download"
    )
    return (
        f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"
    )


def public_file_metadata(document: dict) -> dict:
    """Return document metadata safe for API responses."""

    return {key: document[key] for key in _PUBLIC_DOCUMENT_FIELDS if key in document}


def _local_index_path() -> Path:
    return _ensure_storage_dir() / _LOCAL_INDEX_NAME


def _read_local_index() -> dict[str, dict]:
    try:
        data = json.loads(_local_index_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentPersistenceError(
            "Document metadata is unreadable; refusing mutation to preserve recovery data."
        ) from exc
    if not isinstance(data, dict):
        raise DocumentPersistenceError(
            "Document metadata is malformed; refusing mutation to preserve recovery data."
        )
    return data


def _write_local_index(records: dict[str, dict]) -> None:
    path = _local_index_path()
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise DocumentPersistenceError("Could not persist document metadata.") from exc


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
    final_path = storage_dir / storage_name
    staging_path = storage_dir / f".{storage_name}.{uuid.uuid4().hex}.pending"
    staging_path.write_bytes(content)
    storage_path = str(final_path)

    size = len(content)

    if dsn:
        try:
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
            staging_path.replace(final_path)
        except Exception:
            staging_path.unlink(missing_ok=True)
            # If metadata was committed but the final promote failed, remove
            # the record so callers never receive a completed-looking upload.
            try:
                db_delete_document(dsn, doc_id)
            except Exception:
                pass
            raise
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
        try:
            _write_local_index(records)
            staging_path.replace(final_path)
        except Exception:
            staging_path.unlink(missing_ok=True)
            try:
                records.pop(doc_id, None)
                _write_local_index(records)
            except Exception:
                # A failed rollback remains recoverable: the staged payload
                # has been removed and the metadata failure is surfaced.
                pass
            raise

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
            if not db_delete_document(dsn, doc_id):
                return False
            try:
                Path(storage_path).unlink(missing_ok=True)
            except OSError:
                # The metadata deletion is durable; leave the orphan for
                # retryable garbage collection rather than claiming a failed
                # delete and inviting a duplicate metadata mutation.
                pass
            return True

    records = _read_local_index()
    record = records.pop(doc_id, None)
    if isinstance(record, dict):
        p = Path(str(record.get("storage_path", "")))
        _write_local_index(records)
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
        return True
    storage_dir = _ensure_storage_dir()
    for p in storage_dir.iterdir():
        if p.name == _LOCAL_INDEX_NAME or p.name.endswith(".tmp"):
            continue
        if p.stem == doc_id:
            p.unlink()
            return True
    return False
