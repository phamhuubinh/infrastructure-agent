# Capability and Tool System

## Goal

New tools should be addable without editing the agent's semantic core. The core
should understand a generic capability contract, not hard-code knowledge of
every future integration.

## Capability vs tool

A **tool** is an integration/runtime implementation such as Linux/SSH, Grafana,
Zabbix, Project Knowledge, Internet, or Calculator.

A **capability** is one specific operation exposed by a tool, for example:

- inspect host CPU;
- read service state;
- query Grafana metrics;
- retrieve project chunks;
- search the Internet;
- fetch one public URL;
- perform a deterministic calculation.

The model selects capabilities, not raw commands or arbitrary HTTP requests.

## Required capability metadata

Every capability should declare at least:

- stable capability identifier;
- human-readable purpose and summary;
- owning tool/integration;
- READ or WRITE effect class;
- closed input schema;
- target kind, if any;
- source/connection kind, if any;
- availability/preconditions;
- cost/budget hints when useful;
- result/evidence kind;
- safe activity label;
- runtime binding.

Optional metadata may include alternatives, expected freshness, supported
platforms, or recovery hints, but metadata must not become a second natural-
language router.

## Registration

A new tool should normally require only:

1. implement its runtime adapter;
2. define its capabilities and schemas;
3. register them;
4. add tests;
5. add user-facing configuration if required.

The model controller, permission engine, event system, and generic executor
should not require tool-specific semantic edits.

Do not create empty directories for hypothetical future tools. Create a module
when a real tool is added.

## Current families

### Linux / SSH

Provides host observations and, when WRITE mode is intentionally implemented,
reviewed host mutations. READ may include any reviewed command whose effect is
observation only.

### Grafana

Provides monitoring/dashboard/metric/alert observations through registered API
operations. Future writes must be explicitly marked WRITE.

### Zabbix

Provides monitoring inventory, history, trigger/event, and related observations.
Future mutations must be explicitly WRITE.

### Project Knowledge / RAG

Retrieves relevant material from the active Project. It is a capability inside
the same agent loop, not a separate reasoning mode.

### Internet

Provides bounded public search and URL fetch. The runtime retains network safety
controls independently of the model.

### Calculator

Provides deterministic computation as an ordinary registered capability. It
uses the same action/observation protocol even though it does not access an
external service.

## Commands and raw HTTP

The model must not gain arbitrary shell or arbitrary HTTP authority simply
because a tool internally uses shell or HTTP.

A READ capability may execute a reviewed read-only command. A WRITE capability
may execute a reviewed mutation only if permission allows it. The runtime owns
the actual command/API implementation.

Generated shell commands, config snippets, or code shown in chat are content,
not execution authority.
