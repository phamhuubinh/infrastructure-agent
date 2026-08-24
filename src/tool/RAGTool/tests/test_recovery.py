from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.project_store import ProjectRecoveringError, ProjectStore
from app.recovery import ProjectRecovery, RecoveryPendingError
from app.sparse.bm25_index import BM25Index
from app.vectordb.base import VectorRecord
from app.vectordb.memory_store import InMemoryVectorStore


class _FailingBm25(BM25Index):
    def __init__(self) -> None:
        super().__init__()
        self.fail_delete = False
        self.fail_clear = False

    def delete(self, doc_id: str) -> None:
        if self.fail_delete:
            raise RuntimeError("bm25 delete failed")
        super().delete(doc_id)

    def clear(self) -> None:
        if self.fail_clear:
            raise RuntimeError("bm25 clear failed")
        super().clear()


class _FailingVector(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_delete = False
        self.fail_collection_delete = False
        self.fail_upsert = False

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if self.fail_upsert:
            raise RuntimeError("vector insert failed")
        super().upsert(collection, records)

    def delete(self, collection: str, ids: list[str]) -> None:
        if self.fail_delete:
            raise RuntimeError("vector delete failed")
        super().delete(collection, ids)

    def delete_collection(self, collection: str) -> None:
        if self.fail_collection_delete:
            raise RuntimeError("vector collection delete failed")
        super().delete_collection(collection)


def _recovery(tmp_path: Path):
    projects = ProjectStore(tmp_path)
    vector = _FailingVector()
    indexes: dict[str, _FailingBm25] = {}

    def bm25(project_id: str) -> _FailingBm25:
        return indexes.setdefault(project_id, _FailingBm25())

    return projects, vector, bm25, ProjectRecovery(
        projects=projects,
        vector_store=vector,
        bm25_for_project=bm25,
        collection_for_project=lambda project_id: f"documents_{project_id}",
    )


def _document(projects: ProjectStore, project_id: str, tmp_path: Path) -> dict:
    file_path = projects.project_documents_dir(project_id) / "doc.txt"
    file_path.write_text("document", encoding="utf-8")
    document = {
        "id": "doc",
        "filename": "doc.txt",
        "chunk_ids": ["chunk"],
        "storage_path": str(file_path),
    }
    projects.add_document(project_id, document)
    return document


def test_upload_recovery_removes_orphans_after_vector_or_bm25_failure(
    tmp_path: Path,
) -> None:
    projects, vector, bm25, recovery = _recovery(tmp_path)
    project = projects.create("alpha")
    staged = projects.staging_documents_dir(project["id"]) / "doc.txt"
    staged.write_text("partial", encoding="utf-8")
    record = projects.begin_recovery(
        "upload",
        project_id=project["id"],
        doc_id="doc",
        staging_path=str(staged),
        final_path=str(projects.project_documents_dir(project["id"]) / "doc.txt"),
        chunk_ids=["chunk"],
        phase="indexing",
    )
    vector.fail_delete = True

    with pytest.raises(RecoveryPendingError):
        recovery.recover(project["id"])

    assert projects.get(project["id"])["documents"] == []
    assert projects.recovery_records(project["id"])[0]["id"] == record["id"]
    vector.fail_delete = False
    recovery.recover(project["id"])
    assert not staged.exists()
    assert projects.recovery_records(project["id"]) == []


def test_upload_metadata_or_promotion_failure_stays_invisible_and_recovers(
    tmp_path: Path,
) -> None:
    projects, _, _, recovery = _recovery(tmp_path)
    project = projects.create("alpha")
    final_path = projects.project_documents_dir(project["id"]) / "doc.txt"
    final_path.write_text("indexed but uncommitted", encoding="utf-8")
    projects.begin_recovery(
        "upload",
        project_id=project["id"],
        doc_id="doc",
        staging_path=str(projects.staging_documents_dir(project["id"]) / "doc.txt"),
        final_path=str(final_path),
        chunk_ids=["chunk"],
        phase="promoted",
    )

    # This is the crash/failure state after final-file promotion or before the
    # project metadata commit: no normal document is visible.
    assert projects.get(project["id"])["documents"] == []
    recovery.recover(project["id"])
    assert not final_path.exists()
    assert projects.recovery_records(project["id"]) == []


def test_document_delete_tombstones_before_partial_index_or_file_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, vector, bm25, recovery = _recovery(tmp_path)
    project = projects.create("alpha")
    document = _document(projects, project["id"], tmp_path)
    record = projects.begin_recovery(
        "document_delete",
        project_id=project["id"],
        doc_id="doc",
        chunk_ids=document["chunk_ids"],
        storage_path=document["storage_path"],
        phase="prepared",
    )
    projects.mark_document_deleting(project["id"], "doc")
    projects.update_recovery(record["id"], phase="tombstoned")
    bm25(project["id"]).fail_delete = True

    with pytest.raises(RecoveryPendingError):
        recovery.recover(project["id"])

    assert projects.get_document(project["id"], "doc") is None
    assert Path(document["storage_path"]).exists()
    bm25(project["id"]).fail_delete = False
    recovery.recover(project["id"])
    assert not Path(document["storage_path"]).exists()

    # File removal failure also leaves the tombstone durable and retryable.
    document = _document(projects, project["id"], tmp_path)
    record = projects.begin_recovery(
        "document_delete",
        project_id=project["id"],
        doc_id="doc",
        chunk_ids=document["chunk_ids"],
        storage_path=document["storage_path"],
        phase="tombstoned",
    )
    projects.mark_document_deleting(project["id"], "doc")
    import app.recovery as recovery_module

    monkeypatch.setattr(recovery_module, "_unlink", lambda _path: (_ for _ in ()).throw(OSError("unlink failed")))
    with pytest.raises(RecoveryPendingError):
        recovery.recover(project["id"])
    assert projects.recovery_records(project["id"])[0]["id"] == record["id"]


def test_project_delete_tombstone_survives_later_cleanup_and_metadata_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, vector, bm25, recovery = _recovery(tmp_path)
    project = projects.create("alpha")
    document = _document(projects, project["id"], tmp_path)
    record = projects.begin_recovery(
        "project_delete",
        project_id=project["id"],
        chunk_ids=document["chunk_ids"],
        documents_dir=str(projects.documents_dir / project["id"]),
        phase="tombstoned",
    )
    projects.mark_project_deleting(project["id"])
    bm25(project["id"]).fail_clear = True

    with pytest.raises(RecoveryPendingError):
        recovery.recover(project["id"])
    with pytest.raises(ProjectRecoveringError):
        projects.get(project["id"])
    assert projects.recovery_records(project["id"])[0]["id"] == record["id"]
    bm25(project["id"]).fail_clear = False

    original_delete = projects.delete
    monkeypatch.setattr(projects, "delete", lambda _project_id: (_ for _ in ()).throw(OSError("metadata failed")))
    with pytest.raises(RecoveryPendingError):
        recovery.recover(project["id"])
    assert projects.recovery_records(project["id"])
    monkeypatch.setattr(projects, "delete", original_delete)
    recovery.recover(project["id"])
    assert projects.recovery_records(project["id"]) == []


def test_document_delete_file_then_metadata_failure_remains_tombstoned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, _, _, recovery = _recovery(tmp_path)
    project = projects.create("alpha")
    document = _document(projects, project["id"], tmp_path)
    record = projects.begin_recovery(
        "document_delete",
        project_id=project["id"],
        doc_id="doc",
        chunk_ids=document["chunk_ids"],
        storage_path=document["storage_path"],
        phase="tombstoned",
    )
    projects.mark_document_deleting(project["id"], "doc")
    original_remove = projects.remove_document
    monkeypatch.setattr(
        projects,
        "remove_document",
        lambda *_args: (_ for _ in ()).throw(OSError("metadata remove failed")),
    )

    with pytest.raises(RecoveryPendingError):
        recovery.recover(project["id"])

    assert not Path(document["storage_path"]).exists()
    assert projects.get_document(project["id"], "doc") is None
    assert projects.recovery_records(project["id"])[0]["id"] == record["id"]
    monkeypatch.setattr(projects, "remove_document", original_remove)
    recovery.recover(project["id"])


def test_upload_fault_boundaries_leave_a_persistent_invisible_recovery_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.main as rag_main

    projects, vector, _, recovery = _recovery(tmp_path)
    project = projects.create("alpha")
    monkeypatch.setattr(rag_main, "_projects", projects)
    monkeypatch.setattr(rag_main, "_vector_store", vector)
    monkeypatch.setattr(rag_main, "_data_dir", tmp_path)
    monkeypatch.setattr(rag_main, "_bm25_indexes", {})
    monkeypatch.setattr(rag_main, "_project_locks", {})

    def upload() -> UploadFile:
        return UploadFile(filename="doc.txt", file=BytesIO(b"content"))

    class _Pipeline:
        def __init__(self, failure: str | None) -> None:
            self.failure = failure

        def ingest(self, _path, *, doc_id, metadata, on_prepared_chunks):
            on_prepared_chunks(["chunk"])
            if self.failure == "vector":
                vector.fail_upsert = True
                vector.upsert("unused", [])
            vector.upsert(
                rag_main._collection(project["id"]),
                [VectorRecord("chunk", [1.0], {"doc_id": doc_id})],
            )
            if self.failure == "bm25":
                raise RuntimeError("bm25 insert failed")
            return SimpleNamespace(
                doc_id=doc_id,
                chunk_count=1,
                parser_used="test",
                warnings=[],
                chunk_ids=["chunk"],
            )

    for failure in ("vector", "bm25"):
        vector.fail_upsert = False
        monkeypatch.setattr(
            rag_main,
            "_ingest_pipeline",
            lambda _project, current_failure=failure: _Pipeline(current_failure),
        )
        with pytest.raises(HTTPException, match="Ingestion failed"):
            rag_main.upload_project_document(project["id"], upload())
        assert projects.get(project["id"])["documents"] == []
        assert projects.recovery_records(project["id"])
        vector.fail_upsert = False
        recovery.recover(project["id"])

    monkeypatch.setattr(rag_main, "_ingest_pipeline", lambda _project: _Pipeline(None))
    monkeypatch.setattr(projects, "add_document", lambda *_args: (_ for _ in ()).throw(OSError("metadata failed")))
    with pytest.raises(HTTPException, match="Ingestion failed"):
        rag_main.upload_project_document(project["id"], upload())
    assert projects.get(project["id"])["documents"] == []
    assert projects.recovery_records(project["id"])
    recovery.recover(project["id"])

    monkeypatch.setattr(
        rag_main,
        "_promote_staged",
        lambda *_args: (_ for _ in ()).throw(OSError("promotion failed")),
    )
    with pytest.raises(HTTPException, match="Ingestion failed"):
        rag_main.upload_project_document(project["id"], upload())
    assert projects.get(project["id"])["documents"] == []
    assert projects.recovery_records(project["id"])
    monkeypatch.undo()
