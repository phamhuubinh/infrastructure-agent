# Permission and Autonomy Model

## Effect classes

Orion intentionally keeps permission classification simple.

### READ

A READ action observes or retrieves data without changing external state.

Examples include:

- reading a file;
- reading logs;
- querying a database without mutation;
- inspecting CPU, RAM, disk, process, service, or network state;
- `git status` or `git log`;
- `docker ps` or service status queries;
- querying Grafana or Zabbix;
- Internet search/fetch;
- Project/RAG retrieval;
- deterministic calculation.

READ is about **effect**, not transport. A shell command may be READ if the
reviewed capability guarantees observation-only behavior.

### WRITE

A WRITE action creates, changes, deletes, restarts, deploys, installs, or
otherwise mutates state.

Examples include:

- creating, editing, or deleting files;
- writing to a database;
- starting/stopping/restarting a service;
- installing packages;
- changing configuration;
- deploying software;
- creating or modifying remote resources;
- mutating monitoring configuration.

## User modes

### READ

- READ actions: allowed automatically.
- WRITE actions: blocked.

### RW + ASK

- READ actions: allowed automatically.
- WRITE actions: require approval.

### RW + FULL

- READ actions: allowed automatically.
- WRITE actions: allowed automatically after normal validation.

The mode controls execution only. The model may still recommend a write in READ
mode.

## Approval scope

For `RW + ASK`, approval should be practical rather than noisy. Orion may ask
for approval for one declared group of related write actions, for example:

```text
Edit nginx config on staging, restart nginx, then verify health.
```

Approval is scoped to the declared goal, targets, and write capabilities. A new
write outside that scope requires another approval. READ verification after an
approved write does not require another approval.

## Validation order

A model proposal must be treated as untrusted until the harness confirms:

1. capability exists;
2. capability is available;
3. target/source references resolve exactly when required;
4. arguments satisfy the capability schema;
5. effect class is permitted by the current mode;
6. ASK approval covers the write when required;
7. safety and resource limits permit execution.

No fuzzy target fallback, silent source fallback, or default localhost target is
allowed as authorization behavior.

## Policy must not depend on language keywords

Read/write safety cannot rely on recognizing words such as `restart`,
`khởi động lại`, or equivalents in every language.

The capability's declared effect and runtime behavior are the authority.
Natural-language mutation detection may be used only as optional defense-in-
depth or user messaging; it must not be the primary permission boundary.
