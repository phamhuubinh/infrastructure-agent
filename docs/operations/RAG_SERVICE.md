# RAG service

## Current implementation

Document ingestion and retrieval run inside the Orion application process. There is no
separate RAG service. SQLite persists document metadata and normalized segments, while
the local blob directory persists original bytes. On a normal restart Orion reconciles
non-terminal `uploaded`, `parsing`, or `indexing` records without resurrecting tombstones.

RAG v2 Phase 1–2 also stores optional embedding profiles, vectors, and per-document semantic
progress in SQLite. No production embedding adapter or dense ranking is enabled yet. The current
search still combines lexical and token-hash overlap; documents stay searchable when semantic
progress is missing or failed. The opt-in semantic backfill service can resume missing/stale rows,
but application startup does not acquire a model or schedule semantic work.

The target architecture remains: RAG is a model-callable knowledge source, not an
always-on pre-model stage, and project scope is runtime-bound.
