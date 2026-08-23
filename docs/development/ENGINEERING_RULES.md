# Engineering Rules

These rules are normative for the refactor.

## 1. Model semantics, deterministic authority

For normal configured requests, do not parse natural-language intent, target,
source, freshness/currentness, follow-up meaning, or capability choice in code
before the model in order to choose an execution path.

The model proposes. The harness validates.

## 2. Natural-language text is not authority

Only structured validated state can authorize execution. Never execute shell,
HTTP, database, file, or infrastructure operations directly from generated
text.

## 3. READ and WRITE are effect classes

Every executable capability declares READ or WRITE. A READ implementation must
not mutate state. Permission checks happen before execution.

## 4. No silent identity fallback

Unknown targets, sources, connections, or capabilities fail explicitly. Do not
silently map an unknown target to localhost or a missing source to another
source.

## 5. Provider-neutral core

Vendor-specific model behavior stays in provider adapters. Core agent semantics
must not depend on one vendor's prompt format or schema extension.

## 6. Secrets never enter model context

Keep credentials in trusted runtime/config/secret providers. Pass only safe
logical references to the model.

## 7. Tools own integrations

Commands, API endpoints, parsing, transport policy, and tool-specific behavior
belong to tool modules. The agent core should not duplicate them.

## 8. Evidence remains explicit

Do not convert failure, missing data, or stale data into healthy-looking facts.
Keep target/source/time/provenance with observations.

## 9. Dynamic data is not timeless memory

Previous dynamic observations may be retained as history, but do not silently
represent them as current.

## 10. One event model

UI activity and technical traces derive from the same structured event stream.
Do not create separate inconsistent logging semantics.

## 11. No private reasoning logs

Do not persist or expose raw chain-of-thought. Record decisions, actions,
statuses, evidence summaries, timings, and explicit activity messages instead.

## 12. Keep modules small and directional

Avoid a giant Agent class that owns model routing, session semantics, tool
execution, RAG, evidence, finalization, and legacy behavior together. Each
module should have one clear responsibility and dependencies should point from
orchestration toward interfaces/runtime services, never from tools back into
agent semantics.

## 13. Legacy code is temporary

Compatibility code may remain while real callers exist, but it must be isolated
from the new configured hot path. Delete it once caller analysis and tests show
it is unused.

## 14. No speculative scaffolding

Design interfaces for extension, but do not create empty future-tool folders,
stub services, or unused abstraction layers.

## 15. Tests enforce architecture

Architecture rules that can regress should have tests: no semantic pre-router,
no default target fallback, exact action validation, effect permissions, secret
redaction, provider-neutral contracts, bounded loops, project isolation, and
structured events.
