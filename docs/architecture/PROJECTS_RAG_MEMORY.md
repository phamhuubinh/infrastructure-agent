# Projects, RAG, Context, and Memory

## Target Project model

A Project contains files/knowledge and multiple chats. Project retrieval is a normal READ capability in the same agent loop.

Current implementation gap: standalone RAG exists, but Chat integration does not yet.

## Isolation and mutation consistency

Project/document identity/provenance must be preserved. Deleting one document/Project must not affect another.

Filesystem + metadata + BM25 + vector mutations use a persistent recovery
journal: uploads stage then atomically promote files and commit metadata last;
document/project deletes tombstone visibility before idempotent cleanup. A
per-project mutex prevents concurrent interleaving but is not crash
transactionality.

Corrupt persistence metadata must be preserved/quarantined and fail closed for mutation, not treated as empty and overwritten.

## Retrieval

Prefer deterministic parsing/chunking, Vietnamese-aware lexical retrieval, optional semantic retrieval/model expansion, deterministic fusion/balancing, bounded evidence, then final active-model reasoning.

## Chat memory/context budget

Use one aggregate serialized/token budget. Priority:

1. complete current request within documented limit;
2. compact summary/important structured refs;
3. recent turns;
4. bounded attachment/project evidence.

Do not silently truncate the current request into a different request. Do not drop the compact summary simply because enough recent messages exist.

Dynamic observations keep time/provenance and are not silently relabeled fresh.
