# Data and persistence

## Core entities

Target persistent resources:

```text
ModelConfig
Session
Message/TimelineItem
Attachment
Project
ProjectDocument
DocumentIngestionState
KnowledgeSource
ToolCall/ToolResult metadata
```

## Session

A Session owns a conversation and session-scoped attachments.

It may also own one derived rolling conversation-state checkpoint. This cache records
a bounded state text and the stable canonical timeline boundary it covers; it is not
a timeline message and cannot replace or rewrite canonical history.

## Project

A Project owns durable metadata and project documents.

A session may be associated with one active project. The Project does not own a separate agent runtime.

## Documents

Document lifecycle should be explicit:

```text
uploaded
→ parsing
→ indexing
→ ready
or
→ failed
```

Deletion must remove or tombstone the corresponding index entries so deleted documents do not reappear in retrieval.

Semantic indexing is separate from document ingestion status. A `ready` document remains
queryable through lexical search and exact reads if its semantic profile is `missing`, `indexing`,
or `failed`. `embedding_profiles` stores immutable canonical profile definitions;
`segment_embeddings` stores little-endian float32 vectors keyed by segment/profile/window with
source-text digests; `document_semantic_index` stores per-document/profile progress. Reindexing
does not replace `document_segments` or their citation identities. Tombstoned documents are
excluded from semantic queries immediately, and their vector rows are removed.

## Stores

The implementation may use multiple physical stores:

- relational store for metadata/session/project state;
- object/filesystem store for uploaded files;
- vector database for embeddings;
- lexical index for BM25;
- optional caches.

Cross-store operations require recovery-safe semantics. A failed index update must not make metadata claim a document is ready when it is not.

## Local-first durability

Default deployment should persist data on local volumes. Rebuilding containers must not delete user sessions/projects/documents unless the user explicitly removes persistent data.

## Scheduled executions

The canonical SQLite store additively persists `scheduled_tasks` and `scheduled_runs`.
Each task owns a dedicated ordinary session; run rows reference ordinary requests
and preserve UTC occurrence identity. See [Scheduler v1](SCHEDULER.md) for exact
columns, atomic claim, coalescing, crash recovery and deletion semantics.

## Remote Endpoint v1

See [endpoint runtime and threat model](ENDPOINTS.md) and
[ADR 0015](../decisions/0015-paired-endpoint-execution.md) for the additive worker
transport, identity persistence, fixed tool family and independent policy ceiling.

Remote Endpoint v1's primary mode is a zero-install **Remote Control** portable
worker with temporary in-memory credentials, foreground Disconnect/Exit and
explicit remembered mode. Its endpoint workspace contains Device Chat, Desktop,
Files, Processes, Browser and Connection. Device Chat uses the same canonical
ChatRuntime with persisted server-owned endpoint binding, separate history/mutation
mode and no Project/attachments. Cross-device endpoint calls are rejected.
Portable platform artifacts carry version/source SHA/checksums; source builds
without compatible release metadata show unavailable. Confirmed End & forget
removes endpoint-owned metadata/history under existing active-request safeguards.
See the endpoint operations/architecture reference for platform prerequisites,
cleanup/expiry, download integrity and native artifact smoke coverage.
