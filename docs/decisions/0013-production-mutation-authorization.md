# ADR 0013 — Production mutation authorization baseline

## Status

Proposed.

## Context

ADR 0011 defines the bounded infrastructure mutation lifecycle, but configured
credentials and a registered mutation do not themselves authorize production use.
The QA composition currently blocks mutations unless an explicitly enabled QA case
allows them. That QA-only guard is not a production control: the ordinary bootstrap
has an empty blocked-operation set.

The `operator-action-follow-up` QA artifact showed attempted restart calls during a
status-oriented workflow. Its `not_found` result is not evidence that a restart was
issued, but it demonstrates why model semantic choice alone must not grant a
production side effect.

ADR 0011 intentionally excludes an approval engine. This decision therefore sets a
deployment authorization baseline; it does not claim to establish a user
confirmation for every chat action.

## Proposed decision

Production is read-only by default. An infrastructure mutation is dispatchable only
when trusted server configuration contains one exact allowlist entry for both its
registered `tool_name` and its configured `target_ref`.

The allowlist is an application-owned bootstrap setting in the trusted local JSON
file named by `ORION_INFRASTRUCTURE_CONFIG`. It is a top-level
`mutation_allowlist` array, parsed and validated before the runtime is available.
An unset `ORION_INFRASTRUCTURE_CONFIG`, or an infrastructure file without this
field, means no mutation entries are authorized. Its shape is:

```json
[
  {"tool_name": "linux.service.restart", "target_ref": "monitor"},
  {"tool_name": "grafana.annotation.create", "target_ref": "grafana"}
]
```

The composition root constructs this policy from that file, independently of
credential resolution. It must not accept it from a model argument, request body,
persisted chat/project data, a tool result, or tool discovery. The configuration
source is trusted only as server/operator configuration; it is never model-visible
authority. Legacy credential-only configuration has no implicit allowlist and
therefore remains read-only.

### Fail-closed configuration rules

| Input or call | Proposed result |
| --- | --- |
| Allowlist unset or empty | All mutations denied; reads unaffected. |
| Malformed/unreadable `ORION_INFRASTRUCTURE_CONFIG`, malformed `mutation_allowlist`, duplicate/partial entry, unknown tool, non-mutation tool, or target not present in the configured target catalog | Fail application startup; do not silently start permissively or discard the bad entry. |
| Registered read operation | Allowed through the ordinary ToolRunner flow; it is not governed by this mutation allowlist. |
| Registered mutation whose exact `(tool_name, target_ref)` is absent | Denied before its integration handler/side-effect boundary. |
| Registered mutation whose operation is listed but argument target differs | Denied. A broad operation entry never grants another target. |
| Model supplies a policy/allowlist/enabled-tools argument | Closed-schema validation rejects it; it cannot alter the server policy. |
| Exact configured mutation operation and exact configured target | Eligible for the existing target resolution, credential resolution, preflight, cancellation, dispatch, and verification lifecycle. It is not guaranteed to succeed. |

An explicit denial has precedence over any credential capability or configured
target. The policy does not replace `RuntimeScope`: Orion still attaches the
application-owned session/project scope, then ordinary target resolution validates
the exact `target_ref` against that scope and catalog. A future mutation without a
closed, exact configured target is denied by this baseline until a new ADR defines
its authority model.

### Runtime boundary and result semantics

The policy belongs at the canonical ToolRunner authorization boundary, after exact
registered-tool and closed-schema validation and before a handler can resolve
credentials or issue an integration request. It may consult only the registered
definition, validated arguments, application-owned `RuntimeScope`, and the frozen
bootstrap policy. It does not route intent or choose tools.

For a denied mutation, return the existing canonical error code
`operation_blocked` with a safe message that local server policy does not authorize
the operation. The result is not retryable and does not expose allowlist contents,
credentials, policy paths, or target configuration beyond safe values already
visible to the model. A valid read or a different authorized mutation remains a
model semantic choice through the ordinary loop.

Tool registration and ADR 0007 progressive exposure are unchanged. A mutation may
remain discoverable/expandable as an ordinary registered tool even when the policy
will block a call; no per-request `enabled_tools` field, manual picker, or semantic
pre-router is introduced.

### Audit and side-effect invariants

Record an allow/deny decision using existing safe runtime activity/observability
surfaces: registered tool name, safe target reference, operation kind, decision, and
correlation identity. Do not record raw policy values, environment/configuration
locations, credentials, request headers, model text, or arbitrary argument blobs.

Once allowed, ADR 0011 remains fully controlling: cancellation before dispatch has
no side effect; a post-boundary cancellation or deadline preserves verified evidence
or `outcome_unknown`; no mutation is transparently retried or replayed. Default
read-only prevents unconfigured side effects but neither proves grounding nor
changes deadline behavior.

## Per-action authority is deliberately not claimed

Consider a user who says a service was already restarted and the model proposes to
restart it again. Under the default policy, the call is blocked. Under an exact
deployment allowlist, it can be dispatched because server configuration grants that
operation/target capability; the allowlist does **not** prove that this user freshly
confirmed this particular restart, nor does it prevent a model from choosing a
redundant action.

If product requirements demand per-action user confirmation, that must supersede or
replace the ADR 0011 no-approval-engine constraint in a new ADR. The resulting
confirmation state, UI, API, cancellation and audit flow must be separately
designed and implemented; it is not a prompt convention or an addition to the
model's tool arguments.

## Consequences and implementation acceptance matrix

This ADR is proposed only. It changes neither current production bootstrap behavior
nor QA composition. After acceptance, the follow-on implementation issue must prove
the following offline with fake registry/catalog/handlers only:

| Scenario | Required proof |
| --- | --- |
| Unset config | A mutation returns `operation_blocked`; a read runs normally. |
| Invalid config | Bootstrap fails closed before a runtime is exposed. |
| Exact allowlisted operation and target | The handler can be reached, then existing mutation lifecycle controls apply. |
| Different target or operation | Handler is not reached; result is `operation_blocked`. |
| Model-injected policy argument | Schema validation rejects it before authorization/handler execution. |
| User claims prior action | Tests document that read-only blocks it; allowlisted dispatch is capability authorization, not user confirmation. |
| Audit/log output | It is bounded and redacted, with no credentials or raw policy/configuration material. |

No live mutation, restart, installation, edit, acknowledgement, or external
infrastructure validation is authorized by this ADR or its implementation tests.

## Alternatives considered

- **Continue relying on the QA guard.** Rejected: it is explicitly QA composition,
  not a production authorization boundary.
- **Let configured credentials authorize mutations.** Rejected: credential ability
  is broader than the product's deployment authorization decision.
- **Block by tool kind only.** Rejected: it cannot express an exact configured
  target and over-grants when an operation is suitable only for one target.
- **Add per-action confirmation now.** Deferred: it conflicts with ADR 0011's
  current no-approval-engine scope and needs a separate product/runtime design.
