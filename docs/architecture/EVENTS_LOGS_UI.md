# Events, Logs, and Agent Activity UI

## One event system

Orion should use one structured event/trace system for both:

- user-facing agent activity in the UI;
- technical debugging through logs/trace inspection.

Do not build two unrelated instrumentation systems.

## Event fields

Events should carry enough structured metadata for filtering, for example:

```text
timestamp
request_id
chat_id
project_id
component
event_type
status
model
capability
tool
target
source
duration_ms
error_code
safe_message
```

Only relevant fields need to be present for each event.

## Event examples

```text
request.started
model.started
model.decision
discovery.started
discovery.completed
action.proposed
action.rejected
action.approval_requested
action.approved
tool.started
tool.completed
tool.failed
evidence.created
model.final
request.completed
request.failed
```

## CLI logging

`orion log` should behave conceptually like a structured Linux log viewer: show
all events by default and allow useful filters.

The exact CLI syntax is implementation detail, but intended filters include:

```text
request
chat
project
component
model
tool/capability
target/source
status/error
since/until
follow
```

Examples of the desired UX:

```bash
orion log --request <id>
orion log --chat <id>
orion log --component model
orion log --tool grafana
orion log --status error
orion log --since 10m
```

Filters should be composable.

## UI timeline

The chat UI should render the same event stream in human-friendly form, for
example:

```text
✓ Searching project documents
✓ Checking Linux CPU
✗ Grafana timed out
✓ Reading Zabbix history
✓ Comparing evidence
✓ Completed
```

A user can expand a step to see safe operational details such as duration,
source, target, or error code.

## No raw chain-of-thought

Agent activity must not depend on displaying the model's private chain-of-
thought. The model/runtime can emit a short explicit activity/reason field that
is intended for the user.

## Retention

Event retention is configurable policy. The architecture requires structured
filterable events, not a particular retention duration.

## Debug traces

A request trace is a correlated view over events for one request. It should make
it possible to answer:

- which model calls occurred?
- which capabilities were proposed?
- which actions were rejected and why?
- which tools actually ran?
- what evidence was produced?
- where did latency occur?
- why did the request stop?

The same trace can back UI diagnostics and developer debugging at different
levels of detail.
