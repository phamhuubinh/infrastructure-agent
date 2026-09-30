"""Deterministic production hybrid retrieval contracts without model files or network."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest

from orion.contracts import RuntimeScope
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.local_embeddings import LocalEmbeddingQueryError, LocalEmbeddingUnavailable
from orion.knowledge.ranking import HYBRID_CANDIDATE_DEPTH, fuse_hybrid_ranks
from orion.knowledge.semantic import SemanticHit
from orion.knowledge.service import KnowledgeService


def _scope(session: str, *attachments: str, project: str | None = None) -> RuntimeScope:
    return RuntimeScope(
        session_id=session,
        attachment_ids=attachments,
        project_id=project,
        principal_id="local",
        workspace_id="local",
    )


class ScriptedSemantic:
    def __init__(self, hits: tuple[SemanticHit, ...] = (), error: Exception | None = None) -> None:
        self.hits = hits
        self.error = error
        self.calls: list[tuple[RuntimeScope, str, int, tuple[str, ...]]] = []

    def search(
        self, scope: RuntimeScope, query: str, limit: int, document_ids: tuple[str, ...] = ()
    ) -> tuple[SemanticHit, ...]:
        self.calls.append((scope, query, limit, document_ids))
        if self.error:
            raise self.error
        return self.hits[:limit]


def _service(store, tmp_path, factory: Callable[[], ScriptedSemantic] | None = None):  # type: ignore[no-untyped-def]
    return KnowledgeService(
        store, LocalBlobStore(tmp_path / "blobs"), semantic_retriever_factory=factory
    )


def _hit(service: KnowledgeService, scope: RuntimeScope, name: str) -> str:
    return next(
        segment.segment_id
        for segment in service.search(scope, name, 10)
        if segment.document.name == name
    )


def test_off_mode_keeps_exact_baseline_and_never_initializes(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _service(store, tmp_path)
    session = store.create_session()
    a = service.attach(session, "a.txt", b"alpha beta")
    b = service.attach(session, "b.txt", b"beta gamma")
    scope = _scope(session, a.attachment_id, b.attachment_id)
    before = service.search(scope, "beta", 10)
    assert service.search(scope, "beta", 10) == before
    assert service._semantic_retriever is None  # noqa: SLF001 - checks lazy contract.


def test_hybrid_fuses_dense_candidate_reuses_service_and_limits(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    baseline = _service(store, tmp_path)
    session = store.create_session()
    lexical = baseline.attach(session, "lexical.txt", b"retention calendar")
    dense = baseline.attach(session, "paraphrase.txt", "khôi phục dữ liệu".encode())
    scope = _scope(session, lexical.attachment_id, dense.attachment_id)
    dense_id = _hit(baseline, scope, "paraphrase.txt")
    scripted = ScriptedSemantic((SemanticHit(dense_id, 0.9),))
    creations = 0

    def factory() -> ScriptedSemantic:
        nonlocal creations
        creations += 1
        return scripted

    hybrid = _service(store, tmp_path, factory)
    query = "retention"
    baseline_ids = [item.segment_id for item in baseline.search(scope, query, 50)]
    expected = fuse_hybrid_ranks(baseline_ids, [dense_id], set())
    ranked = hybrid.search(scope, query, 10)
    assert [item.segment_id for item in ranked] == sorted(
        expected, key=lambda item: (-expected[item], item)
    )
    assert dense_id in {item.segment_id for item in ranked}
    assert tuple(item.score for item in ranked) == tuple(
        expected[item.segment_id] for item in ranked
    )
    assert len(hybrid.search(scope, query, 1)) == 1
    assert creations == 1
    assert scripted.calls == [(scope, query, HYBRID_CANDIDATE_DEPTH, ())] * 2


def test_exact_filename_protection_and_ties(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    baseline = _service(store, tmp_path)
    session = store.create_session()
    target = baseline.attach(session, "target.txt", b"unique answer")
    hostile = baseline.attach(session, "hostile.txt", b"other answer")
    scope = _scope(session, target.attachment_id, hostile.attachment_id)
    target_id = _hit(baseline, scope, "target.txt")
    hostile_id = _hit(baseline, scope, "hostile.txt")
    semantic = ScriptedSemantic((SemanticHit(hostile_id, 0.99), SemanticHit(target_id, 0.1)))
    hybrid = _service(store, tmp_path, lambda: semantic)
    assert hybrid.search(scope, "target.txt", 1)[0].segment_id == target_id
    tied = fuse_hybrid_ranks(("b", "a"), ("a", "b"), set())
    assert sorted(tied, key=lambda item: (-tied[item], item)) == ["a", "b"]


def test_dense_cannot_widen_scope_or_restore_deleted_documents(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    baseline = _service(store, tmp_path)
    project_a = store.create_project("A")["project_id"]
    project_b = store.create_project("B")["project_id"]
    session_a = store.create_session(project_id=project_a)
    session_b = store.create_session(project_id=project_b)
    own = baseline.attach_project(project_a, "own.txt", b"shared marker")
    foreign = baseline.attach_project(project_b, "foreign.txt", b"shared marker")
    other_session = baseline.attach(session_b, "other.txt", b"shared marker")
    deleted = baseline.attach(session_a, "deleted.txt", b"shared marker")
    scope_a = _scope(session_a, deleted.attachment_id, project=project_a)
    scope_b = _scope(session_b, other_session.attachment_id, project=project_b)
    ids = [
        _hit(baseline, scope_a, "own.txt"),
        _hit(baseline, scope_b, "foreign.txt"),
        _hit(baseline, scope_b, "other.txt"),
        _hit(baseline, scope_a, "deleted.txt"),
    ]
    baseline.delete(deleted.document.document_id, scope_a)
    scripted = ScriptedSemantic(tuple(SemanticHit(item, 1.0) for item in ids[1:]))
    hybrid = _service(store, tmp_path, lambda: scripted)
    assert {item.document.document_id for item in hybrid.search(scope_a, "shared", 10)} == {
        own.document.document_id
    }
    selected = hybrid.search(scope_a, "shared", 10, (own.document.document_id,))
    assert {item.document.document_id for item in selected} == {own.document.document_id}
    assert scripted.calls[-1] == (
        scope_a,
        "shared",
        HYBRID_CANDIDATE_DEPTH,
        (own.document.document_id,),
    )
    with pytest.raises(PermissionError):
        hybrid.search(scope_a, "shared", 10, (foreign.document.document_id,))
    assert len(scripted.calls) == 2


@pytest.mark.parametrize(
    "error",
    [LocalEmbeddingUnavailable("missing"), LocalEmbeddingUnavailable("corrupt")],
)
def test_unavailable_model_falls_back_without_caching_failure(
    store, tmp_path, error: Exception
) -> None:  # type: ignore[no-untyped-def]
    baseline = _service(store, tmp_path)
    session = store.create_session()
    upload = baseline.attach(session, "ready.txt", b"plain text")
    scope = _scope(session, upload.attachment_id)
    attempts = 0

    def factory() -> ScriptedSemantic:
        nonlocal attempts
        attempts += 1
        raise error

    hybrid = _service(store, tmp_path, factory)
    assert hybrid.search(scope, "plain", 5) == baseline.search(scope, "plain", 5)
    assert hybrid.search(scope, "plain", 5) == baseline.search(scope, "plain", 5)
    assert attempts == 2


def test_recoverable_query_error_falls_back_and_store_errors_propagate(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    baseline = _service(store, tmp_path)
    session = store.create_session()
    upload = baseline.attach(session, "ready.txt", b"plain text")
    scope = _scope(session, upload.attachment_id)
    scripted = ScriptedSemantic(error=LocalEmbeddingQueryError("inference"))
    hybrid = _service(store, tmp_path, lambda: scripted)
    assert hybrid.search(scope, "plain", 5) == baseline.search(scope, "plain", 5)
    scripted.error = sqlite3.OperationalError("broken store")
    with pytest.raises(sqlite3.OperationalError, match="broken store"):
        hybrid.search(scope, "plain", 5)
    scripted.error = TypeError("programming bug")
    with pytest.raises(TypeError, match="programming bug"):
        hybrid.search(scope, "plain", 5)


def test_missing_semantic_vectors_keep_exact_lexical_results(store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    baseline = _service(store, tmp_path)
    session = store.create_session()
    upload = baseline.attach(session, "ready.txt", b"retention period")
    scope = _scope(session, upload.attachment_id)
    hybrid = _service(store, tmp_path, lambda: ScriptedSemantic())
    assert hybrid.search(scope, "retention", 5) == baseline.search(scope, "retention", 5)
