# Knowledge / RAG tool

## Purpose

Give the model searchable/readable access to document knowledge without injecting every document into every prompt.

## Sources

Target source scopes:

- current/session attachments;
- active Project source;
- optional local/shared knowledge source.

## Operations

Exact names may follow implementation, but the tool family needs equivalent operations for:

```text
list documents/sources
search scoped knowledge
read exact document/section
retrieve source metadata
```

## Project behavior

In a Project, the Project source is automatically available to the model. The user does not enable "RAG mode".

## Retrieval quality

The implementation may combine:

- parsing;
- semantic/hierarchical chunking;
- dense embeddings;
- vector retrieval;
- BM25;
- reciprocal-rank fusion;
- reranking;
- exact document reads.

Advanced GraphRAG/RAPTOR/HyDE are optional.

## Result metadata

Preserve source/document/page/section identity so the final answer can cite the material.
