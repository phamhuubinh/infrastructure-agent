# Agent Runtime

## Goal

The runtime should behave like a bounded modern agent: the model decides what
to do next, tools provide observations, and the model continues until it can
answer, needs the user, or cannot make useful progress.

## Decision types

The model-facing protocol should remain small and readable. A decision is one
of:

- **FINAL** — return an answer candidate;
- **ACTION** — propose one registered capability call;
- **DISCOVER** — request bounded information about available capabilities when
  progressive disclosure is used;
- **CLARIFY** — ask the user for missing information or help;
- **REFUSE** — explain that the request cannot be performed.

The transport format may evolve, but it should favor readable explicit field
names and simple closed schemas over cryptic token-saving keys or complicated
provider-specific schemas.

## Action content

An ACTION needs enough information for the harness to validate the model's
semantic choice without reparsing the original prose. Conceptually it contains:

```text
capability_id
target_ref      optional
source_ref      optional
arguments       typed object
activity_text   optional short user-visible status
```

`target_ref` and `source_ref` are proposals, not authority. The validator must
resolve them exactly against registered state.

## Loop

```text
build bounded context
      |
      v
model decision
      |
      +-- FINAL -----> completion/delivery
      |
      +-- CLARIFY ---> user
      |
      +-- REFUSE ----> user
      |
      +-- DISCOVER --> bounded capability metadata --> model
      |
      +-- ACTION ----> validate
                         |
                    reject/observe
                         |
                      execute
                         |
                     evidence
                         |
                    observation
                         |
                         +-----------------> model
```

The harness never automatically invents a semantic alternative after a rejected
model action. If an action fails, the model receives a compact observation and
chooses what to do next.

## Progress and circuit breakers

The model controls strategy; the harness controls resource bounds.

Limits are configuration, not semantic routing. They may include:

- maximum model calls;
- maximum tool actions;
- maximum discovery operations;
- maximum Internet operations;
- request deadline;
- context/token budget;
- maximum write scope size;
- maximum repeated no-progress states.

The runtime should detect obvious non-progress patterns such as repeating the
same action with the same result/error or cycling through the same state without
new evidence. The purpose is to stop loops, not to choose the correct semantic
path for the model.

When a circuit breaker fires, the model should receive a compact terminal or
near-terminal observation when practical so it can explain the problem or ask
the user for help.

## User-visible activity

The model/runtime may emit a short activity description for the UI, for example:

- "Checking Grafana metrics"
- "Searching project documents"
- "Comparing Linux and Zabbix observations"

This is not private chain-of-thought. Raw hidden reasoning is never required for
UI activity.

## Direct answers

If the model decides no tool is needed, it may answer directly. Orion should
not force every request through infrastructure, RAG, Internet, or calculator
logic.
