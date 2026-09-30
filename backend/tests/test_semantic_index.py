from __future__ import annotations

import math
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from embedding_fakes import FakeEmbeddingPort

from orion.contracts import RuntimeScope
from orion.embeddings import (
    EmbeddingProfile,
    decode_vector,
    encode_vector,
    text_digest,
    validate_vector,
)
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.semantic import SemanticIndexingError, SemanticIndexService
from orion.knowledge.service import KnowledgeService
from orion.persistence.sqlite import SQLiteStore


def profile(**changes: object) -> EmbeddingProfile:
    original = EmbeddingProfile(
        implementation="fake",
        model="controlled",
        revision="v1",
        artifact_digest="a" * 64,
        tokenizer_digest="b" * 64,
        precision="float32",
        dimension=2,
        pooling="mean",
        normalization="l2",
        query_prefix="query: ",
        passage_prefix="passage: ",
        windowing_version="v1",
        maximum_input_tokens=512,
    )
    return replace(original, **changes)


def scope(session_id: str, *attachment_ids: str, project_id: str | None = None) -> RuntimeScope:
    return RuntimeScope(
        session_id=session_id,
        attachment_ids=attachment_ids,
        project_id=project_id,
        principal_id="local",
        workspace_id="local",
    )


def test_profile_identity_and_incompatibility() -> None:
    first = profile()
    assert first.profile_id == profile().profile_id
    assert first.canonical_json() == profile().canonical_json()
    for change in (
        {"revision": "v2"},
        {"artifact_digest": "c" * 64},
        {"tokenizer_digest": "d" * 64},
        {"precision": "int8"},
        {"dimension": 3},
        {"pooling": "cls"},
        {"normalization": "none"},
        {"query_prefix": "q: "},
        {"passage_prefix": "p: "},
        {"windowing_version": "v2"},
        {"maximum_input_tokens": 256},
        {"tokenizer_digest": None},
        {"query_prefix": ""},
    ):
        assert replace(first, **change).profile_id != first.profile_id


def test_vector_blob_is_little_endian_float32_and_rejects_invalid_values() -> None:
    blob = encode_vector((1.0, -2.0), 2)
    assert blob == bytes.fromhex("0000803f000000c0")
    assert decode_vector(blob, 2) == (1.0, -2.0)
    assert decode_vector(encode_vector((0.1, 0.2), 2), 2) == validate_vector((0.1, 0.2), 2)
    with pytest.raises(ValueError, match="dimension"):
        encode_vector((1.0,), 2)
    with pytest.raises(ValueError, match="length"):
        decode_vector(blob[:-1], 2)
    for bad in (math.nan, math.inf, -math.inf, 1e100):
        with pytest.raises(ValueError):
            encode_vector((1.0, bad), 2)


