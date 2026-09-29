# ADR 0014 — Conversation mutation permissions

## Status

Accepted. Supersedes ADR 0013's absent-allowlist read-only rule and ADR 0011's
deferred approval-engine statement. Their tool contracts and mutation execution
lifecycle still apply.

## Decision

Each Chat or Project session owns one persisted `mutation_mode`: `read_only` by
default, `confirm`, or `auto`. The application UI and session API change this
value. Model prose, Project instructions, tool arguments and tool results cannot.
The mode is read once when a request starts; changes during an active request are
rejected. A mode change on a draft conversation creates its session immediately.

All registered tools retain their ordinary first-turn schemas. The model chooses
whether to call one. Before a mutation handler runs, Orion validates the registered
tool, closed arguments, configured target and any explicit server ceiling. Then:

| Session mode | Result |
| --- | --- |
| `read_only` | Return `operation_blocked` with model-visible guidance; reads continue. A repeated identical authorization block converges immediately after its correlated result. |
| `confirm` | Persist one pending record, emit `tool.authorization_required`, and pause this exact call. `allow` executes it once; `deny` returns deterministic feedback to the same model loop. |
| `auto` | Dispatch an eligible mutation through the existing handler lifecycle with no per-call prompt. |

An absent `mutation_allowlist` adds no server restriction. If present, it is an
additional exact `(tool_name, target_ref)` ceiling; an empty list denies every
mutation in all three modes. Invalid entries fail startup. Operators using this
ceiling must explain that a selected UI mode can still be denied by server policy.
Configured credentials alone never establish a target or bypass the mode.

Within one request, Orion records a normalized fingerprint of each deterministic
authorization block: registered tool name, SHA-256 of canonical arguments, and
reason (`read_only`, user denial, or server policy). A second matching mutation
gets a correlated `operation_blocked` result without a handler call or another
confirmation prompt, then proceeds to a terminal recovery turn. Different
mutations and permitted reads retain their normal paths. The generic repeat
tracker remains unchanged for unrelated recoverable failures.

## Confirmation and persistence

A pending record binds `request_id`, model `call_id`, `session_id`, registered tool,
configured target, and SHA-256 of canonical JSON arguments. It stores a bounded
tool-specific summary with selected safe identifiers such as a path or service,
never the full argument object, file content or credentials. The live runtime
retains the already validated call; the decision API cannot submit replacement
arguments. A compare-and-set transition accepts only the first decision for that
session/request/call. Unknown, cross-session, stale, cancelled and duplicate
decisions fail. A denial has no side effect. An approval uses the existing
preflight, dispatch, cancellation, deadline and verification path. No mutation is
silently retried.

Human wait time shifts the request's work and absolute mutation-drain deadlines;
model/tool execution time remains bounded. Cancellation interrupts a pending wait.
The synchronous message endpoint rejects confirm-mode requests; callers use the
streaming endpoint to receive the request and pending call identifiers.
Pending calls cannot be resumed after a process restart because the model loop and
validated call are gone; startup marks them expired and their requests failed,
without replay. The canonical timeline keeps the tool call/result correlation.

Audit events contain request and call identity, tool, mutation kind, safe configured
target, session mode and outcome (`blocked`, `pending`, `allowed_by_user`,
`denied_by_user`, `auto_allowed`). They do not contain secrets or raw arguments.

Only accepted presentational `assistant.message` turns enter the visible chat
messages. Streamed deltas are provisional model-turn data, so tool-turn prose does
not appear as an answer and disappear during recovery.

Project documents remain Orion-owned knowledge. A filename alone is not a remote
Linux path; without a registered Project-document mutation tool, Orion must say
that editing a Project document is unsupported.
