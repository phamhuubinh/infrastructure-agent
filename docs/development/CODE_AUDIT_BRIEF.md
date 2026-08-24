# Deep code audit brief for the rebuild

## Objective

Analyze the entire existing repository against the new target architecture before large-scale implementation. Do not assume old abstractions should survive. The audit should answer what can be reused safely, what must be adapted, what must be rewritten, and what should be deleted.

## Required output

Produce a repository-wide disposition matrix with one row per meaningful module/subsystem:

```text
path/subsystem | current role | callers | state/data contract | security boundary |
KEEP / ADAPT / REWRITE / DELETE | target replacement | migration risk | tests
```

## Audit areas

### Model path

Trace provider config → adapter → prompt/context → model response parsing → tool calling. Identify any code that encodes the old decision/state protocol, repairs malformed model output, conflates selection with execution, or leaks provider types into core runtime.

### Runtime

Trace one user request from entrypoint to terminal response. Identify duplicate runtimes, semantic routers, legacy assessment/planning layers, retry loops, completion logic, and hidden state.

### Capabilities/tools

Inventory every real tool/integration and map it to a proposed CapabilityDefinition. Record current arguments, target/source assumptions, effect, credentials, executor code, output shape, and mutation risk.

### Authority/security

Find every place that validates or invents capability IDs, targets, sources, localhost defaults, aliases, permissions, approvals, credentials, network destinations, shell commands, and filesystem paths.

### Evidence

Trace executor output → normalization → persistence → model context → final answer. Find places where attempted execution is treated as success or evidence can be fabricated from prose.

### Persistence

Map session, message, event, approval, project/document, RAG, model config, target/source, and recovery storage. Identify transactional gaps and compatibility data that can be migrated or discarded.

### Backend/UI/CLI

Trace public contracts and determine which can remain stable while internals are replaced. Do not preserve an internal protocol solely because the UI currently depends on it; migrate the UI to typed timeline items.

### Tests/QA

Classify tests as target-contract tests, reusable component tests, old-protocol tests to delete, or tests needing rewrite. Identify generated fixtures that encode obsolete behavior.

## Required architectural review

For each subsystem, answer:

1. Does it fit the model-native tool loop?
2. Does it derive authority from canonical capabilities?
3. Does it keep secrets outside the model?
4. Does it have a bounded execution boundary?
5. Does it emit canonical evidence/events?
6. Does it create a second source of truth?
7. Can it be deleted instead of wrapped?

## No implementation during first audit pass

The first pass should produce the disposition and dependency graph. Do not begin shotgun edits before the replacement boundaries are understood.
