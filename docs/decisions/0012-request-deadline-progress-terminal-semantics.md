# ADR 0012 — Request deadline, progress, and terminal semantics

## Status

Proposed. This is a target contract for later, separately reviewed implementation
issues. It does not change the current runtime, API, provider adapter, or request
storage status by itself.

## Context

The current runtime permits an unlimited useful model/tool chain and has local
provider and tool timeouts. It also has a narrowly defined repeated recoverable
failure check. Those facts do not yet specify one request-wide time budget, what
counts as objective recovery progress, or how a request closes if a final model
turn cannot be obtained. Treating a changed argument, another tool name, or a
retrieval timestamp as automatic progress makes recovery loops invisible; treating
every repeated read as a loop makes legitimate polling and verification impossible.

This decision defines internal runtime control semantics only. It must not become a
model-visible ACTION/OBSERVATION state machine, a semantic pre-router, a manual tool
picker, or a product-level tool-call quota.

## Decision

### One monotonic request budget

When a queued request obtains its session lock and changes durably to `running`,
Orion records `started_monotonic` and derives one `deadline_monotonic`. Queue wait is
not part of this budget. Everything after that transition is: persisting the user
item, preparing conversation state, context construction, each model turn, each
tool dispatch and its required verification, and terminal persistence/emission.
Wall-clock time is for display only and must not decide expiry.

The implementation configuration contract is:

| Setting | Default | Allowed value | Meaning |
| --- | ---: | --- | --- |
| `ORION_REQUEST_DEADLINE_SECONDS` | 120 | 10–900 seconds | Total time from durable `running` to a terminal outcome. |
| `ORION_REQUEST_FINALIZATION_RESERVE_SECONDS` | 5 | 1–60 seconds; strictly less than the request deadline | Time retained for deterministic terminal persistence, events, and fallback. |
| `ORION_MODEL_STREAM_TIMEOUT_SECONDS` | 30 | 1–300 seconds | Provider transport inactivity limit for connect/read/write/pool work; it is not the total request deadline. |
| `ORION_RECOVERY_REPEAT_LIMIT` | 3 | 2–5 | Repetitions of the same recoverable state before recovery is exhausted. |
| `ORION_RECOVERY_CYCLE_REPEAT_LIMIT` | 2 | 2–5 | Repetitions of a multi-state recoverable cycle before recovery is exhausted. |

Invalid values or invalid cross-setting combinations fail configuration validation at
startup; they are never silently clamped. The total default gives a local model time
to make useful multi-step work while bounding a stuck request. The small reserve
avoids spending the entire request budget in a last provider call. The transport
limit remains shorter because it diagnoses inactive I/O, whereas an active stream
may legitimately last longer than 30 seconds. `ORION_QA_REQUEST_TIMEOUT_SECONDS` is
test-runner-only and must never supply any production default or policy.

Every awaited request operation receives both the cancellation signal and the common
monotonic deadline. Its effective local timeout is no greater than the remaining
budget, and a provider transport timeout is additionally capped by the configured
inactivity limit. A timeout wrapper must cancel and await its child before proceeding
to terminalization so it cannot later emit a model delta, dispatch a tool, or write a
second terminal result. Synchronous durable finalization is bounded by the reserved
time operationally; if persistence itself cannot be confirmed, recovery is a process
integrity concern rather than permission to resume the request.

No optional model turn or new tool dispatch may start once remaining time is at or
below the finalization reserve. Work already past an infrastructure mutation's
side-effect boundary follows the mutation rules below instead of being described as
never started.

### Internal lifecycle and terminal gate

The following is an internal runtime lifecycle, not context supplied to the model.
`TERMINALIZING` is a closing gate, not a new model protocol state.

