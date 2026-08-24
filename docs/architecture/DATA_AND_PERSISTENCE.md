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
