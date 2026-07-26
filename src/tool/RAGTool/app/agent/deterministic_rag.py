"""Deterministic RAG pipeline — single-pass retrieval without agent loop.

Replaces the LangGraph-based agent (langgraph_agent.py) with a
deterministic pipeline that matches Orion's architecture principles:
no state graph, no checkpoints, no model-guided iteration.

Pipeline stages:
    1. Query expansion (HyDE, optional)
    2. Parallel retrieval (dense vector + BM25 sparse)
    3. Fusion (Reciprocal Rank Fusion)
    4. Rerank (BGE or no-op)
    5. Return results (optionally generate answer via LLM)

This class delegates to QueryPipeline for the actual retrieval mechanics
and exists as a standalone entry point for callers that want the full
pipeline without depending on langgraph.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.query_pipeline import QueryPipeline, QueryResult, RetrievedChunk


@dataclass
class RAGResult:
    """Output from a deterministic RAG retrieval."""

    answer: str
    chunks: list[RetrievedChunk]
    retrieval_only: bool = False


class DeterministicRAGPipeline:
    """RAG retrieval using deterministic pipeline patterns — no agent loop.

    Replaces the LangGraph-based agent with a single-pass retrieval pipeline.
    No model-guided iteration, no state graph, no checkpoints.
    """

    def __init__(self, query_pipeline: QueryPipeline) -> None:
        self._query_pipeline = query_pipeline

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Single-pass retrieval — deterministic, no iteration.

        Args:
            query: The user's natural-language query.
            top_k: Maximum chunks to return (uses pipeline default if None).

        Returns:
            Ranked list of retrieved chunks with scores and payloads.
        """
        results = self._query_pipeline.retrieve(query)
        if top_k is not None:
            results = results[:top_k]
        return results

    def answer(self, query: str, top_k: int | None = None) -> RAGResult:
        """Retrieve + optionally generate an answer.

        If QueryPipeline has no LLM client configured, returns
        retrieval-only results.
        """
        result: QueryResult = self._query_pipeline.answer(query)
        chunks = result.retrieved
        if top_k is not None:
            chunks = chunks[:top_k]
        return RAGResult(
            answer=result.answer,
            chunks=chunks,
            retrieval_only="no LLM client configured" in result.answer,
        )
