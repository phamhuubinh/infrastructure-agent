from __future__ import annotations

import math
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
from orion.knowledge.semantic import SemanticIndexService
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
