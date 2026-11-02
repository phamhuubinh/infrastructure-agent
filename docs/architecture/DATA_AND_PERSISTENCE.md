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
ScheduledTask / ScheduledRun
EndpointIdentity / PairingToken / EndpointAudit
PendingMutationAuthorization
```

## Session

A Session owns a conversation, surface kind and mutation mode. Ordinary Chat and
Project sessions can own attachments; Device Chat instead binds endpoint_id and
has no Project/attachment scope. Device sessions are excluded from ordinary
conversation discovery.

Legacy derived checkpoint rows remain for storage compatibility. The current
request path does not read them or generate a preparatory model summary; they are
not a second source of conversation truth.

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

The inspected implementation uses SQLite for metadata/session/project/index state
and local blob storage for uploads, with lexical/exact retrieval and configured
semantic indexing. Preserve this baseline. A separate vector database, broker or
new storage service is not required by the redesign.

Cross-store operations require recovery-safe semantics. A failed index update must not make metadata claim a document is ready when it is not.

## Offline backup and restore

Stop Orion, create an owner-controlled backup parent, then use:

```text
orion data export BACKUP_DIRECTORY
orion data import BACKUP_DIRECTORY/orion-backup-UUID NEW_DATA_DIRECTORY
orion data retain BACKUP_DIRECTORY --keep 5
```

Export acquires the runtime lease and includes a SQLite online snapshot, original
UUID blobs and protected provider-credential records, with a versioned checksum
manifest. Import validates the complete bundle and publishes into a new directory;
it refuses an existing target. Set `ORION_DATA_DIR` to that new directory, or
`ORION_DATABASE_PATH` to its `orion.db`, before starting Orion. Existing explicit
database-path configuration takes precedence over the data directory.

Windows DPAPI records require the original Windows account/machine. Environment
credential references require reconfiguration; their values are never exported.
External SSH/tool/MCP configuration, remote worker state, OS key material, logs,
models and binaries are outside the managed-data backup. Only restore trusted
bundles. Retention preflights all matching bundles and deletes only validated owned
files; it does not purge application history or migration snapshots. Failed
exports/imports leave private unpublished staging directories for diagnosis.
See [the v1 lifecycle contract](../refactor/DATA_LIFECYCLE.md) for exact boundaries.

Local blob operations reject redirected ancestors, symlinks, Windows reparse
points, hard links and replacement of the open store's root. New bytes receive
private permissions before writing; legacy owned blobs are protected at store open.
These checks do not isolate a hostile process running as the same OS account.

Lexical/exact retrieval and data operations require no semantic model or packages.
The `semantic` extra and installer embedding flag opt into local E5 support.

## Local-first durability

Default deployment persists data in local application-data storage. Reinstalling
or rebuilding an application must not delete sessions/projects/documents unless
the user explicitly removes persistent data.

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
