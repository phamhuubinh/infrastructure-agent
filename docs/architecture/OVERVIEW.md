# Architecture Overview

```text
USER
  ↓
UI / API
  ↓
SESSION + PROJECT CONTEXT
  ↓
AGENT MODEL
  ↓
FINAL / DISCOVER / ACTION / CLARIFY / REFUSE
  ↓
STAGE CONTRACT + CAPABILITY DISCLOSURE
  ↓
PERMISSION + EXACT VALIDATION
  ↓
TOOL RUNTIME
  ↓
RESULT / EVIDENCE
  ↘
   AGENT MODEL (repeat while useful and bounded)
  ↓
EVIDENCE-AWARE FINAL DELIVERY
  ↓
USER
```

A structured event/trace stream is the target common source for UI activity, diagnostics, and metrics.

## Responsibilities

### UI / API

Accept input, expose state, show activity, collect approval, deliver final output. They do not interpret infrastructure semantics. Persistent destructive UI actions require explicit confirmation. Background generation/timers are bound to the exact session + generation token that created them.

### Session/project context

Supplies bounded context, Project references, recent observations, configured model identity, and execution mode. Context uses one aggregate budget: preserve the complete valid current request, compact summary/structured state, then recent turns/attachments.

### Agent model

Owns language understanding and reasoning.

### Stage/disclosure contract

Progressive disclosure is explicit harness state. At each call, only a bounded set of decision kinds/identifiers is legal. Native JSON schema may guide generation; the harness validates the returned decision after generation.

### Capability registry

Catalog of reviewed operations, schemas, effects, target/source requirements, and runtime bindings.

### Permission/validation

Enforces active-stage legality, actual disclosed capability, exact identities, arguments, permissions, approvals, budgets, and safety. Malformed configuration fails closed.

### Tool runtime/evidence

Executes validated actions only. Evidence preserves status/time/target/source/provenance. Attempted/dispatched and successful evidence are distinct.

### Final delivery

Checks objective execution claims against structured evidence, deterministic result consistency, redaction/protected-information policy, and output/trace bounds without semantic re-routing.

## Central rule

No semantic pre-router such as:

```text
intent detector -> target parser -> freshness regex -> source router -> model
```

Structured application state (permission mode, Project ID, selected file, disclosed capabilities, configured model identity, budgets) is deterministic authority because it is not inferred from prose.
