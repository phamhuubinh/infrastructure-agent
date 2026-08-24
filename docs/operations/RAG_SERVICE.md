# RAG service

## Current repository packaging

The current Compose deployment runs a dedicated service named:

```text
rag-service
```

from the build context:

```text
src/tool/RAGTool
```

Its container-local health endpoint is served on port `8080`.

## Current Compose configuration

At the time of this documentation revision, Compose configures:

```text
RAG_EMBEDDING_PROVIDER=hash
RAG_VECTOR_STORE=memory
RAG_RERANKER=noop
RAG_OCR_PROVIDER=noop
RAG_DATA_DIR=/data
```

The service uses the persistent volume:

```text
orion-ragdata:/data
```

There is no Qdrant container in the current Compose stack.

Do not use `docker compose logs -f qdrant` unless Qdrant is actually added to the deployment.

## Target architectural role

The RAG service is a knowledge backend used through Orion's model-driven tool system.

It is **not** an always-on preprocessor that searches documents before every model request.

Project conversations add a project-scoped knowledge source to the same Chat runtime.

## Retrieval implementation

The codebase may contain components or experiments for multiple retrieval techniques/backends, such as:

- parsers;
- OCR providers;
- semantic/hierarchical chunking;
- embeddings;
- lexical/BM25 retrieval;
- vector retrieval;
- fusion;
- reranking;
- graph/RAPTOR-style components.

The presence of an implementation module does not mean the current Docker deployment runs every backend.

## Health and logs

```bash
docker compose ps
docker compose logs -f rag-service
```

To inspect API/RAG interaction:

```bash
docker compose logs -f api rag-service
```

## Failure diagnosis

For document ingestion/retrieval failures, inspect the configured pipeline rather than assuming a specific vector database:

```text
upload/source scope
→ parser
→ normalization/chunking
→ configured embedding implementation
→ configured lexical/vector index
→ persisted document/source metadata
→ query/retrieval pipeline
→ ToolResult/citation metadata
```

Do not mark a document `ready` until every indexing step required by the active retrieval configuration has completed successfully.

## Project scope

Project isolation is an Orion runtime invariant.

The active `project_id` is bound from application/session state and passed to the knowledge backend through runtime scope. The model chooses the query, not an arbitrary project scope.

See:

- `../architecture/RAG_AND_PROJECT_KNOWLEDGE.md`
- `../architecture/CONTRACTS.md`