| From | Event / guard | To | Required effect |
| --- | --- | --- | --- |
| `QUEUED` | session lock acquired | `RUNNING` | Atomically mark running and create the monotonic deadline. |
| `QUEUED` | cancellation wins before start | `CANCELLED` | Persist one cancellation outcome; no model or tool work starts. |
| `RUNNING` | useful model/tool work | `RUNNING` | Continue only while budget remains above reserve. |
| `RUNNING` | model returns a valid final assistant answer | `TERMINALIZING` | Stop accepting tool dispatch; validate and persist the final answer. |
| `RUNNING` | deadline expires, or remaining time reaches reserve | `TERMINALIZING` | Do not start another model/tool operation; select deterministic incomplete fallback. |
| `RUNNING` | cancellation before a mutation side-effect boundary | `TERMINALIZING` | Stop dispatch and select cancelled outcome. |
| `RUNNING` | cancellation after a mutation side-effect boundary | `TERMINALIZING` | Preserve the dispatched call's verified or `outcome_unknown` ToolResult, then cancel the request. |
| `RUNNING` | hard non-timeout runtime/provider failure | `TERMINALIZING` | Persist a redacted failure outcome. |
| `TERMINALIZING` | exactly one terminal persistence succeeds | `COMPLETED`, `INCOMPLETE`, `FAILED`, or `CANCELLED` | Emit exactly one matching terminal event and release request resources. |

The terminal gate has one idempotent winner. After entry to `TERMINALIZING`, Orion
does not invoke `ToolRunner`, expose/re-expose a tool, or resume the ordinary model
loop. Late stream events are discarded. A provider that returns tool calls while
Orion is collecting a single permitted forced final answer receives no tool result:
those calls are never dispatched. If that forced turn lacks a valid assistant answer,
or it runs out of budget, Orion uses the deterministic incomplete fallback.

`COMPLETED` means a valid persisted assistant final answer. `INCOMPLETE` means Orion
persisted a fixed, data-free fallback explaining that it could not obtain a complete
answer before the deadline or a required final turn; it must not claim a tool result
or citation that was not observed. `FAILED` is a non-cancellation, non-deadline
runtime failure for which no incomplete fallback is selected. `CANCELLED` records
the user's cancellation. Request persistence/API contracts must carry this distinct
terminal outcome rather than encoding incomplete work as successful assistant prose.

### Objective recovery progress and cycles

Recovery tracking applies only to unresolved recoverable states, never as a count of
all model or tool calls. A recovery state is the canonical tuple of operation name,
canonical arguments, result class/error code, and the current recovery barrier. A
barrier advances only on independently observable information, for example:

- a new user message, attachment, bound scope, or explicit authorization/evidence
  version;
- a successful result with a new source/version/cursor/ETag/sequence value that is
  relevant to the unresolved fact; or
- a documented verification observation that confirms a changed target state.

Changing an argument, selecting another tool, reordering calls, or receiving a fresh
retrieval timestamp is not alone a barrier. A success without a relevant version or
evidence identity is not automatically proof of progress either.

Within one barrier, Orion classifies a recoverable transition as follows:

| Classification | Evidence | Runtime treatment |
| --- | --- | --- |
| `confirmed_progress` | A new barrier is observed. | Reset recoverable repeat/cycle tracking. |
| `confirmed_no_progress` | The same normalized recoverable state recurs, or a normalized sequence of two or more recoverable states repeats with no new barrier. | Count the state or shortest repeating cycle. |
| `unknown_progress` | The result lacks enough stable evidence to compare (including an interrupted/ambiguous read). | Preserve the result and return control to the model; do not count it as stalled. |

For a multi-state cycle, Orion normalizes the shortest repeating sequence of two or
more recoverable states, such as `A → B → A → B`. The sequence becomes exhausted
only at `ORION_RECOVERY_CYCLE_REPEAT_LIMIT` complete repetitions with the same
barrier. A single repeated state uses `ORION_RECOVERY_REPEAT_LIMIT`. This is a
bounded recovery guard, not a total tool-call quota: a long useful chain can continue
without limit, and a model remains the semantic decision-maker.

Repeated reads can be valid polling or required verification. A stable snapshot may
be meaningful evidence that verification ran, but does not itself establish either
progress or a stall. It is returned to the model and may be represented as
`unknown_progress` unless the operation contract supplies a stable comparison that
proves the same unresolved recoverable state. Ordinary reads that are not in a
recoverable-error cycle must never be terminated merely because they look similar.

When a state/cycle is exhausted, Orion enters a bounded closing path: it may make one
final model turn with ordinary tools unavailable solely to ask for an explanation or
needed input, provided the finalization reserve permits it. It cannot return to the
ordinary loop. A tool call from that turn is ignored and produces the incomplete
fallback described above.

