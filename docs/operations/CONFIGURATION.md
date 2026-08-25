# Configuration

## Local database

`ORION_DATABASE_PATH` controls the SQLite database location. Otherwise Orion uses
`ORION_DATA_DIR/orion.db`; if `ORION_DATA_DIR` is unset the default is
`$XDG_DATA_HOME/orion` or `~/.local/share/orion`.

```text
~/.local/share/orion/orion.db
```

SQLite runs with WAL enabled. It persists model configuration, sessions, requests,
public timeline items, projects, document metadata, and indexed segments. Original
document blobs live beside it in `blobs/`; `orion.log` is a sanitized local diagnostic
log. Back up the whole data directory while Orion is stopped (or use SQLite's backup API).

## Model configuration

The primary M1 adapter is OpenAI-compatible. Configure it by either:

- setting `ORION_MODEL_BASE_URL`, `ORION_MODEL_ID`, and optionally
  `ORION_MODEL_API_KEY` before starting Orion; or
- creating one active model configuration through `POST /api/models`.

The API accepts only connection information: `provider_type` (currently
`openai_compatible`), `base_url`, `model_id`, and an optional `api_key`. The key is
write-only in API responses.

## Internet integration

Internet search is optional. Set `ORION_INTERNET_SEARCH_URL` to the administrator-chosen,
SearXNG-compatible JSON search endpoint (for example a locally operated SearXNG service).
The endpoint is server-side configuration; it is never supplied by the model or persisted in
chat state. When it is not configured, Chat, Project, documents, and calculator remain usable,
and `/api/integrations/internet` reports an `unconfigured` status. A configured
integration is reported as `healthy` only after its bounded provider probe succeeds;
otherwise it is `unhealthy` and local Orion features remain available.

The registered `internet.search` and `internet.fetch` operations have no credential or scope
arguments. Arbitrary fetch URLs are limited to public HTTP(S) targets; the configured search
endpoint is intentionally administrator-trusted and may be local.

## Tools and secrets

Calculator, knowledge, and Internet tools are registered through the common runtime. Future
integrations configure credentials outside model arguments and prompts. Integration
configuration never creates a per-chat tool picker.

## Infrastructure integrations

Linux, Grafana, and Zabbix are optional server-side integrations. Set
`ORION_INFRASTRUCTURE_CONFIG` to a local JSON configuration file. Its `targets` map
is grouped by integration family; each configured target has a safe `target_ref`, an
optional safe display name, a `credential_ref`, and family-specific connection fields.
Credential values live in the same server-side source under `credentials` (or can be
provided by the composition root in an embedding application); neither values nor
connection fields are model arguments, context, API responses, sources, activity, or
Settings state.

```json
{
  "credentials": {"linux-key": "server-side-value", "monitoring-api": "server-side-value"},
  "targets": {
    "linux": [{"target_ref": "production-node", "credential_ref": "linux-key", "host": "configured-host", "ssh_user": "configured-user"}],
    "grafana": [{"target_ref": "observability", "credential_ref": "monitoring-api", "base_url": "configured-url", "datasources": {"metrics": "prometheus"}}],
    "zabbix": [{"target_ref": "monitoring", "credential_ref": "monitoring-api", "base_url": "configured-url"}]
  }
}
```

Configured families register their full fixed semantic operation family in the same
registry used by Chat and Project. Unconfigured families are absent from that registry;
their sanitized health status is `unconfigured`. Configured families report `healthy`
only after a bounded probe succeeds, otherwise `unhealthy`; unrelated local tools and
Chat/Project remain available.

### Existing local deployment sources

As an alternative to `ORION_INFRASTRUCTURE_CONFIG`, Orion can adapt the server-side
`/etc/orion/tool-credentials.json` deployment file. Set
`ORION_TOOL_CREDENTIALS_PATH` to use a different server-side path. Its Grafana and
Zabbix entries supply only server-side connection/token material; Zabbix frontend
roots are normalized internally to their JSON-RPC endpoint and neither form is
public.

Linux targets may be ordinary OpenSSH aliases. Orion uses `ORION_SSH_TARGET_REFS`
(default `monitor`) as safe target references and lets the normal SSH client resolve
the alias from `ORION_SSH_CONFIG_PATH` (defaulting to the local OpenSSH config).
This avoids duplicating SSH host, user, or identity-file information into model-visible
configuration.
