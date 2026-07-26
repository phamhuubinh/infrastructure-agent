# Task 010: RAG Subsystem Rationalization

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 10 (Sprint 3, P3 - Refactor)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

The `tool/RAGTool/app/agent/langgraph_agent.py` file embeds a LangGraph-based agent subsystem within Orion's tool layer. This creates architectural inconsistency:
1. FAR correctly states Orion should not adopt LangGraph as a core pattern.
2. Yet the RAG subsystem uses `langgraph-core` — a framework whose design philosophy contradicts Orion's.
3. The RAG subsystem has its own retry logic, agent loop, and state management — patterns Orion's ADRs intentionally reject.

The RAG *capabilities* (Qdrant vector store, BM25 sparse index, hierarchical chunking, HyDE query expansion, BGE reranker, OCR support) are genuine strengths. The issue is the *execution architecture* — LangGraph-based agent loop vs. deterministic pipeline.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/tool/RAGTool/app/agent/deterministic_rag.py` (NEW) | Reimplement RAG agent loop using deterministic pipeline patterns | ~200 lines |
| 2 | `src/tool/RAGTool/app/agent/langgraph_agent.py` | Remove or mark deprecated | ~50 lines removed |
| 3 | `pyproject.toml` | Remove `langgraph-core` dependency | ~1 line |
| 4 | `tool/RAGTool/` | Preserve vector store, BM25, chunking, HyDE, BGE reranker components | ~0 lines (no change) |

**Total estimated change:** ~250 lines (+200 new, -50 removed)

---

## 3. Detailed Instructions

### 3.1 Audit scope

**Preserve (transport-agnostic):**
- `QdrantVectorStore` — vector search
- `BM25SparseIndex` — sparse retrieval
- `HierarchicalChunker` — document chunking
- `HyDEQueryExpander` — query expansion
- `BGEReranker` — result reranking
- `OCRParser` — document parsing
- All embedding, ingestion, and fusion logic

**Remove/Replace (LangGraph-specific):**
- Agent loop (`langgraph_agent.py` line ~100-300)
- LangGraph state graph (`StateGraph`)
- Checkpoint management
- BSP execution semantics

### 3.2 `deterministic_rag.py` (NEW)

```python
class DeterministicRAGPipeline:
    """RAG retrieval using deterministic pipeline patterns — no agent loop.
    
    Replaces the LangGraph-based agent with a single-pass retrieval pipeline:
    1. Query expansion (HyDE)
    2. Parallel retrieval (vector + BM25)
    3. Fusion (RRF)
    4. Rerank (BGE)
    5. Return results
    
    No model-guided iteration, no state graph, no checkpoints.
    """
    
    def __init__(
        self,
        vector_store: QdrantVectorStore,
        sparse_index: BM25SparseIndex,
        chunker: HierarchicalChunker,
        query_expander: HyDEQueryExpander,
        reranker: BGEReranker,
    ):
        self._vector_store = vector_store
        self._sparse_index = sparse_index
        self._chunker = chunker
        self._query_expander = query_expander
        self._reranker = reranker
    
    def retrieve(self, query: str, top_k: int = 10) -> list[Document]:
        """Single-pass retrieval — deterministic, no iteration."""
        # Step 1: Expand query
        expanded_queries = self._query_expander.expand(query)
        
        # Step 2: Parallel retrieval
        vector_results = self._vector_store.search(expanded_queries, top_k=top_k)
        sparse_results = self._sparse_index.search(query, top_k=top_k)
        
        # Step 3: Fusion
        fused = self._reciprocal_rank_fusion(vector_results, sparse_results)
        
        # Step 4: Rerank
        reranked = self._reranker.rerank(query, fused)
        
        return reranked[:top_k]
```

### 3.3 Dependency removal

```toml
# pyproject.toml — remove:
# "langgraph-core>=0.2.0",  # REMOVED: replaced by deterministic RAG pipeline
```

---

## 4. Dependencies

- **Task #009** (Immutable Pipeline State) — RAG reimplementation uses new pipeline state model
- Blocks: None

---

## 5. Verification Criteria

- [ ] RAG retrieval quality maintained or improved (benchmark vs. LangGraph baseline)
- [ ] RAG retrieval latency <20% increase
- [ ] `langgraph-core` removed from `pyproject.toml`
- [ ] All existing RAG tests pass with deterministic pipeline
- [ ] No regression in OCR, chunking, embedding, or reranking
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] One atomic commit: `refactor: replace LangGraph-based RAG agent with deterministic pipeline`