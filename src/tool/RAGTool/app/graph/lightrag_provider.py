"""LightRAG adapter (github.com/HKUDS/LightRAG) — faster alternative to
Microsoft GraphRAG. Incremental indexing (unlike GraphRAG's batch
community-detection pipeline), so `build()` can run per-document, making
it a better fit if you need graph retrieval to stay in sync with frequent
ingestion rather than periodic batch reindexing.

Requires `pip install lightrag-hku`. Written against LightRAG's real API.
"""
from __future__ import annotations

from app.graph.base import GraphSearchResult


class LightRagProvider:
    name = "lightrag"

    def __init__(self, working_dir: str, llm_model_func=None, embedding_func=None) -> None:
        self._working_dir = working_dir
        self._llm_model_func = llm_model_func
        self._embedding_func = embedding_func
        self._rag = None

    def _get_rag(self):
        if self._rag is None:
            try:
                from lightrag import LightRAG
                from lightrag.kg.shared_storage import initialize_pipeline_status
            except ImportError as exc:
                raise RuntimeError(
                    "lightrag-hku is not installed (`pip install lightrag-hku`)"
                ) from exc

            self._rag = LightRAG(
                working_dir=self._working_dir,
                llm_model_func=self._llm_model_func,
                embedding_func=self._embedding_func,
            )
            initialize_pipeline_status()
        return self._rag

    def build(self, doc_id: str, text: str) -> None:
        rag = self._get_rag()
        rag.insert(text, ids=[doc_id])

    def search(self, query: str, top_k: int = 10) -> list[GraphSearchResult]:
        rag = self._get_rag()
        from lightrag import QueryParam

        response = rag.query(query, param=QueryParam(mode="hybrid", top_k=top_k))
        return [GraphSearchResult(text=str(response), source_ids=[], score=1.0)]
