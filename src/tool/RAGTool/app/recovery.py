"""Persistent recovery for Project RAG cross-store mutations."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.project_store import ProjectNotFoundError, ProjectStore
from app.sparse.bm25_index import BM25Index
from app.vectordb.base import VectorStore


class RecoveryPendingError(RuntimeError):
    """A persistent tombstone remains and must be retried before use."""


class ProjectRecovery:
    """Reconcile durable operation records with files and retrieval indexes.

    Each operation writes its journal record before a backing-store mutation.
    Deletes tombstone metadata first; uploads remain invisible until metadata
    commits. Recovery is idempotent and safe to run after a process restart.
    """

    def __init__(
        self,
        *,
        projects: ProjectStore,
        vector_store: VectorStore,
        bm25_for_project: Callable[[str], BM25Index],
        collection_for_project: Callable[[str], str],
    ) -> None:
        self._projects = projects
        self._vectors = vector_store
        self._bm25_for_project = bm25_for_project
        self._collection_for_project = collection_for_project

    def recover(self, project_id: str | None = None) -> None:
        failures: list[str] = []
        for record in self._projects.recovery_records(project_id):
            try:
                self._recover_record(record)
            except Exception as exc:
                self._projects.update_recovery(
                    str(record["id"]), last_error=type(exc).__name__
                )
                failures.append(str(record["id"]))
        if failures:
            raise RecoveryPendingError(
                "RAG recovery is pending for operation(s): " + ", ".join(failures)
            )

    def _recover_record(self, record: dict[str, Any]) -> None:
        operation = record.get("operation")
        if operation == "upload":
            self._recover_upload(record)
        elif operation == "document_delete":
            self._recover_document_delete(record)
        elif operation == "project_delete":
            self._recover_project_delete(record)
        else:
            raise ValueError("Unknown persistent RAG recovery operation.")

    def _recover_upload(self, record: dict[str, Any]) -> None:
        project_id = _text(record, "project_id")
        doc_id = _text(record, "doc_id")
        # A committed document wins over an uncleared journal record: this is
        # the crash window after atomic metadata commit and before resolution.
        try:
            document = self._projects.get_document(
                project_id, doc_id, include_recovering=True
            )
        except ProjectNotFoundError:
            document = None
        if document is not None and document.get("state", "active") == "active":
            self._projects.resolve_recovery(_text(record, "id"))
            return

        self._vectors.delete(
            self._collection_for_project(project_id), _strings(record.get("chunk_ids"))
        )
        index = self._bm25_for_project(project_id)
        for chunk_id in _strings(record.get("chunk_ids")):
            index.delete(chunk_id)
        _unlink(record.get("staging_path"))
        _unlink(record.get("final_path"))
        self._projects.resolve_recovery(_text(record, "id"))

    def _recover_document_delete(self, record: dict[str, Any]) -> None:
        project_id = _text(record, "project_id")
        doc_id = _text(record, "doc_id")
        if record.get("phase") == "prepared":
            document = self._projects.get_document(
                project_id, doc_id, include_recovering=True
            )
            if document is not None and document.get("state", "active") == "active":
                # The journal was durable but the tombstone was not yet
                # committed when the process stopped; no delete began.
                self._projects.resolve_recovery(_text(record, "id"))
                return
        chunk_ids = _strings(record.get("chunk_ids"))
        self._vectors.delete(self._collection_for_project(project_id), chunk_ids)
        index = self._bm25_for_project(project_id)
        for chunk_id in chunk_ids:
            index.delete(chunk_id)
        _unlink(record.get("storage_path"))
        try:
            self._projects.remove_document(project_id, doc_id)
        except ProjectNotFoundError:
            pass
        self._projects.resolve_recovery(_text(record, "id"))

    def _recover_project_delete(self, record: dict[str, Any]) -> None:
        project_id = _text(record, "project_id")
        if record.get("phase") == "prepared":
            try:
                project = self._projects.get(project_id, include_recovering=True)
            except ProjectNotFoundError:
                project = None
            if project is not None and project.get("state", "active") == "active":
                self._projects.resolve_recovery(_text(record, "id"))
                return
        collection = self._collection_for_project(project_id)
        delete_collection = getattr(self._vectors, "delete_collection", None)
        if callable(delete_collection):
            delete_collection(collection)
        else:
            self._vectors.delete(collection, _strings(record.get("chunk_ids")))
        index = self._bm25_for_project(project_id)
        index.clear()
        index.remove_persistence()
        documents_dir = record.get("documents_dir")
        if isinstance(documents_dir, str) and documents_dir:
            path = Path(documents_dir)
            if path.exists():
                shutil.rmtree(path, ignore_errors=False)
        try:
            self._projects.delete(project_id)
        except ProjectNotFoundError:
            pass
        self._projects.resolve_recovery(_text(record, "id"))


def _text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Recovery record field {key!r} is invalid.")
    return value


def _strings(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return []
    return list(value)


def _unlink(value: object) -> None:
    if isinstance(value, str) and value:
        Path(value).unlink(missing_ok=True)
