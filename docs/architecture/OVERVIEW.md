# Architecture Overview

## System flow

```text
USER
  |
  v
UI / API
  |
  v
SESSION + PROJECT CONTEXT
  |
  v
AGENT MODEL
  |
  |  FINAL / TOOL ACTION / CLARIFY / REFUSE
  v
CAPABILITY REGISTRY
  |
  v
PERMISSION + VALIDATION
  |
  v
TOOL RUNTIME
  |
  v
RESULT / EVIDENCE
  |
  +------------------------------+
  |                              |
  v                              |
AGENT MODEL <--------------------+
  |
  | repeat while useful
  v
FINAL DELIVERY
  |
  v
USER
```

A structured Event/Trace stream runs alongside the entire flow and feeds both
UI activity views and CLI/debug logging.

## Responsibilities

### UI / API

The UI and API accept user input, expose chat/project state, show agent
activity, collect write approvals, and deliver the final answer. They do not
interpret natural-language infrastructure semantics.

### Session and project context

This layer supplies bounded conversational context, Project references,
retrieval state, recent validated observations, and the current execution mode.
It does not decide what the user means.

### Agent model

The model owns natural-language understanding and reasoning. It decides whether
to answer directly, retrieve knowledge, call a tool, ask the user, refuse, or
continue investigating.

### Capability registry

The registry is the catalog of things Orion can do. Each capability declares
its identity, purpose, effect class, input schema, availability, target/source
requirements, and runtime binding.

### Permission and validation

This boundary converts an untrusted model proposal into either a rejected
action or a validated action. It enforces READ/WRITE policy, approvals,
registered identities, schemas, target/source authority, budgets, and safety.

### Tool runtime

The runtime executes only validated actions through reviewed implementations.
Secrets remain here or in secret/config providers and are never passed to the
model.

### Evidence

Tool outputs are normalized into compact, attributable observations with
status, time, source, target, freshness information, and relevant facts.

### Final delivery

The final boundary checks execution claims and response safety, performs
redaction, applies output limits, and publishes a safe trace projection.

## Central architectural rule

There is no semantic pre-router in front of the model for normal configured
agent requests.

Do not build a chain such as:

```text
intent detector -> target parser -> freshness regex -> source router -> model
```

The model performs language interpretation. Deterministic code validates
structured proposals after the model has made them.

## Machine-readable authority is different from language interpretation

Structured state supplied by the application can remain deterministic authority.
Examples include:

- current READ/RW mode;
- a typed Project identifier;
- a registered connection identifier;
- a user-approved write scope;
- a selected file supplied by the UI;
- execution budgets and policy.

These are not inferred from prose and do not violate the model-driven semantic
boundary.