def test_persist_scope_tombstone_and_profile_isolation(store: SQLiteStore, tmp_path: Path) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    project_a = store.create_project("A")
    project_b = store.create_project("B")
    session_a = store.create_session(project_id=project_a["project_id"])
    session_b = store.create_session(project_id=project_b["project_id"])
    attachment = knowledge.attach(session_a, "alpha.txt", b"alpha fact")
    other_attachment = knowledge.attach(session_b, "other.txt", b"other fact")
    project_doc = knowledge.attach_project(project_a["project_id"], "project.txt", b"project fact")
    foreign_doc = knowledge.attach_project(project_b["project_id"], "foreign.txt", b"foreign fact")
    vectors = {
        "alpha fact": (1.0, 0.0),
        "other fact": (1.0, 0.0),
        "project fact": (0.9, 0.1),
        "foreign fact": (1.0, 0.0),
    }
    fake = FakeEmbeddingPort(profile(), passages=vectors, queries={"find": (1.0, 0.0)})
    semantic = SemanticIndexService(store, fake)
    for upload in (attachment, other_attachment, project_doc, foreign_doc):
        semantic.index_document(upload.document.document_id)
    allowed_scope = scope(session_a, attachment.attachment_id, project_id=project_a["project_id"])
    hits = semantic.search(allowed_scope, "find", 10)
    expected = {
        store.document_segments(attachment.document.document_id)[0]["segment_id"],
        store.document_segments(project_doc.document.document_id)[0]["segment_id"],
    }
    assert {hit.segment_id for hit in hits} == expected
    assert len(fake.query_batches) == 1
    with pytest.raises(PermissionError):
        semantic.search(allowed_scope, "find", 10, (foreign_doc.document.document_id,))
    assert {
        hit.segment_id
        for hit in semantic.search(allowed_scope, "find", 10, (attachment.document.document_id,))
    } == {store.document_segments(attachment.document.document_id)[0]["segment_id"]}
    changed = SemanticIndexService(
        store,
        FakeEmbeddingPort(profile(revision="v2"), passages=vectors, queries={"find": (1.0, 0.0)}),
    )
    assert changed.search(allowed_scope, "find", 10) == ()
    assert knowledge.delete(attachment.document.document_id, allowed_scope)
    assert {hit.segment_id for hit in semantic.search(allowed_scope, "find", 10)} == {
        store.document_segments(project_doc.document.document_id)[0]["segment_id"]
    }
    assert store.delete_project(project_a["project_id"]) is not None
    assert semantic.search(allowed_scope, "find", 10) == ()
    assert store._connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_stale_vectors_and_lexical_fallback(store: SQLiteStore, tmp_path: Path) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    upload = knowledge.attach(session, "ready.txt", b"backup retention thirty days")
    runtime_scope = scope(session, upload.attachment_id)
    segment = store.document_segments(upload.document.document_id)[0]
    semantic = SemanticIndexService(
        store,
        FakeEmbeddingPort(
            profile(),
            passages={"backup retention thirty days": (1.0, 0.0)},
            queries={"find": (1.0, 0.0)},
        ),
    )
    assert (
        store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "missing"
    )
    assert (
        knowledge.document_status(upload.document.document_id, runtime_scope)["semantic_indexing"][
            0
        ]["status"]
        == "missing"
    )
    assert knowledge.search(runtime_scope, "ready.txt", 1)[0].document == upload.document
    semantic.index_document(upload.document.document_id)
    assert semantic.search(runtime_scope, "find", 1)[0].segment_id == segment["segment_id"]
    with store._lock, store._connection:
        store._connection.execute(
            "UPDATE document_segments SET text = ? WHERE segment_id = ?",
            ("changed text", segment["segment_id"]),
        )
    assert semantic.search(runtime_scope, "find", 1) == ()
    assert len(store.segments_needing_embeddings(upload.document.document_id, profile())) == 1
    assert knowledge.search(runtime_scope, "ready.txt", 1)[0].document == upload.document
    assert store.document(upload.document.document_id)["status"] == "ready"


