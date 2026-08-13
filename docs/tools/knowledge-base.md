# Project RAG Analysis

RAG is a dedicated Web UI application flow for analyzing user-uploaded documents. It is not a Chat Child Tool and is not registered behind `KnowledgeTool`.

## Isolation model

- A RAG project owns its document files, dense-vector collection, BM25 index, and latest 100 analyses.
- Retrieval always uses the selected project's collection and index.
- Deleting a document removes its dense and sparse chunks; deleting a project removes its complete corpus.
- Chat sessions separately own their Agent, conversation store, evidence cache, and execution lock.
- Chat routing has no RAG capability or RAG child tool.

## Web UI flow

Open **Phân tích tài liệu** (`/knowledge`):

1. Create a project.
2. Upload PDF, TXT, Markdown, CSV, JSON, YAML, or log files (maximum 50 MiB each).
3. Enter an analysis request.
4. Review the answer, retrieved snippets, and project analysis history.

RAG analysis always synthesizes an answer with Orion's active model. There is no retrieval-only response mode. Without a configured model, project creation and document upload still work, but starting an analysis returns a setup-required error. Configure and test a model in **Cài đặt** first.

## Service boundary

The browser talks only to the FastAPI backend:

```text
Browser → /api/rag/* → backend proxy → internal rag-service:8080
```

The root Docker Compose stack does not publish the RAG port to the host. API-key middleware protects `/api/rag/*` whenever `ORION_API_KEY` is configured.

## Configuration

```bash
RAG_DATA_DIR=/data
RAG_EMBEDDING_PROVIDER=hash
RAG_VECTOR_STORE=memory
RAG_RERANKER=noop
```

The backend supplies Orion's active model as request-scoped internal data for each analysis. It is never stored as shared mutable state in the RAG service, so concurrent projects cannot switch one another's model client. The packaged `memory` vector provider is process-local and persists to `RAG_DATA_DIR/vectors.json`.

## Active API

- `GET /api/rag/health`
- `POST /api/rag/projects`
- `GET /api/rag/projects`
- `GET /api/rag/projects/{project_id}`
- `DELETE /api/rag/projects/{project_id}`
- `POST /api/rag/projects/{project_id}/documents` (multipart field `file`)
- `DELETE /api/rag/projects/{project_id}/documents/{doc_id}`
- `POST /api/rag/projects/{project_id}/analyses`

`/api/knowledge/health` and `/api/knowledge/query` remain compatibility aliases for older clients. They use the isolated built-in `default` project and are not called by Chat.
