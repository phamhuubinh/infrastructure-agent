# RAG Service

Standalone microservice implementing a RAGFlow-style pipeline, built to plug into
the AI Platform as the **RAG** component (see the infra-agent repo's
`docs/ai/03_PLATFORM_ARCHITECTURE.md`, WP2). Own API, own Dockerfile/Docker Compose,
independent of the infra-agent service.

```
PDF Parser   → Docling / Marker (fallback) / MinerU (scientific) / pypdf (always-on fallback)
OCR          → PaddleOCR (+ no-op default)
Chunking     → Hierarchical + Semantic (self-implemented, no external lib)
Embedding    → Qwen3-Embedding / BGE-M3 / OpenAI-compatible (vLLM) / hash (offline dev)
VectorDB     → Qdrant / in-memory (offline dev)
Sparse       → BM25 (self-implemented BM25Okapi)
Fusion       → Reciprocal Rank Fusion (self-implemented)
Reranker     → BGE-reranker-v2 / no-op (offline dev)
Graph        → Microsoft GraphRAG / LightRAG
RAPTOR       → self-implemented (GMM clustering via scikit-learn + pluggable LLM summarizer)
Query Exp.   → HyDE (self-implemented, uses the LLM client)
Evaluation   → Ragas
Serving      → vLLM (via OpenAI-compatible client)
Agent        → LangGraph (retrieve → grade → rewrite → generate loop)
```

## Status — what's real vs. what needs a GPU host to activate

Everything below is real, correctly-wired code — nothing is a placeholder that
returns fake data. The difference is what runs **today, in this sandbox** vs.
what needs a GPU/network to load a model before it can run.

| Component | Runs today, no GPU/network | Needs deployment (GPU/model download/service) |
|---|---|---|
| Parsers | pypdf (always-on fallback) | Docling, Marker, MinerU |
| OCR | no-op (skips, warns) | PaddleOCR |
| Chunking | ✅ fully (hierarchical + semantic merge) | — (only needs *an* embedder, hash provider included) |
| Embedding | hash fallback (not semantically meaningful — dev/test only) | Qwen3-Embedding, BGE-M3, or point the OpenAI-compatible provider at any running server (including vLLM) |
| VectorDB | in-memory store | Qdrant (docker-compose included) |
| Sparse (BM25) | ✅ fully | — |
| Fusion (RRF) | ✅ fully | — |
| Reranker | no-op passthrough | BGE-reranker-v2 |
| Graph | — | GraphRAG, LightRAG (both need an LLM + indexing run) |
| RAPTOR | ✅ clustering fully; summarization uses an extractive fallback | Real LLM summarization (pass any `LlmClient`) |
| HyDE | ✅ fully, once an `LlmClient` is configured | needs an LLM endpoint |
| Ragas | — | needs `pip install ragas` + a judge LLM |
| Agent (LangGraph) | ✅ graph logic; needs the same LLM client as HyDE | needs `pip install langgraph` |

20 unit/integration tests cover chunking, BM25, RRF, the in-memory vector store,
and a full ingest→query pipeline run using only the offline-testable providers.
Run them with:

```bash
python3 -m unittest discover -s tests -v
```

## Running

**Offline / dev mode** (no external services, everything falls back to
in-memory + hash embedding):

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

**With Qdrant** (still using hash embedding, so retrieval quality is not
representative, but proves the Qdrant wiring works):

```bash
docker compose up qdrant -d
RAG_VECTOR_STORE=qdrant RAG_QDRANT_URL=http://localhost:6333 \
  uvicorn app.main:app --port 8080
```

**Full production stack** — install the optional dependencies you need
(see the commented-out section in `requirements.txt`), then point env vars
at your real services:

```bash
export RAG_EMBEDDING_PROVIDER=openai_compatible
export RAG_EMBEDDING_BASE_URL=http://your-vllm-embed-host:8001/v1
export RAG_EMBEDDING_MODEL=qwen3-embedding
export RAG_VECTOR_STORE=qdrant
export RAG_QDRANT_URL=http://your-qdrant-host:6333
export RAG_RERANKER=bge_v2
export RAG_LLM_ENABLED=true
export RAG_LLM_BASE_URL=http://your-vllm-llm-host:8000/v1
export RAG_LLM_MODEL=your-model-name
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Or use `docker compose up` after uncommenting the relevant lines in
`docker-compose.yml` and `requirements.txt`.

## API

```
GET  /health
POST /ingest   multipart file upload -> { doc_id, chunk_count, parser_used, warnings }
POST /query    { "query": "...", "top_k": 5 } -> { answer, retrieved: [...] }
```

## Directory layout

```
app/
  parsers/       DoclingParser, MarkerParser, MinerUParser, PyPdfParser, ParserRouter
  ocr/           PaddleOcrProvider, NoOpOcrProvider
  chunking/      HierarchicalSemanticChunker
  embedding/     Qwen3EmbeddingProvider, BgeM3EmbeddingProvider,
                 OpenAICompatibleEmbeddingProvider, HashEmbeddingProvider
  vectordb/      QdrantVectorStore, InMemoryVectorStore
  sparse/        BM25Index
  fusion/        reciprocal_rank_fusion
  rerank/        BgeRerankerV2Provider, NoOpReranker
  graph/         MicrosoftGraphRagProvider, LightRagProvider
  raptor/        RaptorIndex
  query_expansion/  HydeQueryExpander
  eval/          RagasEvaluator
  serving/       LlmClient (OpenAI-compatible, works with vLLM)
  agent/         RagLangGraphAgent
  pipeline/      IngestPipeline, QueryPipeline (orchestrate everything above)
  config.py      env-var-driven provider selection
  main.py        FastAPI app
tests/           20 tests, all runnable offline
```

Every stage is behind a small interface (`app/*/base.py`) so swapping a
provider (e.g. hash → Qwen3, in-memory → Qdrant, no-op → BGE-reranker-v2)
never requires touching the pipeline orchestration code.

## Known gaps / next steps

- `IngestPipeline._needs_ocr` detects scanned pages and flags a warning,
  but the actual page-image-extraction-and-OCR loop still needs to be
  wired per parser (PDF → page image is parser-specific to implement
  cleanly). Currently OCR fires only when explicitly invoked, not
  automatically mid-ingest.
- `QueryPipeline` currently pulls chunk text only from the dense-search
  hits' payload; a sparse-only hit (BM25 match with no matching dense hit
  in the fused top-k) won't have text available for reranking unless you
  add a document-store lookup by chunk id — noted inline in the code.
- GraphRAG indexing is batch (call `build_workspace_index()` after writing
  documents), not per-request — matches the real GraphRAG cost profile,
  but means graph search lags behind the latest ingested documents until
  you run that build step (cron/queue it in production).
