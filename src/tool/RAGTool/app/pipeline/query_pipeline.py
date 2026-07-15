"""Query pipeline: (optional HyDE) -> dense search + BM25 search in
parallel -> RRF fusion -> rerank top candidates -> (optional graph search
merged in) -> generate answer. Every stage is a pluggable provider, same
principle as the ingest pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.embedding.base import EmbeddingProvider
from app.fusion.rrf import reciprocal_rank_fusion
from app.graph.base import GraphIndex
from app.query_expansion.hyde import HydeQueryExpander
from app.rerank.base import Reranker
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

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        query_vector = (
            self._hyde.expand_to_embedding(query) if self._hyde else self._embedder.embed_query(query)
        )

        dense_hits = self._vector_store.search(self._collection, query_vector, top_k=self._dense_top_k)
        sparse_hits = self._bm25.search(query, top_k=self._sparse_top_k)

        payload_by_id = {h.id: h.payload for h in dense_hits}
        text_by_id = {h.id: h.payload.get("text", "") for h in dense_hits}

        fused = reciprocal_rank_fusion(
            rankings={
                "dense": [h.id for h in dense_hits],
                "sparse": [h.id for h in sparse_hits],
            },
            top_k=self._fusion_top_k,
        )

        # sparse-only hits won't have text/payload from the dense search —
        # in production, fetch their text/payload from the vector store or
        # a document store by id; omitted here for brevity in this scaffold.
        candidates = [(f.id, text_by_id.get(f.id, "")) for f in fused if text_by_id.get(f.id)]

        reranked = self._reranker.rerank(query, candidates, top_k=self._final_top_k)

        results = [
            RetrievedChunk(
                id=r.id, text=r.text, score=r.score, payload=payload_by_id.get(r.id, {})
            )
            for r in reranked
        ]

        if self._graph is not None:
            graph_hits = self._graph.search(query, top_k=3)
            for gh in graph_hits:
                results.append(
                    RetrievedChunk(id="graph:" + gh.text[:16], text=gh.text, score=gh.score, payload={"source": "graph"})
                )

        return results

    def answer(self, query: str) -> QueryResult:
        retrieved = self.retrieve(query)
        if self._llm is None:
            return QueryResult(answer="[no LLM client configured — retrieval-only mode]", retrieved=retrieved)

        context = "\n\n".join(f"[{i+1}] {c.text}" for i, c in enumerate(retrieved))
        prompt = _ANSWER_PROMPT.format(context=context, query=query)
        answer_text = self._llm.complete(prompt, temperature=0.2, max_tokens=700)
        return QueryResult(answer=answer_text, retrieved=retrieved)
