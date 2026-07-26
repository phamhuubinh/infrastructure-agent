"""DEPRECATED — use app.agent.deterministic_rag.DeterministicRAGPipeline instead.

This LangGraph-based agent loop (retrieve → grade → rewrite → generate)
has been replaced by a single-pass deterministic pipeline that matches
Orion's architecture principles: no state graph, no checkpoints, no
model-guided iteration.

The deterministic pipeline (deterministic_rag.py) delegates to
QueryPipeline for retrieval mechanics — the same retrieval/fusion/rerank
stack is preserved. Only the agent loop and LangGraph dependency are removed.

Original class implementation (RagLangGraphAgent + RagAgentState) was
removed because it depended on `langgraph.graph` which is not installed
and should never be installed in this project.

Retained here as a deprecation notice. Will be removed in a future cleanup pass.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "RagLangGraphAgent is deprecated. "
    "Use app.agent.deterministic_rag.DeterministicRAGPipeline instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Historical reference — the original LangGraph-based agent class:
#
#   class RagAgentState(TypedDict):
#       query: str
#       rewritten_query: str
#       context_chunks: list[str]
#       grade: str
#       answer: str
#       retries: int
#
#   class RagLangGraphAgent:
#       def __init__(self, query_pipeline, llm_client, max_retries=1): ...
#       def _build_graph(self):  # StateGraph with retrieve/grade/rewrite/generate nodes
#       def run(self, query): ...
#
# The full implementation is available in git history (commit e5c4d57^).
