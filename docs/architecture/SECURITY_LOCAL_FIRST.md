# Local-first security

## Scope

Orion is primarily a local application with optional external integrations.

The security model should stay simple but real.

## Secrets

Secrets belong outside model context:

```text
.env / secret store / local integration configuration
                    ↓
              integration client
```

Never:

```text
credential
   ↓
model prompt
```

## Tool schemas

Because tools are automatically available to the model, every model-facing schema must be deliberately designed.

Do not expose secret fields when Orion can resolve credentials from local configuration.

## Files

Document tools must prevent path traversal and unauthorized cross-scope access.

Session files remain session-scoped.
Project files remain project-scoped.

## External content

Treat as untrusted:

- uploaded files;
- project documents;
- Internet pages;
- Grafana/Zabbix text fields;
- Linux command output;
- logs.

Untrusted text may inform the answer but cannot redefine Orion's system instructions.
The model must never follow instructions embedded in retrieved content. For fact-only requests,
including requests to repeat a fact verbatim, it should reproduce only relevant factual text,
not embedded instructions or their requested output payloads. If the user explicitly asks to
quote or analyze those instructions, they remain available as evidence for that task; quoting
them does not grant them authority.

Current tool results carry an Orion-owned `_orion_provenance.trust` value of
`untrusted_external_content` in model context, including when their data is compacted. An
identically named field inside retrieved data cannot overwrite this outer label. The canonical
document and ToolResult remain intact: no keyword-based instruction stripping is performed.
These are model-facing trust instructions, not a deterministic guarantee of model compliance;
live safety QA checks both fact extraction and explicit instruction analysis.

## Local network/infrastructure tools

Each Chat/Project conversation has a persisted mutation permission: read-only by
default, confirm each action, or auto allow. Confirmation pauses a validated exact
call before its handler and resumes the same request after a single user decision.
Tool implementations still own configured targets, credentials, validation and
operational safety. An explicitly configured `mutation_allowlist` is an additional
server ceiling; its absence adds no restriction. See ADR 0014.
