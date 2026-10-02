# Tools

## Rule

All registered/configured tools are automatically available to the model in both Chat and Project.

There is no manual tool selection in the conversation UI.

## Current repository families

```text
Knowledge / RAG
Calculator
Internet
Linux
Grafana
Zabbix
Scheduler
```

The exact callable functions/capabilities should come from tool registration code, not a duplicated hard-coded semantic router.

## Model-driven usage

Examples:

```text
"Summarize the attached proposal."
→ RAG/document tools

"Compare the project requirement with current Internet product specs."
→ project RAG + Internet

"Calculate usable capacity."
→ calculator

"Check CPU/memory on this configured host."
→ Linux

"Compare actual latency to the requirement."
→ Project RAG + Grafana

"Check active problems for that monitored host."
→ Zabbix
```

Orion dispatches what the model chooses.

Scheduler tools create and manage persisted tasks in the current Chat/Project scope.
Their unattended executions always use the same Chat runtime in read-only mode.
See [Scheduler v1](../architecture/SCHEDULER.md) for tool schemas and scheduling rules.
