# Target code layout

The exact package names may evolve, but dependencies should point inward toward small canonical contracts.

```text
src/
  orion/
    contracts/
      model.py
      tools.py
      evidence.py
      authority.py
      events.py
    runtime/
      session_runtime.py
      context_builder.py
      tool_exposure.py
      no_progress.py
      completion.py
    capabilities/
      definition.py
      registry.py
      search.py
      targets.py
      sources.py
    authority/
      authorizer.py
      permissions.py
      approvals.py
      budgets.py
      policy.py
    execution/
      request.py
      registry.py
      isolation.py
      result.py
    evidence/
      store.py
      projector.py
      validation.py
    models/
      backend.py
      openai.py
      anthropic.py
      openai_compatible.py
    integrations/
      calculator/
      host/
      grafana/
      zabbix/
      internet/
      project/
    persistence/
      sessions.py
      events.py
      approvals.py
      evidence.py
      recovery.py
    api/
    cli/
```

## Dependency rules

- contracts depend on almost nothing;
- runtime depends on contracts and interfaces, not concrete integrations;
- capability registry contains metadata, not execution logic;
- authority does not call model or interpret prose;
- executors do not decide permission;
- integrations do not bypass evidence/event normalization;
- provider adapters do not own authority or retries;
- UI/backend never infer execution truth from assistant prose.

## Reuse existing code

Existing modules may be kept in place temporarily if they satisfy the new interface cleanly. Do not create wrapper chains solely to preserve old file paths. Once migrated, move or delete code based on clarity and dependency direction.
