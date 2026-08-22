"""Code-first Project RAG retrieval and bounded same-model synthesis."""

from __future__ import annotations

from dataclasses import dataclass

from app.embedding.base import EmbeddingProvider
from app.fusion.rrf import FusedResult, reciprocal_rank_fusion
from app.graph.base import GraphIndex
from app.query_expansion.hyde import HydeQueryExpander
from app.query_expansion.lexical import LexicalQueryExpander
from app.rerank.base import RerankedResult, Reranker
from app.serving.llm_client import LlmClient
from app.sparse.bm25_index import BM25Index
from app.vectordb.base import VectorStore

_ANSWER_PROMPT = (
    "Answer the question using ONLY the context below. Cite which context "
    "snippet(s) you used by number. If the context is insufficient, say so.\n\n"
    "{context}\n\nQuestion: {query}\n\nAnswer:"
)


@dataclass
class RetrievedChunk:
    id: str
    text: str
    score: float
    payload: dict


@dataclass
class QueryResult:
    answer: str
    retrieved: list[RetrievedChunk]


class QueryPipeline:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        reranker: Reranker,
        llm_client: LlmClient | None = None,
        hyde: HydeQueryExpander | None = None,
        graph_index: GraphIndex | None = None,
        collection: str = "documents",
        dense_top_k: int = 30,
        sparse_top_k: int = 30,
        fusion_top_k: int = 15,
        final_top_k: int = 5,
        lexical_expander: LexicalQueryExpander | None = None,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._bm25 = bm25_index
        self._reranker = reranker
        self._llm = llm_client
        self._hyde = hyde
        self._graph = graph_index
        self._collection = collection
        self._dense_top_k = dense_top_k
        self._sparse_top_k = sparse_top_k
        self._fusion_top_k = fusion_top_k
        self._final_top_k = final_top_k
        self._lexical_expander = lexical_expander or (
            LexicalQueryExpander(llm_client) if llm_client is not None else None
        )

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        queries = [query]
        if self._lexical_expander is not None:
            queries.extend(self._lexical_expander.expand(query))

        rankings: dict[str, list[str]] = {}
        payload_by_id: dict[str, dict] = {}
        text_by_id: dict[str, str] = {}
        for position, search_query in enumerate(queries):
            hits = self._bm25.search(search_query, top_k=self._sparse_top_k)
            ranking_name = (
                "bm25:original" if position == 0 else f"bm25:variant:{position}"
            )
            rankings[ranking_name] = [hit.id for hit in hits]
            for hit in hits:
                payload_by_id.setdefault(hit.id, hit.payload)
                text_by_id.setdefault(hit.id, hit.text)

        if self._uses_semantic_embedding():
            query_vector = (
                self._hyde.expand_to_embedding(query)
                if self._hyde is not None
                else self._embedder.embed_query(query)
            )
            dense_hits = self._vector_store.search(
                self._collection, query_vector, top_k=self._dense_top_k
            )
            rankings["dense"] = [hit.id for hit in dense_hits]
            for hit in dense_hits:
                payload_by_id.setdefault(hit.id, hit.payload)
                text_by_id.setdefault(hit.id, str(hit.payload.get("text", "")))

        fused = self._bounded_fused_with_original(reciprocal_rank_fusion(rankings))
        candidates = [
            (result.id, text_by_id[result.id])
            for result in fused
            if text_by_id.get(result.id)
        ]
        reranked = self._reranker.rerank(
            query, candidates, top_k=min(self._fusion_top_k, len(candidates))
        )
        results = self._document_balanced(reranked, payload_by_id)

        if self._graph is not None and len(results) < self._final_top_k:
            for graph_hit in self._graph.search(
                query, top_k=self._final_top_k - len(results)
            ):
                results.append(
                    RetrievedChunk(
                        id="graph:" + graph_hit.text[:16],
                        text=graph_hit.text,
                        score=graph_hit.score,
                        payload={"source": "graph"},
                    )
                )
                if len(results) == self._final_top_k:
                    break
        return results

    def _uses_semantic_embedding(self) -> bool:
        """Hash n-grams are not a semantic retrieval source and stay out of RRF."""
        return bool(getattr(self._embedder, "is_semantic", True))

    def _bounded_fused_with_original(
        self, fused: list[FusedResult]
    ) -> list[FusedResult]:
        selected = fused[: self._fusion_top_k]
        if not selected or any("bm25:original" in item.sources for item in selected):
            return selected
        original = next(
            (item for item in fused if "bm25:original" in item.sources), None
        )
        if original is None:
            return selected
        selected = selected[:-1] + [original]
        return sorted(selected, key=lambda item: (-item.score, item.id))

    def _document_balanced(
        self, reranked: list[RerankedResult], payload_by_id: dict[str, dict]
    ) -> list[RetrievedChunk]:
        """Cover retrieved documents once before accepting repeat chunks."""
        selected: list[RerankedResult] = []
        selected_ids: set[str] = set()
        seen_documents: set[str] = set()
        for result in reranked:
            doc_id = payload_by_id.get(result.id, {}).get("doc_id")
            if not isinstance(doc_id, str) or not doc_id or doc_id in seen_documents:
                continue
            selected.append(result)
            selected_ids.add(result.id)
            seen_documents.add(doc_id)
            if len(selected) == self._final_top_k:
                return self._to_chunks(selected, payload_by_id)
        for result in reranked:
            if result.id not in selected_ids:
                selected.append(result)
                selected_ids.add(result.id)
            if len(selected) == self._final_top_k:
                break
        return self._to_chunks(selected, payload_by_id)

    @staticmethod
    def _to_chunks(
        results: list[RerankedResult], payload_by_id: dict[str, dict]
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                id=result.id,
                text=result.text,
                score=result.score,
                payload=payload_by_id.get(result.id, {}),
            )
            for result in results
        ]

    def answer(self, query: str) -> QueryResult:
        retrieved = self.retrieve(query)
        if self._llm is None:
            raise RuntimeError(
                "No analysis model configured. Configure and test a model before running RAG analysis."
            )
        context = "\n\n".join(
            f"[{i + 1}] {chunk.text}" for i, chunk in enumerate(retrieved)
        )
        prompt = _ANSWER_PROMPT.format(context=context, query=query)
        answer_text = self._llm.complete(prompt, temperature=0.2, max_tokens=700)
        return QueryResult(answer=answer_text, retrieved=retrieved)
