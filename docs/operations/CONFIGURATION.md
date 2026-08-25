# Configuration

## Local database

`ORION_DATABASE_PATH` controls the SQLite database location. Its M1 default is:

```text
./data/orion.db
```

SQLite runs with WAL enabled. It persists model configuration, sessions, requests,
and public timeline items.

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
and `/api/integrations/internet` reports an `unavailable` status.

The registered `internet.search` and `internet.fetch` operations have no credential or scope
arguments. Arbitrary fetch URLs are limited to public HTTP(S) targets; the configured search
endpoint is intentionally administrator-trusted and may be local.

## Tools and secrets

Calculator, knowledge, and Internet tools are registered through the common runtime. Future
integrations configure credentials outside model arguments and prompts. Integration
configuration never creates a per-chat tool picker.
