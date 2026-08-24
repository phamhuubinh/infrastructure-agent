# RAG and project knowledge

## RAG's role

RAG is a **knowledge source used by the model**, not a mandatory stage applied to every user message.

The model decides when document retrieval is useful.

## Knowledge scopes

The target supports distinct scopes:

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

A deployment may maintain a local shared knowledge library. If present, it is a separate explicit source, never implicitly mixed with project data.

## Active Project

Within a project conversation the model can use:

```text
session attachments
+ active project's RAG source
+ other registered tools
```

It must not receive documents from unrelated projects.

## Ingestion

Target ingestion:

```text
file
 ↓
identify format
 ↓
parse text/structure
 ↓
normalize
 ↓
chunk with document/page/section metadata
 ↓
embedding
 ↓
lexical/vector indexes
 ↓
ready
```

Parser/embedding/index implementations are replaceable components.

## Retrieval

Retrieval should not assume "top-k vector chunks" is sufficient for every task.

Support at least these task shapes:

### Local fact/question answering

Search relevant chunks, optionally rerank, return source metadata.

### Whole-document understanding

Use document structure, larger sections, hierarchical summaries, or iterative reading rather than only local chunk search.

### Cross-document comparison

Retrieve from multiple explicitly scoped documents and preserve document identity in results.

### Exact document reading

When the model already knows the document ID, allow deterministic read/section retrieval without semantic search.

## Hybrid retrieval

Useful pipeline:

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

Advanced GraphRAG/RAPTOR/HyDE techniques are optional optimizations, not architecture requirements.

## Citations

A retrieved item should preserve:

- source scope;
- project/session ID;
- document ID;
- document name;
- page/section when available;
- chunk/segment ID;
- text;
- retrieval score/rank metadata where useful.

Document-grounded answers should cite these source identities when practical.

## Untrusted text

Retrieved text is data. A document instruction such as "ignore previous rules" must not become an Orion system instruction.