### Cancellation, timeout, and side effects

Cancellation is an externally requested stop; deadline expiry is Orion's watchdog.
They have separate terminal reasons and telemetry. If both are observable, the first
monotonic signal wins; an already-entered terminal gate cannot be replaced.

For read-only operations, cancellation/deadline cancels the awaited work and prevents
further dispatch. For a mutation, `ToolRunner` must check cancellation and remaining
budget immediately before its documented side-effect boundary. Before that boundary,
it returns `cancelled` and no side effect is claimed. Once the semantic request has
been issued, neither cancellation nor timeout may label the mutation as unperformed,
retry it transparently, or replay it in another request. Orion persists the resulting
verification evidence. If it cannot establish final state, the canonical result is
`outcome_unknown`, with any safe verification detail retained, before the request
closes as cancelled or incomplete as applicable.

## Acceptance matrix and synthetic traces

These traces are review evidence for this proposed contract; they are not a request
to add test code in this issue.

| Trace | Expected outcome | Must not happen |
| --- | --- | --- |
| Long useful tool chain | Each call adds a relevant barrier; chain continues while the deadline permits, then completes normally. | A fixed model/tool-call count terminates it. |
| `A/B` recoverable error cycle | With no barrier, the normalized `A,B` cycle exhausts at the configured limit; at most one tool-free final turn is allowed. | Treating different tool names as automatic progress or dispatching a final-turn tool call. |
| Stable snapshot verification | The repeated snapshot is preserved; comparison is unknown or operation-defined, and model may finish/continue. | Declaring a stall solely from the read/timestamp repetition. |
| Provider hangs or never produces final turn | Common deadline/inactivity handling cancels the child; one `INCOMPLETE` fallback/event is persisted. | A second terminal event, late delta, or another tool dispatch. |
| User cancels before dispatch | One `CANCELLED` outcome; no side effect. | Calling the tool after cancellation. |
| User cancels after mutation dispatch | Tool result contains verified evidence or `outcome_unknown`; request closes cancelled. | Recording the mutation as not attempted, retrying, or replaying it. |

## Required follow-up after acceptance

No implementation may begin on the strength of this proposed ADR alone. Explicit
acceptance and dependency sequencing are required. The implementation work must at
least make these coordinated documentation/contract changes before or with code:

| Area | Required change |
| --- | --- |
| `docs/architecture/CONTRACTS.md` | Define request terminal outcome/status, incomplete fallback identity, deadline/cancellation telemetry, and preservation of post-boundary mutation evidence. |
| `docs/architecture/FAILURE_RECOVERY.md` | Replace the current changed-name/argument/error-code progress wording with barrier and multi-state-cycle semantics. |
| `docs/architecture/MODEL_TOOL_LOOP.md` and `CHAT_RUNTIME.md` | State the internal-only closing gate and that it does not impose a tool-call quota or model-visible FSM. |
| `docs/architecture/MODEL_BACKENDS.md` and operations/configuration documentation | Define request-deadline versus provider inactivity settings, validation, and local-first defaults. |
| Runtime, persistence, API/event, provider, and tool-runner implementation issues | Thread one deadline/cancellation controller through every await, provide atomic terminal persistence, preserve mutation uncertainty, and add offline fake-clock/scripted-backend/mock-transport traces. |

The existing `recovery_pending`, `capability_action_pending`, and
`recovery_exhausted_next` implementation details are not themselves this contract.
Follow-up code may replace them only while preserving the accepted semantics above.

## Consequences
- Chat and Project retain the same `ChatRuntime`, canonical registry, `ToolRunner`,
  `RuntimeScope`, and provider-neutral model contracts.
- Model-controlled registry-derived progressive tool exposure remains unchanged;
  terminal gating only stops dispatch after Orion has decided to close a request.
- No keyword, intent, or regex semantic router and no manual tool picker is added.
- A request deadline bounds elapsed work, not semantic usefulness, and therefore is
  not a substitute for provider, tool, or infrastructure-operation timeouts.
- Offline synthetic traces can establish control-flow behavior; they do not prove
  deployed-model answer quality or live stability.