def test_embedding_windows_reparse_and_explicit_backfill(
    store: SQLiteStore, tmp_path: Path
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    upload = knowledge.attach(session, "windows.txt", b"Original segment")
    segment = store.document_segments(upload.document.document_id)[0]
    fake = FakeEmbeddingPort(
        profile(), passages={"Original segment": (0.0, 1.0)}, queries={"find": (1.0, 0.0)}
    )
    semantic = SemanticIndexService(store, fake)
    store.put_segment_embeddings(
        str(segment["segment_id"]),
        profile(),
        text_digest("Original segment"),
        ((0.0, 1.0), (1.0, 0.0)),
    )
    assert [
        row["window_ordinal"]
        for row in store.visible_embedding_rows(scope(session, upload.attachment_id), profile())
    ] == [0, 1]
    assert semantic.search(scope(session, upload.attachment_id), "find", 1)[0].score == 1.0
    with pytest.raises(ValueError, match="changed"):
        store.put_segment_embeddings(
            str(segment["segment_id"]), profile(), text_digest("old"), ((1.0, 0.0),)
        )
    store.set_semantic_index_state(upload.document.document_id, profile().profile_id, "ready", 1, 1)
    store.store_parsed_document(
        upload.document.document_id,
        "Original segment",
        [
            {
                "segment_id": segment["segment_id"],
                "ordinal": 0,
                "text": "Original segment",
                "page": None,
                "section": None,
            }
        ],
    )
    assert (
        store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "missing"
    )
    assert store.visible_embedding_rows(scope(session, upload.attachment_id), profile()) == []
    semantic.reconcile_missing()
    assert fake.passage_batches == [("Original segment",)]
    assert (
        store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "ready"
    )
    assert (
        store.document_segments(upload.document.document_id)[0]["segment_id"]
        == segment["segment_id"]
    )


def test_failed_batch_resumes_without_duplicates_after_reopen(
    store: SQLiteStore, tmp_path: Path
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    upload = knowledge.attach(
        session, "two.md", b"# First\n\nfirst text\n\n# Second\n\nsecond text", "text/markdown"
    )
    segments = store.document_segments(upload.document.document_id)
    assert len(segments) == 2
    mapping = {str(row["text"]): (1.0, 0.0) for row in segments}
    failing = FakeEmbeddingPort(
        profile(), passages=mapping, queries={"find": (1.0, 0.0)}, fail_passage_call=2
    )
    with pytest.raises(RuntimeError, match="interruption"):
        SemanticIndexService(store, failing).index_document(
            upload.document.document_id, batch_size=1
        )
    state = store.semantic_index_state(upload.document.document_id, profile().profile_id)
    assert (state["status"], state["indexed_segments"], state["total_segments"]) == ("failed", 1, 2)
    assert (
        knowledge.document_status(
            upload.document.document_id, scope(session, upload.attachment_id)
        )["semantic_indexing"][0]["status"]
        == "failed"
    )
    assert (
        knowledge.search(scope(session, upload.attachment_id), "two.md", 1)[0].document
        == upload.document
    )
    store.close()
    reopened = SQLiteStore(tmp_path / "orion.db")
    try:
        restored = FakeEmbeddingPort(profile(), passages=mapping, queries={"find": (1.0, 0.0)})
        index = SemanticIndexService(reopened, restored)
        index.index_document(upload.document.document_id, batch_size=1)
        assert restored.passage_batches == [(str(segments[1]["text"]),)]
        assert (
            reopened.semantic_index_state(upload.document.document_id, profile().profile_id)[
                "status"
            ]
            == "ready"
        )
        index.index_document(upload.document.document_id)
        assert len(restored.passage_batches) == 1
        rows = reopened.visible_embedding_rows(scope(session, upload.attachment_id), profile())
        assert len(rows) == 2
        assert {row["source_text_digest"] for row in rows} == {
            text_digest(str(segment["text"])) for segment in segments
        }
    finally:
        reopened.close()


def test_multi_window_index_and_production_order_unchanged(
    store: SQLiteStore, tmp_path: Path
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    first = knowledge.attach(session, "first.txt", b"alpha beta")
    second = knowledge.attach(session, "second.txt", b"beta gamma")
    runtime_scope = scope(session, first.attachment_id, second.attachment_id)
    before = tuple(hit.segment_id for hit in knowledge.search(runtime_scope, "beta", 10))

    class WindowedFake(FakeEmbeddingPort):
        def passage_windows(self, text: str) -> tuple[str, ...]:
            return tuple(text.split())

    fake = WindowedFake(
        profile(),
        passages={"alpha": (1.0, 0.0), "beta": (0.0, 1.0), "gamma": (1.0, 0.0)},
        queries={"beta": (0.0, 1.0)},
    )
    index = SemanticIndexService(store, fake)
    assert index.reconcile_missing(max_documents=2).reindexed == 2
    assert fake.passage_batches == [("alpha", "beta"), ("beta", "gamma")]
    assert len(store.visible_embedding_rows(runtime_scope, profile())) == 4
    assert len(index.search(runtime_scope, "beta", 10)) == 2
    assert tuple(hit.segment_id for hit in knowledge.search(runtime_scope, "beta", 10)) == before
    assert index.reconcile_missing(max_documents=2).reindexed == 0
    assert len(store.visible_embedding_rows(runtime_scope, profile())) == 4
    first_segment = store.document_segments(first.document.document_id)[0]
    with store._lock, store._connection:
        store._connection.execute(
            "UPDATE document_segments SET text = ? WHERE segment_id = ?",
            ("alpha gamma", first_segment["segment_id"]),
        )
    assert index.reconcile_missing(max_documents=1).reindexed == 1
    assert len(store.visible_embedding_rows(runtime_scope, profile())) == 4


def test_deletion_during_embedding_cannot_publish_vectors(
    store: SQLiteStore, tmp_path: Path
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    upload = knowledge.attach(session, "temporary.txt", b"sensitive transient text")
    runtime_scope = scope(session, upload.attachment_id)

    class DeletingFake(FakeEmbeddingPort):
        def embed_passages(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            assert knowledge.delete(upload.document.document_id, runtime_scope)
            return super().embed_passages(texts)

    fake = DeletingFake(
        profile(),
        passages={"sensitive transient text": (1.0, 0.0)},
        queries={"text": (1.0, 0.0)},
    )
    index = SemanticIndexService(store, fake)
    with pytest.raises(LookupError, match="live ready"):
        index.index_document(upload.document.document_id)
    assert index.search(runtime_scope, "text", 10) == ()
    assert knowledge.search(runtime_scope, "text", 10) == ()


def test_backfill_cursor_bounds_250_documents_and_repairs_late_rows(
    store: SQLiteStore, tmp_path: Path
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    uploads = [
        knowledge.attach(session, f"document-{number:03d}.txt", f"passage {number:03d}".encode())
        for number in range(250)
    ]
    ordered_ids = [
        str(row["document_id"])
        for row in store._connection.execute(
            "SELECT document_id FROM documents ORDER BY created_at, document_id"
        )
    ]
    late_missing = ordered_ids[-2]
    late_failed = ordered_ids[-3]
    late_tombstone = ordered_ids[-4]
    late_stale = ordered_ids[-1]
    multi_text = str(store.document_segments(late_missing)[0]["text"])
    passages = {f"passage {number:03d}": (1.0, 0.0) for number in range(250)}
    passages.update({multi_text + " A": (1.0, 0.0), multi_text + " B": (0.0, 1.0)})
    passages["updated late text"] = (0.0, 1.0)

    class CountingFake(FakeEmbeddingPort):
        def __init__(self) -> None:
            super().__init__(profile(), passages=passages, queries={"find": (1.0, 0.0)})
            self.windowed: list[str] = []

        def passage_windows(self, text: str) -> tuple[str, ...]:
            self.windowed.append(text)
            return (text + " A", text + " B") if text == multi_text else (text,)

    fake = CountingFake()
    index = SemanticIndexService(store, fake)
    first = index.reconcile_missing(max_documents=10)
    assert (first.inspected, first.reindexed, first.failed) == (10, 10, 0)
    assert len(fake.windowed) == 10
    second = index.reconcile_missing(max_documents=10)
    assert (second.inspected, second.reindexed, second.failed) == (10, 10, 0)
    assert len(fake.windowed) == 20
    assert first.cursor_document_id != second.cursor_document_id
    for _ in range(23):
        progress = index.reconcile_missing(max_documents=10)
        assert progress.inspected <= 10
    assert len(fake.windowed) == 250
    assert store.semantic_index_state(late_stale, profile().profile_id)["status"] == "ready"

    healthy = index.reconcile_missing(max_documents=10)
    assert (healthy.inspected, healthy.reindexed, healthy.failed, healthy.wrapped) == (
        10,
        0,
        0,
        True,
    )
    assert len(fake.windowed) == 250  # Healthy documents required no tokenizer calls.

    stale_segment = store.document_segments(late_stale)[0]
    missing_segment = store.document_segments(late_missing)[0]
    failed_segment = store.document_segments(late_failed)[0]
    with store._lock, store._connection:
        store._connection.execute(
            "UPDATE document_segments SET text = ? WHERE segment_id = ?",
            ("updated late text", stale_segment["segment_id"]),
        )
        store._connection.execute(
            "DELETE FROM segment_embeddings WHERE segment_id = ? AND profile_id = ? "
            "AND window_ordinal = 1",
            (missing_segment["segment_id"], profile().profile_id),
        )
        store._connection.execute(
            "DELETE FROM segment_embeddings WHERE segment_id = ? AND profile_id = ?",
            (failed_segment["segment_id"], profile().profile_id),
        )
    store.set_semantic_index_state(late_failed, profile().profile_id, "failed", 0, 1)
    runtime_scope = scope(session, *(upload.attachment_id for upload in uploads))
    assert knowledge.delete(late_tombstone, runtime_scope)
    for _ in range(25):
        progress = index.reconcile_missing(max_documents=10)
        assert progress.inspected <= 10
    assert len(fake.windowed) == 253
    assert store.semantic_index_state(late_failed, profile().profile_id)["status"] == "ready"
    assert store.segments_needing_embeddings(late_stale, profile()) == []
    assert store.segments_needing_embeddings(late_missing, profile()) == []
    assert store.segments_needing_embeddings(late_failed, profile()) == []
    assert store.document(late_tombstone) is None
    assert (
        store._connection.execute(
            "SELECT COUNT(*) FROM segment_embeddings WHERE segment_id IN "
            "(SELECT segment_id FROM document_segments WHERE document_id = ?)",
            (late_tombstone,),
        ).fetchone()[0]
        == 0
    )


def test_backfill_cursor_persists_across_failure_and_reopen(tmp_path: Path) -> None:
    database = tmp_path / "resume.db"
    store = SQLiteStore(database)
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    uploads = [
        knowledge.attach(session, f"restart-{number:02d}.txt", f"restart {number:02d}".encode())
        for number in range(20)
    ]
    passages = {f"restart {number:02d}": (1.0, 0.0) for number in range(20)}
    failing = FakeEmbeddingPort(
        profile(), passages=passages, queries={"find": (1.0, 0.0)}, fail_passage_call=4
    )
    first = SemanticIndexService(store, failing).reconcile_missing(max_documents=10)
    assert (first.inspected, first.reindexed, first.failed) == (10, 9, 1)
    failed_ids = [
        upload.document.document_id
        for upload in uploads
        if store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "failed"
    ]
    assert len(failed_ids) == 1
    store.close()

    reopened = SQLiteStore(database)
    try:
        restored = FakeEmbeddingPort(profile(), passages=passages, queries={"find": (1.0, 0.0)})
        index = SemanticIndexService(reopened, restored)
        second = index.reconcile_missing(max_documents=10)
        assert (second.inspected, second.reindexed, second.failed) == (10, 10, 0)
        assert second.cursor_document_id != first.cursor_document_id
        third = index.reconcile_missing(max_documents=10)
        assert (third.inspected, third.reindexed, third.failed, third.wrapped) == (10, 1, 0, True)
        assert (
            reopened.semantic_index_state(failed_ids[0], profile().profile_id)["status"] == "ready"
        )
        assert (
            reopened._connection.execute(
                "SELECT COUNT(*) FROM segment_embeddings WHERE profile_id = ?",
                (profile().profile_id,),
            ).fetchone()[0]
            == 20
        )
    finally:
        reopened.close()


def test_backfill_interruption_reopens_at_unfinished_document(tmp_path: Path) -> None:
    database = tmp_path / "interrupted.db"
    store = SQLiteStore(database)
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    for number in range(12):
        knowledge.attach(session, f"interrupt-{number:02d}.txt", f"item {number:02d}".encode())
    ordered_ids = [
        str(row["document_id"])
        for row in store._connection.execute(
            "SELECT document_id FROM documents ORDER BY created_at, document_id"
        )
    ]
    passages = {f"item {number:02d}": (1.0, 0.0) for number in range(12)}

    class InterruptedFake(FakeEmbeddingPort):
        def __init__(self) -> None:
            super().__init__(profile(), passages=passages, queries={"find": (1.0, 0.0)})
            self.calls = 0

        def embed_passages(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            self.calls += 1
            if self.calls == 4:
                raise KeyboardInterrupt
            return super().embed_passages(texts)

    with pytest.raises(KeyboardInterrupt):
        SemanticIndexService(store, InterruptedFake()).reconcile_missing(max_documents=10)
    cursor = store._connection.execute(
        "SELECT last_document_id FROM semantic_backfill_cursors WHERE profile_id = ?",
        (profile().profile_id,),
    ).fetchone()
    assert cursor is not None
    assert cursor["last_document_id"] == ordered_ids[2]
    store.close()

    reopened = SQLiteStore(database)
    try:
        restored = SemanticIndexService(
            reopened,
            FakeEmbeddingPort(profile(), passages=passages, queries={"find": (1.0, 0.0)}),
        )
        resumed = restored.reconcile_missing(max_documents=10)
        assert (resumed.inspected, resumed.reindexed, resumed.failed) == (9, 9, 0)
        assert (
            reopened._connection.execute(
                "SELECT COUNT(*) FROM segment_embeddings WHERE profile_id = ?",
                (profile().profile_id,),
            ).fetchone()[0]
            == 12
        )
        assert (
            reopened.semantic_index_state(ordered_ids[3], profile().profile_id)["status"] == "ready"
        )
    finally:
        reopened.close()


def test_backfill_never_indexes_preexisting_tombstone(store: SQLiteStore, tmp_path: Path) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    uploads = [
        knowledge.attach(session, f"live-{number:02d}.txt", f"live {number:02d}".encode())
        for number in range(12)
    ]
    deleted = uploads[-1]
    runtime_scope = scope(session, *(upload.attachment_id for upload in uploads))
    assert knowledge.delete(deleted.document.document_id, runtime_scope)
    fake = FakeEmbeddingPort(
        profile(),
        passages={f"live {number:02d}": (1.0, 0.0) for number in range(12)},
        queries={"find": (1.0, 0.0)},
    )
    index = SemanticIndexService(store, fake)
    inspected = sum(index.reconcile_missing(max_documents=5).inspected for _ in range(3))
    assert inspected == 11
    assert ("live 11",) not in fake.passage_batches
    assert len(fake.passage_batches) == 11
    assert (
        store._connection.execute(
            "SELECT COUNT(*) FROM segment_embeddings WHERE segment_id IN "
            "(SELECT segment_id FROM document_segments WHERE document_id = ?)",
            (deleted.document.document_id,),
        ).fetchone()[0]
        == 0
    )


def test_stale_ready_document_window_failure_persists_failed_state(
    store: SQLiteStore, tmp_path: Path
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    upload = knowledge.attach(session, "stale.txt", b"original passage")
    segment = store.document_segments(upload.document.document_id)[0]

    class WindowFailure(FakeEmbeddingPort):
        fail_windows = False

        def passage_windows(self, text: str) -> tuple[str, ...]:
            if self.fail_windows:
                raise RuntimeError("tokenizer failure")
            return super().passage_windows(text)

    fake = WindowFailure(
        profile(),
        passages={"original passage": (1.0, 0.0), "revised passage": (0.0, 1.0)},
        queries={"find": (1.0, 0.0)},
    )
    index = SemanticIndexService(store, fake)
    index.index_document(upload.document.document_id)
    assert (
        store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "ready"
    )
    with store._lock, store._connection:
        store._connection.execute(
            "UPDATE document_segments SET text = ? WHERE segment_id = ?",
            ("revised passage", segment["segment_id"]),
        )
    fake.fail_windows = True
    with pytest.raises(SemanticIndexingError, match="tokenizer failure"):
        index.index_document(upload.document.document_id)
    state = store.semantic_index_state(upload.document.document_id, profile().profile_id)
    assert state["status"] == "failed"
    assert "tokenizer failure" in state["error_message"]
    progress = index.reconcile_missing(max_documents=1)
    assert (progress.inspected, progress.reindexed, progress.failed) == (1, 0, 1)
    assert (
        store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "failed"
    )
    runtime_scope = scope(session, upload.attachment_id)
    assert knowledge.search(runtime_scope, "stale.txt", 1)
    assert knowledge.read(runtime_scope, upload.document.document_id).segments
    fake.fail_windows = False
    repaired = index.reconcile_missing(max_documents=1)
    assert (repaired.inspected, repaired.reindexed, repaired.failed) == (1, 1, 0)
    assert (
        store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "ready"
    )


def test_unexpected_persistence_failure_aborts_without_advancing_cursor(
    store: SQLiteStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    for number in range(2):
        knowledge.attach(session, f"item-{number}.txt", f"item {number}".encode())
    ordered_ids = [
        str(row["document_id"])
        for row in store._connection.execute(
            "SELECT document_id FROM documents ORDER BY created_at, document_id"
        )
    ]
    failing_segment = str(store.document_segments(ordered_ids[1])[0]["segment_id"])
    original_put = store.put_segment_embeddings

    def fail_second(
        segment_id: str,
        embedding_profile: EmbeddingProfile,
        source_digest: str,
        windows: tuple[tuple[float, ...], ...],
    ) -> None:
        if segment_id == failing_segment:
            raise sqlite3.OperationalError("simulated disk failure")
        original_put(segment_id, embedding_profile, source_digest, windows)

    monkeypatch.setattr(store, "put_segment_embeddings", fail_second)
    fake = FakeEmbeddingPort(
        profile(),
        passages={"item 0": (1.0, 0.0), "item 1": (0.0, 1.0)},
        queries={"find": (1.0, 0.0)},
    )
    index = SemanticIndexService(store, fake)
    with pytest.raises(sqlite3.OperationalError, match="disk failure"):
        index.reconcile_missing(max_documents=2)
    cursor = store._connection.execute(
        "SELECT last_document_id FROM semantic_backfill_cursors WHERE profile_id = ?",
        (profile().profile_id,),
    ).fetchone()
    assert cursor is not None and cursor["last_document_id"] == ordered_ids[0]
    assert store.semantic_index_state(ordered_ids[1], profile().profile_id)["status"] == "indexing"
    monkeypatch.setattr(store, "put_segment_embeddings", original_put)
    resumed = index.reconcile_missing(max_documents=2)
    assert (resumed.inspected, resumed.reindexed, resumed.failed) == (1, 1, 0)
    assert store.semantic_index_state(ordered_ids[1], profile().profile_id)["status"] == "ready"


def test_unexpected_windowing_programming_error_aborts_without_cursor(
    store: SQLiteStore, tmp_path: Path
) -> None:
    knowledge = KnowledgeService(store, LocalBlobStore(tmp_path / "blobs"))
    session = store.create_session()
    upload = knowledge.attach(session, "programming.txt", b"programming error")

    class ProgrammingFake(FakeEmbeddingPort):
        broken = True

        def passage_windows(self, text: str) -> tuple[str, ...]:
            if self.broken:
                raise TypeError("unexpected adapter bug")
            return super().passage_windows(text)

    fake = ProgrammingFake(
        profile(),
        passages={"programming error": (1.0, 0.0)},
        queries={"find": (1.0, 0.0)},
    )
    index = SemanticIndexService(store, fake)
    with pytest.raises(TypeError, match="unexpected adapter bug"):
        index.reconcile_missing(max_documents=1)
    assert (
        store._connection.execute(
            "SELECT 1 FROM semantic_backfill_cursors WHERE profile_id = ?",
            (profile().profile_id,),
        ).fetchone()
        is None
    )
    assert (
        store.semantic_index_state(upload.document.document_id, profile().profile_id)["status"]
        == "indexing"
    )
    fake.broken = False
    resumed = index.reconcile_missing(max_documents=1)
    assert (resumed.inspected, resumed.reindexed, resumed.failed) == (1, 1, 0)
