# Backend and API

## Role

The backend is the application boundary for:

- Chat requests;
- Project lifecycle;
- document upload/ingestion;
- model configuration;
- session state;
- cheap application health;
- streaming runtime events.

## Resource-oriented target

Exact routes may evolve, but product resources should remain recognizable:

```text
/health
/models
/sessions
/sessions/{id}/messages
/sessions/{id}/attachments
/sessions/{id}/documents/{document_id}
/projects
/projects/{id}
/projects/{id}/documents
/knowledge/...
```

## Chat request

A message submission should identify:

- session;
- user message;
- optional attachments;
- active project relation (owned by session/project state rather than tool choice).

There should be no list such as:

```json
{"enabled_tools":["rag","grafana"]}
```

in normal Chat/Project request semantics.

## Streaming

Streaming should expose public progress:

```text
message accepted
model started
tool call started
tool call completed/failed
model resumed
assistant output
request completed/failed
```

UI may render these events but does not use them to choose tools.

## OpenAPI

Generate OpenAPI from the implemented backend. Do not treat a hand-written stale schema as architectural authority.

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
