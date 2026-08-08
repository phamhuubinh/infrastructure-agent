# Orion Project RAG Service

Standalone FastAPI service for the Web UI's document-analysis workspace. It is not imported into the Chat Agent and does not participate in chat tool selection.

## Isolation and persistence

Each project owns:

- document files under `RAG_DATA_DIR/documents/{project_id}`;
- a dense collection named `documents_{project_id}`;
- a persistent BM25 index;
- project metadata and the latest 100 analysis records.

The offline `memory` vector provider persists all collections to `RAG_DATA_DIR/vectors.json`. The root Compose stack mounts `/data` to a named volume. Project operations are serialized per project so upload, query, and delete cannot observe a partially updated index.

## Pipeline

```text
File → parser → optional OCR repair → hierarchical/semantic chunks
     → embedding → project dense collection + project BM25 index

Analysis request → dense + BM25 retrieval → RRF → reranker
                 → required project RAG LLM synthesis
```

Always-available offline providers are pypdf/text parsing, hash embeddings, the persistent memory vector store, BM25, RRF, and a no-op reranker. Optional providers include Docling/Marker/MinerU, PaddleOCR, Qwen3/BGE/OpenAI-compatible embeddings, Qdrant, BGE reranking, GraphRAG/LightRAG, HyDE, RAPTOR, and Ragas.

## Running locally

From this directory:

```bash
uv sync --group dev
RAG_DATA_DIR=/tmp/orion-rag uv run uvicorn app.main:app --reload --port 8080
uv run pytest tests -q
```

The service can boot and ingest documents before a model is configured:

```bash
RAG_EMBEDDING_PROVIDER=hash
RAG_VECTOR_STORE=memory
RAG_RERANKER=noop
```

Analysis itself always requires a model. In the root Orion stack, the backend passes the active Orion model as request-scoped internal configuration, so concurrent projects never mutate shared model state. For standalone development, environment variables may be used:

```bash
export RAG_LLM_BASE_URL=http://your-llm:8000/v1
export RAG_LLM_MODEL=your-model
export RAG_LLM_API_KEY=your-key
```

For production retrieval quality, select an OpenAI-compatible/Qwen3/BGE embedding provider and optionally Qdrant. Install only the optional dependencies needed by the selected providers; the base image intentionally stays offline-testable.

## API

```text
GET    /health
POST   /projects
GET    /projects
GET    /projects/{project_id}
DELETE /projects/{project_id}
POST   /projects/{project_id}/documents
DELETE /projects/{project_id}/documents/{doc_id}
POST   /projects/{project_id}/analyses
```

Upload uses multipart field `file` and rejects files over 50 MiB. Analysis accepts:

```json
{"query": "Compare the proposals and list risks", "top_k": 5}
```

The response includes `answer` and `retrieved`. When no model is configured, analysis returns HTTP 503 rather than a retrieval-only answer. Legacy `/ingest` and `/query` endpoints remain isolated in the built-in `default` project for older clients; Chat does not use them.

## Current limitations

- Scanned-PDF detection exists, but parser-specific PDF-page image extraction still needs to be connected before automatic OCR repair is complete.
- Graph indexes remain batch-built optional indexes; they are not updated by every upload.
- The JSON-backed local project store is appropriate for the current single-instance deployment. A multi-instance deployment would require transactional shared metadata storage and distributed locking.
