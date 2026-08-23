# Testing Strategy

Tests should prove both behavior and architecture boundaries.

## Contract tests

Verify canonical parsing/serialization for:

- FINAL / ACTION / DISCOVER / CLARIFY / REFUSE;
- target/source references;
- typed arguments;
- observations;
- event records;
- permission/effect modes.

Malformed model output fails closed.

## Validator tests

Cover:

- registered/unknown capability;
- registered/unknown target;
- registered/unknown source;
- invalid arguments;
- unavailable capability;
- READ in all modes;
- WRITE blocked in READ;
- WRITE approval required in RW+ASK;
- approved scope accepted;
- WRITE allowed in RW+FULL;
- no localhost/source fallback;
- budgets and safety controls.

## Agent-loop tests

Use deterministic fake models to cover:

- direct FINAL;
- discovery then action;
- action then observation then FINAL;
- multiple useful actions;
- rejected action then recovery;
- tool failure then alternate model strategy;
- CLARIFY;
- provider failure;
- no-progress loop breaker;
- budget exhaustion.

The harness should not semantically repair invalid actions.

## Capability tests

Each tool owns tests for:

- parameter schema;
- READ/WRITE effect correctness;
- transport behavior;
- parsing;
- typed failure results;
- secret redaction;
- target/source binding;
- safe handling of malformed external data.

## Project/RAG tests

Cover:

- document parse/index lifecycle;
- project isolation;
- document deletion;
- multilingual/Vietnamese retrieval;
- bounded retrieval size;
- document provenance;
- chat can retrieve active Project knowledge;
- another Project's data cannot leak;
- retrieval failure is explicit.

## Memory tests

Cover:

- recent-turn retention;
- summary compaction;
- token/context bounds;
- structured reference retention;
- dynamic evidence timestamp preservation;
- old dynamic evidence is not relabeled as fresh.

## Provider tests

Core agent tests use the provider-neutral interface. Each real provider adapter
gets focused tests for request translation, structured output, usage metadata,
timeouts, cancellation, and error normalization.

Run at least one live/native structured-output smoke test for the currently
supported provider/runtime combinations when credentials/runtimes are available.

## Event/trace tests

Verify:

- request correlation;
- action/tool/model lifecycle events;
- UI-safe messages;
- log filtering fields;
- failures produce useful error codes;
- secret values and private reasoning never appear.

## End-to-end QA

A release-quality run should include:

1. type checking/static checks;
2. unit/contract tests;
3. integration tests;
4. Docker/runtime startup;
5. model connectivity checks;
6. real READ investigation scenarios;
7. Project/RAG scenarios;
8. UI activity timeline;
9. `orion log` filtering;
10. WRITE approval scenarios when WRITE is enabled.

When a full QA run fails, isolate and fix the first real failure before treating
later cascaded failures as separate architecture problems.
