# Knowledge / RAG tool

## Purpose

Give the model searchable/readable access to document knowledge without injecting every document into every prompt.

## Sources

Target source scopes:

- current/session attachments;
- active Project source;
- optional local/shared knowledge source.

## Scope ownership

The model chooses **when retrieval is useful** and **what to retrieve**.

Orion owns the actual session/project scope.

Preferred model-facing operation:

```text
knowledge.search(query="retention requirement")
```

Orion supplies:

```text
RuntimeScope(
  session_id=...,
  project_id=<active project or null>,
  attachment_ids=...,
)
```

to the Knowledge implementation.

Ordinary knowledge calls should not allow the model to escape an active Project by inventing an arbitrary project identity.

## Operations

Exact public names may follow implementation, but the tool family needs equivalent operations for:

```text
list documents/sources visible in current runtime scope
search scoped knowledge
read exact document/section in scope
retrieve source metadata
```

## Project behavior

In a Project, the Project source is automatically bound to the runtime.

The user does not enable "RAG mode" and the model does not manually select Project A vs Project B.

## Retrieval quality

The implementation may combine:

- parsing;
- semantic/hierarchical chunking;
- dense embeddings;
- vector retrieval;
- BM25;
- reciprocal-rank fusion;
- reranking;
- exact document reads;
- hierarchical/iterative whole-document reading.

Advanced GraphRAG/RAPTOR/HyDE are optional.

## Result metadata

Return source-aware `ToolResult` data preserving:

```text
source identity
document identity
page/section when available
segment/chunk identity
text
ranking metadata where useful
```

This metadata allows final answers to cite the material.

See `../architecture/CONTRACTS.md` for canonical source/document/retrieval contracts.
