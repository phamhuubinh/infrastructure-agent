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

## Local network/infrastructure tools

The current product direction does not require a complex approval engine for every automatic tool call. Tool implementations still own their normal argument validation, configured targets, credentials, and operational safety.

Infrastructure mutations are production read-only unless an exact operation and
configured target are authorized in trusted server configuration. Credentials do not
grant that product authority. See ADR 0013 for the bounded allowlist, failure,
audit, and non-goals contract; it does not add a per-action approval engine to
Chat/Project.
