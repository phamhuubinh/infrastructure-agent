# Security and Secret Boundary

## Secret rule

> **The model never receives credentials.**

API keys, passwords, SSH private keys, bearer tokens, and similar secrets stay
on the machine running Orion and are resolved only by trusted runtime
components.

## Secret references

The model may see safe logical identifiers such as:

```text
grafana-prod
zabbix-main
monitor
staging-db
```

It should not need to know the secret value or, where avoidable, the secret's
filesystem path.

The runtime maps logical connection/tool identifiers to local configuration,
SSH config, environment variables, private files, OS secret stores, or another
trusted provider.

## Tool isolation

The model selects a registered capability. It does not receive arbitrary:

- shell execution;
- filesystem mutation;
- HTTP requests;
- database queries with unrestricted effects;
- credential lookup;
- registry modification.

Any powerful primitive used internally by a tool remains behind a reviewed
capability boundary.

## Network safety

Internet and remote-access tools retain deterministic controls appropriate to
their transport, including where relevant:

- public/private address policy;
- DNS and redirect validation;
- request timeouts;
- response-size limits;
- bounded retries;
- target allowlists/registries;
- credential scoping.

These controls are independent of model reasoning.

## READ/WRITE enforcement

The declared capability effect is checked before execution. Runtime
implementations must match their declared effect. A capability declared READ
must not mutate external state.

Tests should explicitly verify the effect boundary for high-risk capabilities.

## Logs and traces

Secret values, raw authorization headers, private keys, passwords, and private
chain-of-thought must not appear in public traces or normal logs.

Structured logs may include safe connection identifiers, action IDs, error
codes, timings, and redacted evidence summaries.
