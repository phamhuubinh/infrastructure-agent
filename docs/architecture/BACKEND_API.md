# Backend and API

## Role

R12 adds native owner credentials, durable request admission and a generated
shared owner SDK. See [native access](../refactor/NATIVE_AUTH.md),
[SDK contract](../refactor/SDK.md) and
[dated implementation evidence](../refactor/evidence/R12_SESSION_2026-10-31.md).
Browser cookies/Origin and endpoint-worker credentials retain separate boundaries.
New consumers admit through `/api/sessions/{id}/requests` with a client UUID,
then observe `/api/requests/{id}/event-page` or `/stream`; reconnecting observation
does not submit another model turn. Legacy message endpoints retain their existing
behavior until client migration. Version reports compatibility; doctor reports
configuration observations, not live-provider/target readiness.

The backend is the application boundary for:

- Chat requests;
- Project lifecycle;
- document upload/ingestion;
- model configuration;
- session state;
- cheap application health;
- streaming runtime events;
- endpoint administration, device-bound conversation and manual control resources;
- scheduler task resources using the same runtime.

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

Chat, Project and Device Chat submissions enter the same runtime. The API resolves
the persisted surface and binds principal/workspace/project/endpoint identity
server-side. Generic session routes must not become a way to retarget, attach
Project data to, or delete a Device Chat outside endpoint lifecycle safeguards.
See [Endpoints](ENDPOINTS.md) for the implemented endpoint route categories.

A message submission should identify:

- session;
- user message;
- optional attachments;
- active project relation (owned by session/project state rather than tool choice).

There should be no list such as:

```json
{"enabled_tools":["rag","windows"]}
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
