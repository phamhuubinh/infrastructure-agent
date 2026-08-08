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
- No model configuration is required to install or start Orion.

### Optional (warn + safe default)
- `servers.json` / `ORION_SERVERS_FILE` — Model registry. A missing file is created as an empty registry; zero model entries is valid setup mode.
- `tools.json` — Tracked non-secret tool registry; warns if missing or invalid JSON and returns an empty dict.
- `targets.json` — Warns if missing or invalid JSON; returns empty dict.
- `/etc/orion/tool-credentials.json` or `ORION_SECRETS_PATH` — System-wide deployment tool URLs/tokens; returns an empty dict when absent or invalid. Docker maps the host path selected by `ORION_TOOL_SECRETS_FILE` to the runtime path.
- `config/conversational_patterns.yaml` — Returns safe defaults on any failure.
- `config/capability_plans.yaml` — Returns empty dict on any failure.
- `config/concepts.yaml` — Returns empty dict on any failure.
- `config/target_aliases.yaml` — Returns empty dict on any failure.
- `config/health_patterns.yaml` — Returns empty list on any failure.
- `ORION_*` environment variables — Optional; defaults provided in code.

## Deterministic reasoning rollout flags

`config/feature_flags.yaml` is an optional, strict configuration file used
while rolling out deterministic reasoning and general-agent routing. An
absent file keeps the historical DR1 evidence flags off and keeps the shipped
GA1 route controls on. A current-information request whose GA1 web controls
are disabled fails as unverified; it never falls back to an ungrounded current
answer.

```yaml
schema_version: rollout.v1
structured_command_result: true
canonical_facts: true
composite_rules: true
claim_guard: true
general_agent_routing_v1: true
external_verification_v1: true
web_search_v1: true
source_constraints_v1: true
```

`ORION_FEATURE_FLAGS_FILE` selects another YAML file. A per-flag environment
variable overrides the file: `ORION_FEATURE_STRUCTURED_COMMAND_RESULT`,
`ORION_FEATURE_CANONICAL_FACTS`, `ORION_FEATURE_COMPOSITE_RULES`, and
`ORION_FEATURE_CLAIM_GUARD`. GA1 controls use
`ORION_GENERAL_AGENT_ROUTING_V1`, `ORION_EXTERNAL_VERIFICATION_V1`,
`ORION_WEB_SEARCH_V1`, and `ORION_SOURCE_CONSTRAINTS_V1`. Values must be one
of `true`/`false`, `1`/`0`, `yes`/`no`, or `on`/`off`; invalid/unknown file
keys fail validation.

Enable in this order after a QA gate: structured command provenance, canonical
Facts, composite rules, then claim grounding. Rollback reverses only the
affected layer and does not alter tool, evidence-package, or API response
schemas. The action-claim/read-only guard is not disabled by `claim_guard`.
These flags are temporary and must be removed after the migration exit
criteria in `docs/migrations/deterministic_reasoning_v1.md` are met.

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
