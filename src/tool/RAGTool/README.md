# Orion Project RAG Service

This directory contains the **current standalone Project/document-analysis service** used by the Web
UI.

At implementation baseline `259f85b`, this service is not imported into the canonical Chat agent
and does not participate in Chat capability selection.

That current separation is **not** the accepted target architecture. ADR-0003 and
`docs/architecture/PROJECTS_RAG_MEMORY.md` define Project knowledge as a normal READ capability in
the same agent loop. The retrieval implementation here may remain useful as the backend for that
future capability; do not create a second semantic agent architecture around it.

## Isolation and persistence

Each project owns:

- document files under `RAG_DATA_DIR/documents/{project_id}`;
- a dense collection named `documents_{project_id}`;
- a persistent, Vietnamese-accent-folded BM25 index;
- project metadata and the latest 100 analysis records.

The offline `memory` vector provider persists collections to `RAG_DATA_DIR/vectors.json`. The root
Compose stack mounts `/data` to a named volume. Project operations are serialized per project so
upload/query/delete cannot observe a partially updated index.

## Pipeline

```text
File → parser → hierarchical/semantic chunks
     → embedding → project dense collection + project BM25 index

Analysis request → original-query BM25 + bounded same-model lexical variants
                 → rank-based RRF → deterministic/no-op reranker
                 → document-balanced context → required RAG LLM synthesis
```

The root Compose configuration uses pypdf/text parsing, hash embeddings, the persistent memory vector
store, BM25, RRF, a no-op reranker, and a no-op OCR provider.

Hash embeddings are deterministic development plumbing, not semantic retrieval, so hash dense
rankings are excluded from fusion. A configured semantic embedding provider may contribute a bounded
dense ranking alongside BM25.

The request-scoped analysis model makes at most one lexical-expansion call before final synthesis;
expansion failure falls back to original-query BM25 only.

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

Analysis itself requires a model. In the root Orion stack, the backend passes the active Orion model
as request-scoped internal configuration so concurrent projects do not mutate shared model state.

For standalone development:

```bash
export RAG_LLM_BASE_URL=http://your-llm:8000/v1
export RAG_LLM_MODEL=your-model
export RAG_LLM_API_KEY=your-key
```

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

Upload uses multipart field `file` and rejects files over 50 MiB.

Analysis accepts:

```json
{"query": "Compare the proposals and list risks", "top_k": 5}
```

The response includes `answer` and `retrieved`. Without a configured model, analysis returns HTTP
503 rather than a retrieval-only answer.

Legacy `/ingest` and `/query` endpoints remain isolated in the built-in `default` project for older
clients. Canonical Chat does not use them.

## Migration boundary

When Project knowledge is integrated into the canonical agent, preserve these rules:

- Project/document isolation remains deterministic authority.
- Retrieval results are bounded evidence, not execution authority.
- The model decides when Project retrieval is useful.
- The Chat agent should call a registered READ capability rather than bypassing the capability/
  validation boundary.
- Do not keep a separate RAG semantic mode once the canonical capability is wired.
