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

## Tools and secrets

M1 registers only `calculator.evaluate`, which needs no credentials. Future
integrations configure credentials outside model arguments and prompts. Configuration
determines whether an integration is registered; it never creates a per-chat tool
picker.
