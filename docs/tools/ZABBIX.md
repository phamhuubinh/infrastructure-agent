# Zabbix tools

## Purpose and availability

These are the initial model-facing Zabbix operation contracts, including template
read access because templates are within the currently documented Zabbix capability
scope. A successfully configured integration registers them through the ordinary
`ToolRegistry` for the same Chat and Project loop. There is no Zabbix mode, tool
picker, approval flow, semantic router, raw base-URL/token argument, or generic
Zabbix JSON-RPC method invocation.

Every schema is a closed object. `target_ref` is the exact opaque, stable, non-secret
configured Zabbix identity defined in [`CONTRACTS.md`](../architecture/CONTRACTS.md):
1–64 characters matching `^[a-z][a-z0-9._-]{0,63}$`. It is resolved and validated
before every upstream request; connection data and credentials remain server-side.

Zabbix object IDs are operation data, represented as decimal strings matching
`^[1-9][0-9]{0,18}$`. This preserves upstream identity without accepting arbitrary
JSON-RPC objects. Filter text is 1–128 characters and rejects NUL/control characters.
Timestamps use RFC 3339 `date-time`; an end timestamp must be later than its start.

## Read operations

### `zabbix.host.get`

Returns bounded normalized host summaries. It may select exact host IDs, a bounded
name substring, or the bounded default listing; object IDs returned by this tool can
be supplied to later Zabbix calls.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "host_ids": {
      "type": "array", "items": {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"},
      "minItems": 1, "maxItems": 50, "uniqueItems": true
    },
    "name_contains": {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[^\\u0000-\\u001f]+$"},
    "monitored_only": {"type": "boolean", "default": true},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}
  },
  "required": ["target_ref"],
  "additionalProperties": false
}
```

When both selectors are present, they are intersected. Returned records are capped by
`limit` and contain only safe host identity/name/status/interface summary data.

### `zabbix.event.list`

Returns bounded normalized event summaries. Severity values are Orion semantic
values, mapped internally to the Zabbix API rather than passed as a generic filter.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "host_ids": {
      "type": "array", "items": {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"},
      "minItems": 1, "maxItems": 50, "uniqueItems": true
    },
    "severities": {
      "type": "array", "items": {"type": "string", "enum": ["not_classified", "information", "warning", "average", "high", "disaster"]},
      "minItems": 1, "maxItems": 6, "uniqueItems": true
    },
    "acknowledged": {"type": "boolean"},
    "from": {"type": "string", "format": "date-time", "maxLength": 40},
    "to": {"type": "string", "format": "date-time", "maxLength": 40},
    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100}
  },
  "required": ["target_ref"],
  "additionalProperties": false
}
```

`from` and `to` must be supplied together when either is supplied; the interval is
limited to 31 days. Event descriptions/tags are untrusted data and are bounded before
returning to the model.

### `zabbix.history.get`

Returns bounded raw history observations for explicitly identified items only; it is
not a generic history query. The interval is limited to seven days and returned data
is capped by `limit`.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "item_ids": {
      "type": "array", "items": {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"},
      "minItems": 1, "maxItems": 10, "uniqueItems": true
    },
    "from": {"type": "string", "format": "date-time", "maxLength": 40},
    "to": {"type": "string", "format": "date-time", "maxLength": 40},
    "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 500}
  },
  "required": ["target_ref", "item_ids", "from", "to"],
  "additionalProperties": false
}
```

### `zabbix.trigger.get`

Returns bounded normalized trigger summaries, optionally narrowed to explicit trigger
or host identities.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "trigger_ids": {
      "type": "array", "items": {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"},
      "minItems": 1, "maxItems": 50, "uniqueItems": true
    },
    "host_ids": {
      "type": "array", "items": {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"},
      "minItems": 1, "maxItems": 50, "uniqueItems": true
    },
    "only_problem": {"type": "boolean", "default": false},
    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100}
  },
  "required": ["target_ref"],
  "additionalProperties": false
}
```

If both ID filters are supplied, they are intersected.

### `zabbix.template.get`

Returns bounded safe template summaries. This explicit operation covers the current
documented template scope without allowing arbitrary API method calls.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "template_ids": {
      "type": "array", "items": {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"},
      "minItems": 1, "maxItems": 50, "uniqueItems": true
    },
    "name_contains": {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[^\\u0000-\\u001f]+$"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}
  },
  "required": ["target_ref"],
  "additionalProperties": false
}
```

When both selectors are supplied, they are intersected. All Zabbix read operations
may make no more than two transient transport retries before a response; retries use
the identical target, runtime scope, and validated arguments. Validation, permission,
and not-found failures are not retried.

## Mutation operation

### `zabbix.event.acknowledge`

Acknowledges one or more existing events. The semantic operation maps internally to
Zabbix's acknowledgement API; model arguments never carry a raw method name, action
bitmask, token, or request object. The side-effect boundary is dispatch of that
semantic acknowledgement after target/credential resolution, preflight, and the
immediate cancellation check.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "event_ids": {
      "type": "array", "items": {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"},
      "minItems": 1, "maxItems": 50, "uniqueItems": true
    },
    "message": {"type": "string", "maxLength": 500, "pattern": "^[^\\u0000-\\u001f]*$", "default": ""}
  },
  "required": ["target_ref", "event_ids"],
  "additionalProperties": false
}
```

Preflight loads each event and its acknowledgement state. Events already acknowledged
are converged without dispatch; if all are already acknowledged, return success with
`changed: false` and per-event observed state. Otherwise dispatch one acknowledgement
for only the unacknowledged IDs, then require API confirmation and, where practical,
bounded observed acknowledged state. Success data includes `target_ref`, `changed`,
safe `event_ids`, `acknowledged_event_ids`, and a per-event
`verification: {"status": "verified" | "confirmed"}` summary.

Acknowledgement is convergent but not blindly replayable. There is no automatic retry
after dispatch: a transport-uncertain call verifies state when practical and otherwise
returns `outcome_unknown`. Cancellation before dispatch returns/propagates `cancelled`
with no side effect; after dispatch it is not rollback and follows the same bounded
verification/unknown-outcome rule.

## Results, sources, and activity

Read observations use canonical `ToolResult` and, where useful, `SourceRef` with
`source_kind: "zabbix"`, safe configured target as `source_id`, and safe object/time
provenance. A mutation source represents observed acknowledgement evidence only, not
authorization. Upstream text is untrusted data and results, sources, logs, and public
activity never include credentials, tokens, raw headers, base URLs, or secret-bearing
URLs. The normal runtime activity shows safe tool name, target, read/mutation,
lifecycle, `changed`, verification, and explicit unknown outcome.
