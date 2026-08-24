# Configuration

## `.env.example`

The current `.env.example` contains operator-facing values for manually running Compose:

```text
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
ORION_API_KEY
ORION_TOOL_SECRETS_FILE
```

Do not document `API_PORT` or `DATABASE_URL` as current `.env.example` keys unless they are added to that file.

## Installer-managed `.env`

`./install.sh` creates/touches `.env` and ensures these values exist:

```text
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
ORION_API_KEY
ORION_TOOL_SECRETS_FILE
ORION_TOOL_SECRETS_GID
```

Missing PostgreSQL/API secrets are generated locally.

## Compose-derived runtime configuration

Some runtime values are assembled directly in `docker-compose.yml` rather than copied from `.env.example`.

Examples include the API database URL, RAG service URL, environment name, packaged Web URL, model host alias, and internal secrets path.

When documenting an exact runtime setting, verify whether it belongs to:

```text
.env
.env.example
docker-compose.yml
external tool-credentials file
persisted Orion model/application settings
```

Do not merge these into one fictional configuration surface.

## Tool credentials

Grafana/Zabbix secret material is stored outside model context in the configured tool-credentials JSON file.

Default installer path:

```text
/etc/orion/tool-credentials.json
```

The API container receives it through the Compose secret `orion-tool-credentials`.

## Model configuration

The installer may optionally add an existing OpenAI-compatible model endpoint interactively.

Models can also be configured later through the current Settings/CLI surface.

Model configuration commonly needs:

```text
connection name
provider
base URL
served model ID
API key when required
```

## RAG configuration

The current Compose defaults are local/minimal:

```text
RAG_EMBEDDING_PROVIDER=hash
RAG_VECTOR_STORE=memory
RAG_RERANKER=noop
RAG_OCR_PROVIDER=noop
RAG_DATA_DIR=/data
```

The target architecture may support additional embedding/vector/reranking implementations without changing Chat/Project semantics.

## Product principle

Configuration determines whether an integration is registered/available.

It does not create a per-chat tool picker.

Once a tool is registered/configured successfully, the model may use it automatically in both Chat and Project.

## Secrets

Keep credentials in local secret/configuration mechanisms.

Never place secrets in project documents, prompt templates, tool descriptions, or model-visible arguments unless the user explicitly asks to process a credential as data and the product has an intentional safe path for that case.
