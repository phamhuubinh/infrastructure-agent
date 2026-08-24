# Target code layout

This is a clean target layout, not a requirement to preserve current module names.

```text
src/orion/
  app/
    config.py
    dependencies.py

  runtime/
    chat_runtime.py
    context_builder.py
    timeline.py
    streaming.py

  models/
    backend.py
    contracts.py
    registry.py
    providers/
      openai_compatible.py
      anthropic.py
      ...

  tools/
    contracts.py
    registry.py
    runner.py
    health.py
    knowledge/
    calculator/
    internet/
    linux/
    grafana/
    zabbix/

  knowledge/
    documents.py
    sources.py
    ingestion.py
    retrieval.py
    citations.py

  projects/
    service.py
    contracts.py

  persistence/
    sessions.py
    projects.py
    documents.py

  api/
    app.py
    sessions.py
    projects.py
    documents.py
    models.py
    health.py

ui/
tests/
```

## Dependency direction

```text
UI/API
  ↓
ChatRuntime
  ├── ContextBuilder
  ├── ModelBackend
  ├── ToolRegistry/ToolRunner
  ├── Session/Project stores
  └── Knowledge service
```

Tools depend on their integrations, not on semantic routers.

Project uses ChatRuntime rather than owning a second runtime.

## Migration rule

Current code can be reused if it cleanly implements one of these responsibilities. Old routing/protocol abstractions should not be preserved solely to reduce diff size.
