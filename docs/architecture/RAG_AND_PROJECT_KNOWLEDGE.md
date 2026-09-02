# RAG and project knowledge

## RAG's role

RAG is a **knowledge source used by the model**, not a mandatory stage applied before every user message.

The model decides when document retrieval is useful.

Orion binds deterministic session/project scope.

## Knowledge scopes

### Session/chat source

Files attached to a chat can become retrievable in the owning session.

```text
session_source:<session_id>
```

### Project source

Files stored in a Project are persistent and retrievable only in that project scope.

```text
project_source:<project_id>
```

### Optional local/global knowledge

A deployment may maintain a local shared knowledge library. If present, it is a separate explicit source, never silently merged into project storage.

## Scope binding

The active project is resolved from Orion application state.

Preferred model-facing behavior:

```text
knowledge.search(query="retention requirement")
```

rather than:

```text
knowledge.search(project_id="some-arbitrary-project", query="...")
```

Orion passes a bound runtime scope to the tool implementation:

```text
session_id
active project_id (optional)
current attachment identities
```

The Knowledge tool then searches only sources valid for that runtime scope.

This is not semantic routing. The model still decides whether retrieval is needed and what information to retrieve.

## Active Project

Within a project conversation the model can use:

```text
session attachments
+ active project's RAG source
+ other registered tools
```

It must not receive documents from unrelated projects.

## Ingestion

Current local Knowledge ingestion accepts binary-safe multipart uploads and supports:

- UTF-8 text;
- Markdown;
- PDF;
- DOCX;
- XLSX.

The configured raw upload bound defaults to 4 MiB. Office containers additionally pass
archive-entry, expanded-size, encryption/macro, path-traversal, and compression-ratio safety
checks. PDF and spreadsheet parsing also have bounded extracted-content/page/cell safety limits.
Upload size and archive expansion limits are separate controls.

The ingestion pipeline is:

```text
file bytes
 ↓
validate upload bound and identify format
 ↓
parse text/structure
 ↓
normalize source-location units
 ↓
chunk with document/page/section metadata
 ↓
lexical/vector index
 ↓
ready (or explicit failed state)
```

PDF page numbers, DOCX heading/paragraph/table locations, and XLSX sheet/row locations are
preserved through chunks into `SourceRef` where available.

The persisted lifecycle remains explicit:

```text
uploaded → parsing → indexing → ready
                         └────→ failed
```

Current ingestion executes synchronously inside the local application request path; persisted
intermediate states and blob identity remain restart-reconcilable. A future worker may move the
same state machine off-request without changing the parser/index/source contracts.

Parser, embedding, lexical, and vector implementations are replaceable components.

A deployment does not need a specific vector database to satisfy the architecture.

## Retrieval task shapes

Retrieval must not assume "top-k vector chunks" is sufficient for every task.

### Local fact/question answering

Search relevant segments, optionally rerank, and return source metadata.

### Whole-document understanding

Use document structure, larger sections, hierarchical summaries, or iterative reads rather than only local chunk search.

### Cross-document comparison

Retrieve from multiple explicitly scoped documents and preserve document identity in results.

### Exact document reading

When the model already knows the document identity, allow deterministic read/section retrieval without semantic search.

## Hybrid retrieval

A possible implementation pipeline is:

```text
query
 ├── lexical/BM25
 └── dense/vector
        ↓
fusion
        ↓
optional rerank
        ↓
source-aware results
```

This is an implementation option, not a mandatory dependency list.

GraphRAG, RAPTOR, HyDE, and similar techniques are optional optimizations.

## Citations

A retrieved segment should preserve enough identity to support citations:

- source scope;
- project/session identity;
- document ID;
- document name;
- page/section when available;
- segment/chunk ID;
- text;
- retrieval score/rank metadata where useful.

See `CONTRACTS.md` for canonical `KnowledgeSourceRef`, `DocumentRef`, `RetrievedSegment`, and `SourceRef` concepts.

## Untrusted text

Retrieved text is data.

A document instruction such as "ignore previous rules" must not become an Orion system instruction.
