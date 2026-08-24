# API and backend architecture

## Role

The backend exposes stable product resources while hiding provider/executor internals. API schemas should represent typed session, request, tool, approval, evidence, target/source, project, and model state.

## Suggested resources

- `/health` — service health, not model health.
- `/models` — configured model connections and explicit health state.
- `/sessions` — create/list/read/delete sessions.
- `/sessions/{id}/messages` — submit user requests and read timeline items.
- `/sessions/{id}/approvals/{approval_id}` — allow/deny exact pending action.
- `/sessions/{id}/events` — stream public typed runtime events.
- `/targets` and `/sources` — exact configured references, with secrets omitted.
- `/projects` and `/documents` — project/RAG lifecycle.
- `/metrics` — projections from the canonical event stream.

Exact HTTP paths may change during implementation; resource semantics should not.

## Streaming

Long-running requests should stream typed events or server-sent events. The UI should not infer tool success from assistant text.

## Health

Separate:

- service reachable;
- model configured;
- model health unknown/healthy/unhealthy;
- integration configured;
- integration health.

HTTP 200 alone is not semantic health.

## OpenAPI

Generate OpenAPI from the implemented backend. Do not hand-edit a target `openapi.json` before implementation stabilizes.
