# Scheduler v1

Scheduler executes persisted prompts through the composition root's existing
`ChatRuntime`, canonical registry, `ToolRunner`, context builder, request records,
and timeline. It runs inside `orion web`; it introduces no separate agent, process,
semantic router, or UI. Prompts remain ordinary untrusted user messages.

## Schedules

One-time input is `schedule_kind: "once"` with a timezone-aware RFC3339 `run_at`
(including seconds and optional fractional seconds). Orion persists its resolved
UTC instant. Naive dates, invalid timestamps and offsets are rejected. A past
instant is valid and executes once when reconciled.

Recurring input is `schedule_kind: "recurring"`, a five-field `cron`, and an explicit
IANA `timezone`. Fields are minute, hour, day-of-month, month, day-of-week. Supported
syntax: numeric values, `*`, comma lists, inclusive ranges, positive `/step` suffixes,
JAN–DEC and SUN–SAT names, and Sunday 0 or 7. Whitespace and names are canonicalized.
Seconds fields, macros and extended cron operators are rejected. Sets deduplicate
repeated values, so the grammar cannot schedule more frequently than once a minute.
When both day fields are restricted they combine with OR; wildcard day fields combine
with AND. Calendar searches are bounded to eight years, covering the longest leap-day
interval across a non-leap century; schedules with no occurrence are rejected at creation.

Evaluation uses timezone-aware local calendar minutes and UTC round trips. A
nonexistent DST minute is skipped. Both folds of an ambiguous minute execute, each
with a distinct UTC occurrence identity. A local daily schedule can therefore be
23 or 25 hours apart. `tzdata` is installed for systems without an OS IANA database,
including Windows.

`next_run_at` is UTC. The next occurrence is computed from the scheduled occurrence,
never from its completion. An overdue recurring task coalesces to its latest due
occurrence, then advances to the first future occurrence. Search walks calendar
days instead of replaying every missed minute. Resume preserves the saved occurrence
and applies this same coalescing rule.

## Persistence and recovery

The canonical SQLite store performs an additive `CREATE TABLE/INDEX IF NOT EXISTS`
migration; existing Chat rows are retained. `scheduled_tasks` contains:

- `task_id` primary key; `principal_id`, `workspace_id`, optional `project_id`;
- unique `execution_session_id` referencing `sessions`;
- bounded `prompt` (1–16,000 characters);
- `schedule_kind`, `run_at` OR `cron` + `timezone`, with an exclusive schedule check;
- `next_run_at`, `state` (`enabled`, `paused`, `completed`, `deleted`);
- `created_at`, `updated_at`, optional `deleted_at`.

`scheduled_runs` contains `run_id` primary key, `task_id`, `scheduled_for`, `status`
(`running`, `completed`, `failed`, `interrupted`), optional Orion `request_id`,
`started_at`, `completed_at`, and optional `error_kind` (64 characters maximum) /
`error_message` (512 maximum). No transcripts are copied. Task/due/history indexes,
`UNIQUE(task_id, scheduled_for)` and a partial unique index allowing only one
`running` row per task enforce the claim invariants.

Claiming uses `BEGIN IMMEDIATE` on the shared SQLite connection: select a due enabled
task, insert its unique `running` row, and advance `next_run_at` (or mark a one-time
task completed) in one transaction. Commit happens before `begin_scheduled` or model
execution. Failure to advance rolls back the reservation. A duplicate reservation
cannot execute again. A second `BEGIN IMMEDIATE` transaction creates a queued request
and links it to that running occurrence atomically, requiring exactly one previously
unlinked run in its dedicated session. Link failure rolls back request creation.
`begin_scheduled` adopts the persisted request and registers its pending prompt and
cancellation state in memory before the model loop starts. Scheduler history makes
the original `scheduled_for` and lateness inspectable.

Startup atomically fails queued/running requests linked from orphaned scheduler
`running` rows with a fixed bounded message and marks those runs interrupted without
retrying their occurrences. Already terminal requests retain their outcomes. It checks
task/session principal, workspace and project equality and live Project existence;
invalid enabled tasks are paused. Due valid tasks then
follow the coalescing rule. Scheduler reconciliation never modifies unrelated Chat
request rows or resumes lost in-memory prompts. Recurring failures preserve their
already saved next occurrence; interrupted one-time tasks require manual recreation.

