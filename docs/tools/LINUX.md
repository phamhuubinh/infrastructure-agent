# Linux tools

## Purpose and availability

These are the initial model-facing Linux operation contracts. A successfully
configured Linux integration registers them through the ordinary `ToolRegistry`; all
registered tools are automatically visible in Chat and Project. There is no Linux
mode, approval flow, semantic router, generic shell, `linux.exec`, `linux.shell`,
`ssh.exec`, or `command.run` model-facing operation.

`target_ref` selects one exact configured Linux target. It is an opaque non-secret
reference, not a hostname, SSH username, key path, credential reference, or transport
option. Its common contract and server-side resolution rules are in
[`CONTRACTS.md`](../architecture/CONTRACTS.md). All schemas below are closed JSON
Schema-shaped contracts (`type: object`, `additionalProperties: false`).

### Common validated values

`target_ref` is a 1–64 character configured identifier matching
`^[a-z][a-z0-9._-]{0,63}$`. `service` and `package` are 1–128 character semantic
identifiers matching `^[A-Za-z0-9][A-Za-z0-9@+_.:-]{0,127}$`; they cannot start with
`-` and cannot contain whitespace, `/`, shell metacharacters, command substitution,
or multiple commands. A `version`, when accepted, is 1–128 characters matching
`^[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,127}$`.

`path` is an absolute POSIX path of at most 4,096 characters with no NUL or control
characters and no `.` or `..` component. The executor canonicalizes it and performs a
direct bounded file read; it treats it as data and never interpolates it into a shell
command. Target-side file authorization remains an integration concern.

The schemas show defaults that #93 must apply when an optional field is omitted.

## Read operations

### `linux.system.inspect`

Returns a bounded structured summary of CPU, memory, disk, and/or network state for
one configured target. It does not return arbitrary command output.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "sections": {
      "type": "array", "items": {"type": "string", "enum": ["cpu", "memory", "disk", "network"]},
      "minItems": 1, "maxItems": 4, "uniqueItems": true,
      "default": ["cpu", "memory", "disk", "network"]
    }
  },
  "required": ["target_ref"],
  "additionalProperties": false
}
```

### `linux.file.read`

Reads one bounded byte range from a validated absolute path. The result contains
bounded decoded text or a safe indication that the selected range is non-text; it
does not execute or source the file.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "path": {"type": "string", "minLength": 1, "maxLength": 4096, "pattern": "^/[^\\u0000-\\u001f]*$"},
    "offset": {"type": "integer", "minimum": 0, "maximum": 1073741824, "default": 0},
    "length": {"type": "integer", "minimum": 1, "maximum": 65536, "default": 16384}
  },
  "required": ["target_ref", "path"],
  "additionalProperties": false
}
```

The path-component and canonicalization rules above are additional required
operation validation; JSON Schema alone is not sufficient for them.

### `linux.service.status`

Returns structured observed service state, including safe status fields such as unit
name, active state, substate, and enabled state where supported.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "service": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9@+_.:-]{0,127}$"}
  },
  "required": ["target_ref", "service"],
  "additionalProperties": false
}
```

### `linux.package.status`

Returns structured installed/version state for one semantic package identifier.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "package": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9@+_.:-]{0,127}$"}
  },
  "required": ["target_ref", "package"],
  "additionalProperties": false
}
```

Read operations may use bounded transport retries only before a successful response,
and only against the same validated target and `RuntimeScope`. The default is no more
than two retries for transient `connection_error`, `timeout`, or documented temporary
`upstream_error`; no validation, permission, or not-found error is retried.

## Mutation operations

### `linux.service.restart`

Requests the explicit semantic restart of one validated service. The side-effect
boundary is dispatch of that restart request after target/credential resolution,
preflight, and the immediate cancellation check.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "service": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9@+_.:-]{0,127}$"}
  },
  "required": ["target_ref", "service"],
  "additionalProperties": false
}
```

Preflight confirms that the service exists and that the configured identity may
restart it. Request acceptance alone is not success: bounded post-action verification
must observe the service in `active`/running state. Success data includes
`target_ref`, `changed: true`, `service`, `observed_state`, and
`verification: {"status": "verified"}`.

A restart is not idempotent as an action. Orion never automatically retries it; each
new tool call is a new restart request. If dispatch or cancellation after dispatch
leaves the outcome uncertain, return `outcome_unknown` (with safe verification
evidence if available). A later restart requires status inspection first.

### `linux.package.install`

Converges one package to installed state, optionally at an explicitly requested
version. It never accepts package-manager flags or raw commands. Its side-effect
boundary is dispatch of the one package-install request after preflight and the
immediate cancellation check.

```json
{
  "type": "object",
  "properties": {
    "target_ref": {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"},
    "package": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9@+_.:-]{0,127}$"},
    "version": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,127}$"}
  },
  "required": ["target_ref", "package"],
  "additionalProperties": false
}
```

Preflight reads the current package state. If the requested package/version is already
installed, return success with `changed: false` and the observed version without a
side effect. Otherwise install once and verify the final package state within a
bounded period. Success data contains `target_ref`, `changed`, `package`,
`requested_version` (when supplied), `observed_version`, and
`verification: {"status": "verified"}`. No blind replay follows uncertain dispatch;
use `outcome_unknown` when final state cannot be determined.

For both mutations, cancellation before the side-effect boundary returns/propagates
`cancelled` and issues no mutation. Cancellation after dispatch is not rollback;
Orion performs the stated bounded verification where possible and never fabricates a
success or a no-change claim.

## Results, sources, and activity

Reads return canonical `ToolResult` plus a useful `SourceRef` when the observation is
source-bearing: `source_kind: "linux"`, `source_id` as safe configured target ref,
and safe operation/section/timestamp metadata. Mutation sources are post-action
observation only when meaningful. Results, sources, logs, and public activity never
include secrets or transport details. Normal runtime activity displays safe tool name,
target display/ref, read versus mutation, lifecycle, `changed`, verification, and an
explicit unknown outcome when applicable.
