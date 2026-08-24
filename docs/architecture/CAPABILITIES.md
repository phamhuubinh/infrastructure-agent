# Capability and Tool System

A **tool** is an integration/runtime implementation. A **capability** is one specific reviewed operation exposed by a tool.

The model selects capabilities, never arbitrary shell/HTTP primitives.

## Required metadata

Stable ID, purpose, tool, READ/WRITE effect, closed argument schema, target/source requirements, availability, budget hint, result/evidence kind, activity label, runtime binding.

## Registration vs disclosure

Registration makes a capability known to the harness. It does **not** mean the model has seen it in the current turn.

```text
registered
  -> group disclosed
  -> exact capability summary disclosed
  -> selected detail/schema disclosed
  -> ACTION may propose that exact ID
  -> authority validation
```

At the first stage, the harness may disclose bounded **group-level** purposes
and result kinds to help the model decide whether to DISCOVER. This does not
disclose capability IDs, schemas, refs, or execution authority. For example,
the Calculator group advertises exact arithmetic as a deterministic result;
the model must still DISCOVER it before an ACTION can be proposed.

Do not retroactively treat an invented capability ID as disclosed merely because registry lookup succeeds.

## Implemented vs target families

Canonical Chat currently intends to expose configured/available Linux/SSH, Grafana, Zabbix, Internet, and Calculator capabilities.

**Project Knowledge/RAG is target-only for Chat at the current baseline.** The standalone `src/tool/RAGTool/` service is not yet registered as a Chat capability.

## Extension

Adding a tool should normally require runtime adapter + capability definitions/schemas + registration + tests + configuration. It should not require tool-specific semantic edits in the agent core.

Local deterministic tools use that same registration path. Calculator registers one
READ capability with an operation-discriminated closed argument schema; it has no
target or source authority.
