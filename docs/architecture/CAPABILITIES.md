# Canonical capabilities

## Principle

Every executable operation is represented by one canonical `CapabilityDefinition`. This is the single source of truth from which model-facing schemas, authority validation, executor binding, result validation, and evidence projection are derived.

## Required fields

Conceptual shape:

```python
CapabilityDefinition(
    capability_id="host.service.restart",
    namespace="host",
    purpose="Restart a named service on an exact host target",
    effect="write",
    arguments_schema=...,
    target_policy=...,
    source_policy=...,
    permission_class="privileged_write",
    approval_policy="required",
    budget_cost=5,
    runtime_binding="host.service.restart.v1",
    result_schema=...,
    result_kind="operation_result",
    idempotency_policy="dedupe_exact_success",
    safety_reviewed=True,
)
```

## Identity

Capability IDs are stable, exact, lowercase identifiers. Do not use aliases at the authority boundary.

Recommended hierarchy:

```text
host.service.status
host.service.restart
host.cpu.inspect
grafana.query
zabbix.problem.list
internet.search
internet.fetch
compute.deterministic
project.search
project.document.read
```

## Arguments

- JSON-safe only.
- Closed schema: `additionalProperties=false`.
- Operation variants use discriminated `oneOf`/sum-type schemas rather than mega-objects containing unrelated nullable fields.
- No raw credential fields.
- No arbitrary shell command unless an explicit future capability is reviewed for that purpose.

## References

Target/source applicability is part of the capability contract.

- `target`: infrastructure object being acted upon, e.g. host.
- `source`: data/integration origin, e.g. Grafana or Zabbix connection.

A non-applicable reference is omitted from the model tool schema, not represented as nullable user/model input.

## Runtime binding

`runtime_binding` resolves through an `ExecutorRegistry`. The capability registry does not execute code itself. The executor receives an already-authorized request and must still enforce its local binding contract.

## Result contract

Each capability declares a bounded structured result schema. Executors cannot return arbitrary unbounded blobs directly to the model. Result validation precedes evidence creation.

## Registration

Calculator, Linux, Grafana, Zabbix, Internet, and future tools all register through the same capability abstraction. They may have different executors, but not different authority architectures.

## Review requirements

A capability cannot become executable until it has:

- stable ID;
- closed argument schema;
- explicit effect;
- target/source policy;
- permission/approval class;
- budget cost;
- executor binding;
- result schema/evidence projector;
- tests;
- safety review flag.
