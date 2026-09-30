# RAG and project knowledge

## RAG's role

RAG is a **knowledge source used by the model**, not a mandatory stage applied before every user message.

When an answer depends on session or Project document contents, current document evidence must be
retrieved before synthesis. For discovery across Project or session knowledge, or when no exact
document identity is visible, `knowledge.search` is the default retrieval step.
Orion exposes bounded ready-document names, media types, and status for the active Project in model
context. A user-visible Project filename or title is resolved through `knowledge.search`, which
returns the exact `document_id` and citable evidence. Session attachments and Project documents
are Orion knowledge, never Linux paths or infrastructure targets. `linux.file.*` requires an
explicit path on a configured Linux target.

When a current-session attachment exposes an exact `document_id` and the task clearly targets that
attachment, `knowledge.read` may retrieve it directly. This is grounded retrieval, not prompt
prefetching. `knowledge.read` also remains the deterministic path for whole-document,
named-section, adjacent-context, and iterative reading. `knowledge.list_documents` is metadata
discovery and is not a content-QA preflight.

The model still decides the retrieval query and whether follow-on reads are needed. Orion does not
add an application-side semantic pre-router.

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

Attachment identities are runtime-bound scope. Current-session attachment metadata may also expose
an exact `document_id` to the model so it can perform a deterministic read of that attachment
without a metadata-listing preflight. The document contents themselves are not prefetched.

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
lexical/hash-overlap retrieval; optional, explicitly backfilled dense index
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

### RAG v2 Phase 3B production retrieval

The default production `knowledge.search` fuses lexical overlap with a deterministic
token-hash overlap ranker. Token hashing is **not learned semantic retrieval**. Phase 1–2 adds a
provider-neutral `EmbeddingPort`, immutable model profiles, Orion-owned float32 vector encoding,
SQLite segment-embedding storage, separate semantic indexing progress, and an offline retrieval
benchmark. Phase 3A adds an explicitly provisioned local FastEmbed/ONNX E5 adapter and bounded
semantic backfill. Phase 3B adds operator opt-in hybrid ranking to the same model-called
`knowledge.search`. With `ORION_KNOWLEDGE_SEMANTIC_SEARCH=hybrid`, the service lazily loads the
local model on the first search with visible segments, obtains up to 50 scoped dense candidates
from `SemanticIndexService.search`, and fuses their rank with the existing production baseline
rank. Fusion uses reciprocal rank with `k=60`, a 0.05 score bonus for an exact case-insensitive
filename match, and canonical segment ID tie-breaking. The requested result limit still applies.
No model-visible routing or new retrieval service is introduced.

`documents.status = ready` retains its existing meaning: parsing, chunking, and segment storage
completed, so lexical search and exact reading work. Semantic indexing has an independent
`missing → indexing → ready` path and may enter `failed`; either `missing` or `failed` leaves
the document available through lexical retrieval. A ready document may have no current vectors,
or only some current vectors. Hybrid mode uses only existing valid current-profile vectors;
it does not imply complete semantic coverage. Absent or `off` mode retains the exact Phase 3A
production ranking and scores. A missing/corrupt/unavailable local model, a recoverable query
inference failure, or no visible dense hits falls back to that same lexical ranking. Unexpected
persistence, scope, and programming failures propagate. Normal startup and search never download
model weights, backfill vectors, or call an external embedding endpoint.

These are independent states: document `ready` means canonical text can be searched/read; model
`installed` means verified local weights are present (otherwise `missing` or `corrupt`); document
semantic `ready` means its current segments have current-profile vectors (otherwise `missing` or
`failed`); production mode `off` or `hybrid` controls whether dense ranking is attempted. Model
memory is incurred only when an enabled search first loads E5, and the loaded service is reused.

An embedding profile identifies its implementation, pinned model revision and digests, precision,
dimension, pooling, normalization, input prefixes, token limit, and windowing version. Its ID is
derived from the canonical definition. Persisted vectors are keyed by original segment ID,
profile ID, and window ordinal; a source-text digest prevents stale vectors from ranking.
Backfill may resume from missing/stale segments without replacing document segments or changing
source and citation identities. Application-owned scope filters candidate vectors before ranking.

## Retrieval task shapes

Retrieval must not assume "top-k vector chunks" is sufficient for every task.

### Local fact/question answering

Search relevant segments first, optionally rerank, and return source metadata. Do not require a
metadata-listing call before content retrieval. If the model already knows an exact document ID,
constrain search to that document when appropriate.

### Whole-document understanding

Use document structure, larger sections, hierarchical summaries, or iterative reads rather than only local chunk search.

### Cross-document comparison

Retrieve from multiple explicitly scoped documents and preserve document identity in results.

### Exact document reading

When the task requires whole-document, named-section, adjacent-context, or iterative reading and
the model already knows the document identity, allow deterministic read/section retrieval. This is
grounded retrieval but is distinct from ranked content search; it should not replace
`knowledge.search` as the default fact/topic/quote discovery path.

## Hybrid retrieval

The opt-in Phase 3B production pipeline is:

```text
model-called knowledge.search(query)
 ├── current lexical + token-hash baseline rank
 └── scoped E5 dense segment rank (at most 50, when available)
        ↓
Phase 3A RRF fusion (k=60, exact-filename protection)
        ↓
source-aware results
```

There is no reranker in Phase 3B. The lexical baseline remains available whenever semantic
retrieval is off or unavailable.

Phase 3C measures a deterministic document-balanced evidence selector after the existing bounded
ranking. It first takes each document's best candidate in upstream order, then fills remaining
slots in original order. It keeps original segments, scores, and citations, requires no new model
or resource, and is **not active** in production `knowledge.search`. Phase 3B remains the production
behavior; any activation decision is deferred. There is still no learned reranker.

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
