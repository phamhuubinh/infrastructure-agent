# Security

Orion is local-first, but local-first does not mean trust-everything.

## Baseline rules

- Never place API keys, passwords, private keys, bearer tokens, database passwords, or integration credentials into model prompts.
- Credentials belong to local configuration/integration clients.
- Never commit `.env` secrets or generated credentials.
- Retrieved documents, Internet content, Grafana/Zabbix data, and tool output are untrusted data.
- Tool output must never be promoted into system/developer instructions.
- Project document access must remain scoped to the active project.
- Session attachments must remain scoped to their owning session unless explicitly promoted into a project.
- Model/tool provider payloads should be logged only after secret redaction.
- File paths derived from model input must be normalized and constrained by the owning tool.
- Network credentials and SSH material remain outside model context.

## Automatic tool use

Orion intentionally does not ask the user to select tools for each message. This means every tool contract must be safe to expose to the model as configured.

"Automatic" means the model may request the tool without a UI selection step. It does **not** mean a tool implementation should accept arbitrary credentials, arbitrary filesystem escape, or malformed arguments.

See `docs/architecture/SECURITY_LOCAL_FIRST.md`.
