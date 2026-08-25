# Grafana tools

## Purpose and availability

These are the initial model-facing Grafana contracts. A successfully configured
Grafana integration registers them through the normal `ToolRegistry`, automatically
available to the same Chat and Project model loop. There is no Grafana mode, tool
picker, approval flow, semantic router, raw base-URL/token argument, or generic
Grafana HTTP/API operation.

Every schema is a closed object. `target_ref` is the same exact, opaque, non-secret
configured target identity defined in [`CONTRACTS.md`](../architecture/CONTRACTS.md):
1–64 characters matching `^[a-z][a-z0-9._-]{0,63}$`. Connection details and
credentials are server-side only.

`dashboard_uid` and `datasource_uid` are Grafana object identities used as operation
data, each 1–40 characters matching `^[A-Za-z0-9_-]{1,40}$`. They are not URLs or
credentials. Text strings reject NUL/control characters; timestamps use RFC 3339
`date-time` and `time_end`/`to` must be later than `time`/`from`.

## Read operations

### `grafana.dashboard.get`

Returns bounded safe dashboard definition/metadata for one dashboard UID. The result
does not expose datasource credentials embedded in any upstream representation.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "dashboard_uid": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,40}$"}
  },
  "required": ["target_ref", "dashboard_uid"],
  "additionalProperties": false
}
```

### `grafana.datasource.query`

Runs one bounded read query through a specifically named Grafana datasource and
returns normalized, bounded datapoints/series. `query` is datasource query language
data, not a transport request, and is limited to 4,000 characters with no NUL/control
characters. #93 must expose this operation only through datasource adapters/configured
datasources that enforce read-only query authority; write/admin datasource commands
must be rejected before dispatch. This is operation-specific safety validation, not a
semantic pre-router.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "datasource_uid": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,40}$"},
    "query": {"type": "string", "minLength": 1, "maxLength": 4000, "pattern": "^[^\\u0000-\\u001f]+$"},
    "from": {"type": "string", "format": "date-time", "maxLength": 40},
    "to": {"type": "string", "format": "date-time", "maxLength": 40},
    "max_data_points": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 500}
  },
  "required": ["target_ref", "datasource_uid", "query", "from", "to"],
  "additionalProperties": false
}
```

The integration validates `from < to`, limits the requested interval to 31 days, and
caps returned series/points to the stated bounds. It may use at most two transient
transport retries before a response, always against the same target and query.

### `grafana.alert.list`

Returns bounded normalized alert-rule state. State values are Orion's normalized
semantic values, not an invitation to invoke Grafana's generic alert APIs.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "states": {
      "type": "array",
      "items": {"type": "string", "enum": ["normal", "alerting", "pending", "no_data", "error", "recovering"]},
      "minItems": 1, "maxItems": 6, "uniqueItems": true
    },
    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100}
  },
  "required": ["target_ref"],
  "additionalProperties": false
}
```

## Mutation operation

### `grafana.annotation.create`

Creates one bounded Grafana annotation. It is the initial Grafana mutation because it
is a clear semantic side effect without dashboard/datasource administration authority.
The side-effect boundary is dispatch of the create request after target/credential
resolution, semantic preflight, and the immediate cancellation check.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "time": {"type": "string", "format": "date-time", "maxLength": 40},
    "time_end": {"type": "string", "format": "date-time", "maxLength": 40},
    "text": {"type": "string", "minLength": 1, "maxLength": 1000, "pattern": "^[^\\u0000-\\u001f]+$"},
    "tags": {
      "type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64, "pattern": "^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$"},
      "maxItems": 10, "uniqueItems": true, "default": []
    },
    "dashboard_uid": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,40}$"},
    "panel_id": {"type": "integer", "minimum": 1, "maximum": 2147483647}
  },
  "required": ["target_ref", "time", "text"],
  "additionalProperties": false
}
```

`time_end`, when supplied, must be after `time`; `panel_id` requires `dashboard_uid`.
Success requires an upstream success response containing a stable sanitized annotation
identity. Success data contains `target_ref`, `changed: true`, `annotation_id`,
`time`, optional `time_end`, and `verification: {"status": "accepted", "annotation_id": "..."}`.

Annotation creation is not idempotent: it creates a new event each time. Orion never
automatically retries after dispatch. If cancellation or transport failure occurs
after dispatch, bounded lookup/response-based verification is attempted only when
safe; otherwise return `outcome_unknown`, never a blind replay. Before dispatch,
cancellation returns/propagates `cancelled` and creates nothing.

## Results, sources, and activity

Read observations use canonical `ToolResult` and, where useful, `SourceRef` with
`source_kind: "grafana"`, safe configured target as `source_id`, and safe object/time
provenance. An annotation source can represent its post-create observation only; it is
not authorization evidence. Results, sources, logs, and activity omit credentials,
tokens, base URLs, raw headers, and secret-bearing URLs. The normal runtime activity
shows only safe tool name, target, read/mutation, lifecycle, `changed`, verification,
and explicit unknown outcome.
