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
