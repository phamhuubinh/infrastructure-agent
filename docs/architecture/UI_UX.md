# UI and UX

## Goal

The interface should make Orion feel like one capable agent, not a collection
of separate backend modes. The user states the goal; the agent decides which
registered capabilities are useful.

## Primary surfaces

### Chat

Chat is the main agent interface. It contains:

- conversation;
- execution mode (`READ`, `RW + ASK`, or `RW + FULL`);
- agent activity timeline;
- write approval cards when required;
- source/evidence details on demand;
- clear failure/help states.

Tool selection is not a mandatory user workflow. Advanced controls may allow a
user to constrain the agent, for example "do not use Internet" or "use only
project documents", but these are optional constraints rather than required
modes.

### Projects

A Project provides:

- Project name/metadata;
- file/document management;
- retrieval/indexing state;
- multiple chats inside the Project;
- document-level visibility/provenance;
- Project-scoped search/analysis UX where useful.

The dedicated Project UI exists because document work is a primary Orion use
case, not because RAG is a separate agent architecture.

### Models and connections

Settings should make it easy to switch between local and cloud model
connections without changing agent behavior. Infrastructure/tool connections
are configured separately from model connections and never expose secret values
to the model.

### Logs / diagnostics

The UI should offer a request activity/debug view backed by the same event data
as `orion log`. A failed turn should make it possible to see whether failure
occurred in model generation, action validation, approval, tool execution,
retrieval, evidence handling, or final delivery.

## Activity timeline

Normal users should see short meaningful steps, not implementation noise:

```text
Searching project documents
Checking Grafana
Grafana timed out
Checking Zabbix
Comparing observations
Completed
```

Expanded details may show safe fields such as target, source, duration, result
count, and error code.

## Write approval UX

In `RW + ASK`, Orion presents a concise write scope before mutation. A useful
approval card answers:

- what will change?
- where will it change?
- why is it needed?
- what verification will follow?

One approval may cover a clearly declared related write batch. New writes
outside that scope require a new approval.

## Errors

Do not show generic "something went wrong" when a safe specific category is
known. Prefer actionable states such as:

- model unavailable;
- Grafana timeout;
- target unknown;
- write blocked in READ mode;
- approval required;
- project retrieval unavailable;
- agent stopped because no progress was made.

The model may then propose the best next step or ask the user for help.

## Token use and UI

The UI activity stream does not require injecting all event text back into model
context. Events are operational state. Only the bounded context useful for the
next model decision is sent to the model.

## Private reasoning

Never make raw private chain-of-thought a UI requirement. Show explicit action,
status, evidence, and short user-facing activity/reason summaries instead.
