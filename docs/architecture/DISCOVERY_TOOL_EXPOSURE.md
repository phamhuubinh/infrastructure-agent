# Discovery and dynamic tool exposure

## Problem

Infrastructure agents may have dozens or hundreds of capabilities. Sending every detailed schema on every model call wastes context and increases tool-selection errors.

## Design

The initial tool surface contains a small number of always-available harness tools, especially:

- `capability.search` — search/load reviewed capability namespaces or capabilities;
- project/context retrieval tools when the session has project knowledge.

`capability.search` is read-only harness functionality. It does not grant infrastructure authority.

Example:

```json
{
  "namespace": "calculator",
  "query": "exact arithmetic"
}
```

Result:

```json
{
  "matches": [
    {
      "capability_id": "compute.deterministic",
      "purpose": "Exact deterministic arithmetic",
      "effect": "read",
      "result_kind": "deterministic_result"
    }
  ],
  "loaded_tools": ["compute.deterministic"]
}
```

On the next model call, `compute.deterministic` is present as a real tool with its exact argument schema.

## Exposure state

Each request/session runtime tracks an immutable-or-monotonic exposure set:

```text
exposed_tools = {
  capability.search,
  compute.deterministic,
  host.service.status,
  ...
}
```

A registered capability that is not exposed cannot be called. Provider tool schemas are generated only from exposed capabilities.

## Namespaces

Prefer small, coherent namespaces such as:

- `host`;
- `grafana`;
- `zabbix`;
- `internet`;
- `calculator`;
- `project`.

Namespaces are discovery surfaces, not authority scopes. Actual authority always belongs to exact capability + exact references + exact arguments.

## Search constraints

- No fuzzy authorization from a search result.
- Search may use semantic ranking to help model discovery, but execution still requires exact selected capability ID.
- Search results never contain credentials, raw commands, or unrestricted executor details.
- Loading a tool does not imply permission to execute it.

## Provider compatibility

OpenAI Responses models may use native deferred tool loading/tool search when available. Other providers use Orion-managed client-side exposure. Both normalize to the same harness state; provider features must not become architectural requirements.
