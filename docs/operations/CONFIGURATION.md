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

## Project and session document uploads

`ORION_MAX_DOCUMENT_UPLOAD_BYTES` controls the maximum raw document upload size accepted by
the local API. The default is `4194304` bytes (4 MiB). The value must be a positive integer.
This raw upload bound is separate from Office archive member/expanded-size/compression-ratio
checks and from parser-specific PDF page/XLSX cell/extracted-text safety limits.

Supported local Knowledge upload formats are UTF-8 text/Markdown, PDF, DOCX, and XLSX.
Browser uploads use `multipart/form-data`; binary files are never decoded through `File.text()`
before transport.

## Model configuration

The primary M1 adapter is OpenAI-compatible. Configure it by either:

- setting `ORION_MODEL_BASE_URL`, `ORION_MODEL_ID`, and optionally
  `ORION_MODEL_API_KEY` before starting Orion; or
- creating saved model configurations through `POST /api/models` and selecting one active
  configuration through `POST /api/models/{model_config_id}/activate`.

The API accepts only connection information: `provider_type` (currently
`openai_compatible`), `base_url`, `model_id`, and an optional `api_key`. The key is
write-only in API responses.

The first saved model becomes active automatically. Adding later profiles preserves the existing
active model until it is explicitly changed. Orion blocks deletion of the active model; select a
different saved profile first.

## Internet integration

Internet search works out of the box through Orion's built-in bounded DuckDuckGo HTML search
client. Set `ORION_INTERNET_SEARCH_URL` only to override it with an administrator-chosen,
SearXNG-compatible JSON search endpoint (for example a locally operated SearXNG service).
The endpoint is server-side configuration; it is never supplied by the model or persisted in
chat state. Orion application health is a cheap process check and does not probe external tools.

The registered `internet.search` and `internet.fetch` operations have no credential or scope
arguments and there is no Internet toggle or tool picker. The model decides when Internet search
is useful; only then does the search query leave the local Orion machine. Arbitrary fetch URLs
are limited to public HTTP(S) targets; the configured SearXNG endpoint is intentionally
administrator-trusted and may be local.

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
registry used by Chat and Project. Unconfigured families are absent from that registry.
Tool execution activity and controlled tool errors are the product-visible evidence of
availability; Settings does not probe or toggle integrations.

## Remote file and document tools

Configured Linux targets expose bounded semantic reads for UTF-8 text, `.docx`, and `.xlsx`
through `linux.document.read`, plus structured verified edits through `linux.file.edit`.
Legacy `.doc`, `.xls`, macro-enabled `.docm`/`.xlsm`, invalid packages, and non-UTF-8 text
editing are rejected with controlled errors. Edits are applied in memory, uploaded to an
Orion-generated temporary file in the original directory, verified, atomically replaced, and
read back for final verification. Remote permissions continue to apply.

## Live QA

`make qa-smoke` and `make qa-full` are manual-only live commands, never dependencies of test,
lint, acceptance, CI, installation, packaging, or Orion startup. They run the current HTTP API in
an isolated temporary data directory; they do not use Docker or legacy endpoints. They require a
local active model profile or the `ORION_QA_MODEL_*` overrides. Reports are written under
`artifacts/qa/`; unavailable optional Linux, Grafana, and Zabbix suites are reported as `SKIP`.

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