Task deletion is soft deletion and retains the session/history on disk. Public
lookup/list/history exclude deleted tasks. Explicit deletion of the dedicated
session or its Project removes dependent task/run rows with `ON DELETE CASCADE`;
request references use `ON DELETE SET NULL`. Session/Project deletion and task
pause/resume/delete reject a running scheduler occurrence, including the interval
between reservation and request creation. Exhausted one-time schedules cannot be
paused/resumed. Pause/resume are otherwise idempotent.

## Scope and mutation governance

Creating scope is runtime-owned. Creation checks the source session inside the
transaction and atomically creates a fresh execution session with the same
principal/workspace/Project. Session attachments are never copied. Project
instructions/documents remain available through normal context and knowledge tools.
Every task lookup/mutation requires exact principal, workspace and Project equality;
plain Chat cannot inspect a Project task and one Project cannot inspect another.

`ChatRuntime.begin_scheduled` pins only that internal request to
`MutationMode.READ_ONLY`. Changing the stored dedicated session mode to `auto` or
`confirm` cannot weaken this boundary. All canonical tool schemas remain visible;
mutations receive the existing `operation_blocked` result through the existing
runtime governance path. A scheduled call never enters confirmation waiting.

Interactive task management uses ordinary conversation permissions. Read tools are
`scheduler.list`, `scheduler.get`, `scheduler.history`. Mutation tools are
`scheduler.create`, `scheduler.pause`, `scheduler.resume`, `scheduler.delete`.
Their closed schemas cannot accept principal, workspace, Project, or mutation-mode
overrides. Creation accepts `TaskInput`; lookup/mutations accept `task_id`; list and
history accept `limit` (default 50, maximum 100). Pending confirmation uses a fixed
internal `scheduler` target, the existing request/session/call/argument-digest binding,
and a safe action/identifier summary without the task prompt. The existing configured
server mutation ceiling remains fail-closed: an explicit infrastructure allowlist
blocks scheduler mutations; absent that ceiling, conversation mode governs them.

## Protected API

| Method | Endpoint | Input |
| --- | --- | --- |
| POST | `/api/scheduler/tasks` | JSON schedule + `session_id` |
| GET | `/api/scheduler/tasks` | query `session_id`, optional `limit` |
| GET | `/api/scheduler/tasks/{task_id}` | query `session_id` |
| POST | `/api/scheduler/tasks/{task_id}/pause` | query `session_id` |
| POST | `/api/scheduler/tasks/{task_id}/resume` | query `session_id` |
| DELETE | `/api/scheduler/tasks/{task_id}` | query `session_id` |
| GET | `/api/scheduler/tasks/{task_id}/history` | query `session_id`, optional `limit` |

The API derives scope from the authenticated principal's visible source session;
`session_id` selects that scope rather than changing task ownership. Direct API task
management is an explicit user operation, as with existing resource management APIs.
All seven routes are explicitly classified protected in the Remote Access inventory.
Remote mutations require exact Origin; unknown routes remain 404. Hidden tasks/scopes
return 404, active/exhausted conflicts 409, invalid schedules/limits 422. Public task
and history payloads use existing redaction; scheduler errors use fixed bounded text
rather than copying provider exceptions, credentials or transcripts.

## Lifecycle and validation

FastAPI lifespan starts one engine, reconciles persisted work and launches one
`asyncio` task. Its serial `tick` boundary reserves and awaits one occurrence at a
time. With no due work it waits on a task-change event until the next due UTC instant;
with no scheduled work it waits indefinitely for an event. Create, pause, resume and
delete wake that event. Shutdown wakes idle waits, cancels the current runtime request,
and drains the worker, with a five-second shutdown bound. Interrupted/cancelled
execution remains visible in scheduler history. The engine's clock and wake waiter,
and the service clock, are injectable for deterministic tests.

`backend/tests/test_scheduler.py` and `test_scheduler_api.py` cover calendar/DST,
migration, ownership, atomic rollback/uniqueness, coalescing, restart/interruption,
ordinary timeline references, Project context, forced read-only operation, interactive
permissions, API isolation/auth/Origin/limits, wake-up, shutdown and single execution.
The native Windows workflow runs these tests and the remote route-policy suite in
addition to its installer/release smoke scenarios.
