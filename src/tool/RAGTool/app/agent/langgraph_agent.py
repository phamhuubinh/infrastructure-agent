"""LangGraph agent wrapping the RAG pipeline in a retrieve -> grade ->
(re-query if weak) -> generate -> reflect loop — this is what turns a
plain "retrieve then generate" pipeline into an agentic one (matches
LangGraph's "Corrective RAG" / "Self-RAG" reference patterns).

Requires `pip install langgraph langchain-core`. The graph nodes call back
into this service's own query_pipeline (retrieval/fusion/rerank) and
llm_client (grading/generation) — LangGraph only owns the control flow
(loop, branch, retry), not retrieval or generation logic itself.
"""

from __future__ import annotations

from typing import TypedDict

from app.pipeline.query_pipeline import QueryPipeline
from app.serving.llm_client import LlmClient

_GRADE_PROMPT = (
    "You are grading whether retrieved context is sufficient to answer a "
    "question. Question: {query}\n\nContext:\n{context}\n\n"
    "Reply with exactly one word: sufficient or insufficient."
)

_ANSWER_PROMPT = (
    "Answer the question using ONLY the context below. If the context is "
    "insufficient, say so explicitly rather than guessing.\n\n"
    "Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
)


class RagAgentState(TypedDict):
    query: str
    rewritten_query: str
    context_chunks: list[str]
    grade: str
    answer: str
    retries: int


class RagLangGraphAgent:
    def __init__(
        self, query_pipeline: QueryPipeline, llm_client: LlmClient, max_retries: int = 1
    ) -> None:
        self._query_pipeline = query_pipeline
        self._llm = llm_client
        self._max_retries = max_retries
        self._graph = self._build_graph()

    def _build_graph(self):
        try:
            from langgraph.graph import END, StateGraph
        except ImportError as exc:
            msg = "langgraph is not installed (`pip install langgraph langchain-core`)"
            raise RuntimeError(msg) from exc

        graph = StateGraph(RagAgentState)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("grade", self._grade_node)
        graph.add_node("rewrite", self._rewrite_node)
        graph.add_node("generate", self._generate_node)

        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "grade")
        graph.add_conditional_edges(
            "grade",
            self._should_rewrite,
            {"rewrite": "rewrite", "generate": "generate"},
        )
        graph.add_edge("rewrite", "retrieve")
        graph.add_edge("generate", END)

        return graph.compile()

    def run(self, query: str) -> RagAgentState:
        initial_state: RagAgentState = {
            "query": query,
            "rewritten_query": query,
            "context_chunks": [],
            "grade": "",
            "answer": "",
            "retries": 0,
        }
        return self._graph.invoke(initial_state)

    # -- nodes -------------------------------------------------------

    def _retrieve_node(self, state: RagAgentState) -> dict:
        results = self._query_pipeline.retrieve(state["rewritten_query"])
        return {"context_chunks": [r.text for r in results]}

    def _grade_node(self, state: RagAgentState) -> dict:
        context = "\n\n".join(state["context_chunks"])
        prompt = _GRADE_PROMPT.format(query=state["query"], context=context)
        grade = (
            self._llm.complete(prompt, temperature=0.0, max_tokens=5).strip().lower()
        )
        return {"grade": grade}

    def _should_rewrite(self, state: RagAgentState) -> str:
        if "insufficient" in state["grade"] and state["retries"] < self._max_retries:
            return "rewrite"
        return "generate"

    def _rewrite_node(self, state: RagAgentState) -> dict:
        prompt = (
            f"Rewrite this question to be more specific and retrieval-friendly, "
            f"keeping the same intent: {state['query']}"
        )
        rewritten = self._llm.complete(prompt, temperature=0.3, max_tokens=100)
        return {"rewritten_query": rewritten.strip(), "retries": state["retries"] + 1}

    def _generate_node(self, state: RagAgentState) -> dict:
        context = "\n\n".join(state["context_chunks"])
        prompt = _ANSWER_PROMPT.format(query=state["query"], context=context)
        answer = self._llm.complete(prompt, temperature=0.2, max_tokens=600)
        return {"answer": answer}
