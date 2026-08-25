# RAG service

## Current implementation

Document ingestion and retrieval run inside the Orion application process. There is no
separate RAG service. SQLite persists document metadata and normalized segments, while
the local blob directory persists original bytes. On a normal restart Orion reconciles
non-terminal `uploaded`, `parsing`, or `indexing` records without resurrecting tombstones.

The target architecture remains: RAG is a model-callable knowledge source, not an
always-on pre-model stage, and project scope is runtime-bound.
