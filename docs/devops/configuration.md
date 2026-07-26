# Configuration Error Handling Policy

Orion uses a consistent error handling policy across all 11 configuration sources. This document defines the policy for how configuration errors are detected, reported, and handled.

## Policy Overview

| Scenario | Behavior | Rationale |
|----------|----------|-----------|
| **Missing required config** | `MissingConfigFileError` → `SystemExit(1)` at startup | Fail fast, fail loud, fail with context |
| **Missing optional config** | Warning via `_warn()`, continue with safe defaults | Graceful degradation for non-critical configs |
| **Invalid config value** | `InvalidConfigValueError` → `SystemExit(1)` at startup | Report file, key, expected type, received value |
| **Missing required key** | `MissingRequiredKeyError` → `SystemExit(1)` at startup | Explicitly identify what key is missing |

## Error Collection

All configuration errors are collected before exit. The system does not fail on the first error — it validates all config sources, reports all errors together, then exits via `SystemExit(1)`.

## Required vs Optional Sources

### Required
- `servers.json` — Must exist and contain valid JSON with at least one server entry. Missing servers.json causes a fatal startup error.

### Optional (warn + safe default)
- `tools.json` — Warns if missing or invalid JSON; returns empty dict.
- `targets.json` — Warns if missing or invalid JSON; returns empty dict.
- `config/secrets.local.json` — Warns if missing or invalid JSON; returns empty dict.
- `config/conversational_patterns.yaml` — Returns safe defaults on any failure.
- `config/capability_plans.yaml` — Returns empty dict on any failure.
- `config/concepts.yaml` — Returns empty dict on any failure.
- `config/target_aliases.yaml` — Returns empty dict on any failure.
- `config/health_patterns.yaml` — Returns empty list on any failure.
- `ORION_*` environment variables — Optional; defaults provided in code.

## Error Format

All errors use the `ConfigurationError` hierarchy (`src/shared/config_errors.py`). Each error includes:

```
Configuration error in <file>:
  Key: <key>
  Expected: <expected_type_or_value>
  Received: <received_value>
```

This format is intentionally limited to 3 lines of context per error for readability.

## Error Subtypes

| Exception | When Used |
|-----------|-----------|
| `MissingConfigFileError` | Required config file does not exist |
| `InvalidConfigValueError` | Config value has wrong type, invalid format, or out of range |
| `MissingRequiredKeyError` | Required key is absent from config |

## Integration with Pydantic Validation (Task #002)

The Pydantic schemas in `src/shared/config_schema.py` handle type validation. When schema validation fails, errors are converted to `InvalidConfigValueError` instances with file, key, and expected/received context.

## Architecture

The error policy is applied in two layers:
1. **`OrionConfig.load()` in `src/shared/config.py`** — The unified config accessor (Task #003) collects all errors during loading and raises `SystemExit(1)` after reporting all errors.
2. **`runtime_factory.py`** — Uses `InvalidConfigValueError` for server lookup failures instead of generic `RuntimeError`.

## References

- Task #002: Config Schema Validation (Pydantic)
- Task #003: Unified Config Accessor
- Task #012: Config Error Handling Policy (this task)