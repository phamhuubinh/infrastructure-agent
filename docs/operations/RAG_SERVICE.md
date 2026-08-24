# RAG service

## Current repository

The repository contains a dedicated RAG service under `src/tool/RAGTool` and local Qdrant integration.

The implementation includes components for:

- document parsers;
- OCR providers;
- semantic/hierarchical chunking;
- embeddings;
- BM25;
- vector storage;
- fusion;
- reranking;
- optional graph/RAPTOR-style components;
- ingestion/query pipelines;
- project storage/recovery.

## Target role

The RAG service is a knowledge backend used by the model through Orion tools.

It is **not** an always-on preprocessor for every chat prompt.

## Health

Use:

```bash
docker compose ps
docker compose logs -f rag
docker compose logs -f qdrant
```

## Failure diagnosis

If upload succeeds but retrieval fails, inspect:

```text
parser
→ chunker
→ embedding endpoint
→ Qdrant/vector write
→ BM25/index write
→ project/source metadata
→ query pipeline
```

Do not mark documents ready until all required indexing steps for the selected retrieval mode complete successfully.
