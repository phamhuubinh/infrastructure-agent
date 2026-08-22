from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.embedding.hash_provider import HashEmbeddingProvider
from app.pipeline.query_pipeline import QueryPipeline
from app.query_expansion.lexical import (
    MAX_ADDITIONAL_VARIANTS,
    MAX_VARIANT_CHARS,
    LexicalQueryExpander,
)
from app.rerank.noop_reranker import NoOpReranker
from app.sparse.bm25_index import BM25Index
from app.vectordb.base import VectorRecord
from app.vectordb.memory_store import InMemoryVectorStore


class _ScriptedLlm:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, float, int]] = []

    def complete(self, prompt: str, temperature: float = 0.2, max_tokens: int = 512):
        self.calls.append((prompt, temperature, max_tokens))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _RecordingBm25(BM25Index):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    def search(self, query: str, top_k: int = 10):
        self.queries.append(query)
        return super().search(query, top_k)


def _pipeline(index: BM25Index, llm=None, final_top_k: int = 5, vector_store=None):
    return QueryPipeline(
        embedder=HashEmbeddingProvider(dimension=16),
        vector_store=vector_store or InMemoryVectorStore(),
        bm25_index=index,
        reranker=NoOpReranker(),
        llm_client=llm,
        collection="project-only",
        fusion_top_k=10,
        final_top_k=final_top_k,
    )


def test_same_model_expansion_retrieves_english_only_chunk_and_keeps_original_query() -> None:
    index = _RecordingBm25()
    index.add("vi", "Máy chủ Dell R750", {"doc_id": "vi"})
    index.add("en", "Dell server maintenance guide", {"doc_id": "en"})
    llm = _ScriptedLlm([json.dumps(["Dell server", "Dell PowerEdge"]), "answer"])

    result = _pipeline(index, llm=llm).answer("máy chủ Dell")

    assert index.queries[0] == "máy chủ Dell"
    assert "Dell server" in index.queries
    assert {chunk.id for chunk in result.retrieved} >= {"vi", "en"}
    assert len(llm.calls) == 2
    assert llm.calls[0][1:] == (0.0, 96)
    assert llm.calls[1][1:] == (0.2, 700)


def test_lexical_expansion_is_bounded_deduplicated_and_fail_closed() -> None:
    duplicate_llm = _ScriptedLlm(
        [json.dumps(["MAY CHU DELL", "Dell server", "dell server"])]
    )
    assert LexicalQueryExpander(duplicate_llm).expand("máy chủ Dell") == ["Dell server"]

    too_many_llm = _ScriptedLlm([json.dumps(["one", "two", "three", "four"])])
    assert LexicalQueryExpander(too_many_llm).expand("query") == []

    too_long_llm = _ScriptedLlm([json.dumps(["x" * (MAX_VARIANT_CHARS + 1)])])
    assert LexicalQueryExpander(too_long_llm).expand("query") == []

    malformed_llm = _ScriptedLlm(["- not JSON"])
    assert LexicalQueryExpander(malformed_llm).expand("query") == []

    failing_llm = _ScriptedLlm([RuntimeError("offline")])
    assert LexicalQueryExpander(failing_llm).expand("query") == []
    assert len(failing_llm.calls) == 1
    assert MAX_ADDITIONAL_VARIANTS == 3


def test_expansion_exception_uses_only_the_original_query_without_retry() -> None:
    index = _RecordingBm25()
    index.add("original", "original evidence", {"doc_id": "one"})
    llm = _ScriptedLlm([RuntimeError("offline")])

    retrieved = _pipeline(index, llm=llm).retrieve("original")

    assert [chunk.id for chunk in retrieved] == ["original"]
    assert index.queries == ["original"]
    assert len(llm.calls) == 1


def test_hash_fallback_is_not_a_dense_or_semantic_ranking_source() -> None:
    index = BM25Index()
    index.add("matching", "lexical evidence", {"doc_id": "one"})
    vector_store = MagicMock()

    retrieved = _pipeline(index, vector_store=vector_store).retrieve("lexical")

    assert [chunk.id for chunk in retrieved] == ["matching"]
    vector_store.search.assert_not_called()


def test_document_balancing_covers_retrieved_documents_without_injecting_irrelevant() -> None:
    index = BM25Index()
    index.add("a-1", "server server server", {"doc_id": "a"})
    index.add("a-2", "server server", {"doc_id": "a"})
    index.add("b-1", "server", {"doc_id": "b"})
    index.add("irrelevant", "unrelated database", {"doc_id": "c"})

    retrieved = _pipeline(index, final_top_k=2).retrieve("server")

    assert [chunk.id for chunk in retrieved] == ["a-1", "b-1"]
    assert {chunk.payload["doc_id"] for chunk in retrieved} == {"a", "b"}
    assert all(chunk.id != "irrelevant" for chunk in retrieved)


def test_project_delete_removes_bm25_persistence_and_dense_state(
    tmp_path, monkeypatch
) -> None:
    import app.main as rag_main
    from app.project_store import ProjectNotFoundError, ProjectStore

    projects = ProjectStore(tmp_path)
    project = projects.create("Delete lifecycle")
    project_id = project["id"]
    chunk_id = "chunk-1"
    projects.add_document(
        project_id,
        {"id": "doc-1", "chunk_ids": [chunk_id]},
    )

    vector_store = InMemoryVectorStore()
    monkeypatch.setattr(rag_main, "_data_dir", tmp_path)
    monkeypatch.setattr(rag_main, "_projects", projects)
    monkeypatch.setattr(rag_main, "_vector_store", vector_store)
    monkeypatch.setattr(rag_main, "_bm25_indexes", {})
    monkeypatch.setattr(rag_main, "_project_locks", {})

    collection = rag_main._collection(project_id)
    vector_store.upsert(
        collection,
        [
            VectorRecord(
                chunk_id,
                [1.0, 0.0],
                {"doc_id": "doc-1", "text": "Máy chủ Dell"},
            )
        ],
    )

    index = rag_main._bm25(project_id)
    index.add(chunk_id, "Máy chủ Dell", {"doc_id": "doc-1"})
    persist_path = tmp_path / "bm25" / f"{project_id}.json"
    assert persist_path.exists()

    result = rag_main.delete_project(project_id)

    assert result["status"] == "deleted"
    assert not persist_path.exists()
    assert vector_store.search(collection, [1.0, 0.0]) == []
    assert project_id not in rag_main._bm25_indexes

    try:
        projects.get(project_id)
    except ProjectNotFoundError:
        pass
    else:
        raise AssertionError("deleted project still exists")



def test_expansion_cannot_cross_project_indexes_and_delete_removes_both_states() -> None:
    project_a = BM25Index()
    project_b = BM25Index()
    project_a.add("a", "alpha confidential", {"doc_id": "a"})
    project_b.add("b", "beta public", {"doc_id": "b"})
    llm = _ScriptedLlm([json.dumps(["alpha confidential"])])

    retrieved = _pipeline(project_b, llm=llm).retrieve("beta")
    assert [chunk.id for chunk in retrieved] == ["b"]
    assert project_b.search("alpha confidential") == []

    vector_store = InMemoryVectorStore()
    vector_store.upsert(
        "project-only",
        [VectorRecord("a", [1.0, 0.0], {"doc_id": "a", "text": "alpha confidential"})],
    )
    project_a.delete("a")
    vector_store.delete("project-only", ["a"])
    assert project_a.search("alpha confidential") == []
    assert vector_store.search("project-only", [1.0, 0.0]) == []
