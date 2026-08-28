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
