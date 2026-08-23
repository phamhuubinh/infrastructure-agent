# Target Code Layout

This is the intended dependency shape for the refactor. Exact filenames may
change when implementation proves a better split, but responsibilities should
remain separated.

```text
src/
├── agent/
│   ├── runtime.py              # bounded agent loop
│   ├── contracts.py            # decisions/actions/observations
│   ├── context.py              # bounded request/chat context assembly
│   ├── completion.py           # objective final checks
│   └── progress.py             # budgets/no-progress detection
│
├── models/
│   ├── base.py                 # provider-neutral model interface
│   ├── registry.py             # configured model connections
│   └── providers/              # real provider adapters only
│
├── capabilities/
│   ├── base.py                 # capability/tool contracts
│   ├── registry.py             # registration/discovery
│   ├── linux/                  # created because Linux exists
│   ├── grafana/
│   ├── zabbix/
│   ├── internet/
│   ├── project_knowledge/
│   └── calculator/
│
├── execution/
│   ├── validator.py            # exact authority + schema + permission
│   ├── permissions.py          # READ / RW+ASK / RW+FULL
│   ├── approvals.py            # scoped write approvals
│   └── executor.py             # dispatch validated actions only
│
├── evidence/
│   ├── contracts.py
│   ├── normalize.py
│   └── provenance.py
│
├── projects/
│   ├── service.py              # project/chat/file lifecycle
│   └── retrieval/              # current project retrieval implementation
│
├── sessions/
│   ├── store.py
│   └── memory.py               # recent turns + compact summary + refs
│
├── events/
│   ├── contracts.py
│   ├── emitter.py
│   ├── store.py
│   └── filters.py
│
├── security/
│   ├── secrets.py              # logical refs -> trusted secret material
│   ├── redaction.py
│   └── network.py
│
├── backend/                    # HTTP/API application boundary
└── cli/                        # CLI application boundary
```

## Dependency direction

```text
UI/API/CLI
   -> agent runtime
      -> model interface
      -> capability registry
      -> execution validator/executor
      -> evidence
      -> sessions/projects
      -> events

execution executor
   -> registered capability runtime

capability runtime
   -> external system / local OS / retrieval backend
```

Tools must not depend on agent-language semantics. Provider adapters must not
authorize actions. Project retrieval must not own chat orchestration.

## What not to recreate

Do not recreate separate core modules whose primary job is to interpret prose
before the model, such as:

```text
intent_resolver
target_semantic_parser
source_semantic_router
freshness_keyword_detector
mutation_keyword_router
followup_regex_selector
```

Exact registry lookup after a structured model proposal is valid and required;
natural-language routing before the proposal is not.

## Compatibility

Legacy modules can live in an explicit `legacy/` or compatibility area only if
they still have real callers during migration. They should not remain wired
into construction of the new configured agent merely for convenience.
