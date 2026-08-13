# Configuration Behavior

Orion validates present JSON/YAML configuration at startup and reports all
schema errors together through `ConfigValidationError`. Optional absent files
use their code-defined defaults.

## Sources

| Source | Current behavior |
|---|---|
| `servers.json` / `ORION_SERVERS_FILE` | Optional model registry; an empty registry starts setup mode |
| `tools.json` | Tracked non-secret Child Tool registry |
| `targets.json` | Optional JSON target registry |
| `/etc/orion/tool-credentials.json` / `ORION_SECRETS_PATH` | External tool endpoints and credentials; empty mapping disables those configured integrations |
| `config/concepts.yaml` | Semantic concepts |
| `config/capability_plans.yaml` | Concept/action capability mappings |
| `config/conversational_patterns.yaml` | General-conversation patterns |
| `config/target_aliases.yaml` | Target aliases |
| `config/health_patterns.yaml` | Health-request patterns |
| `config/rules/*.yaml` | Reviewed atomic/composite rule schemas |
| `config/feature_flags.yaml` / `ORION_FEATURE_FLAGS_FILE` | Optional strict feature-switch object |
| `ORION_*` variables | Runtime overrides read by the relevant configuration component |

The production `ExecutionEngine` requires at least one reviewed atomic rule
from `config/rules/`; it fails startup instead of silently loading unreviewed
hardcoded thresholds.

## Feature switches

The repository does not contain `config/feature_flags.yaml`, so
`FeatureFlagsConfig` defaults apply unless an override file or environment
value is provided:

```yaml
schema_version: rollout.v1
structured_command_result: false
canonical_facts: false
composite_rules: false
claim_guard: false
general_agent_routing_v1: true
external_verification_v1: true
web_search_v1: true
source_constraints_v1: true
```

Environment overrides:

| Field | Variable |
|---|---|
| `structured_command_result` | `ORION_FEATURE_STRUCTURED_COMMAND_RESULT` |
| `canonical_facts` | `ORION_FEATURE_CANONICAL_FACTS` |
| `composite_rules` | `ORION_FEATURE_COMPOSITE_RULES` |
| `claim_guard` | `ORION_FEATURE_CLAIM_GUARD` |
| `general_agent_routing_v1` | `ORION_GENERAL_AGENT_ROUTING_V1` |
| `external_verification_v1` | `ORION_EXTERNAL_VERIFICATION_V1` |
| `web_search_v1` | `ORION_WEB_SEARCH_V1` |
| `source_constraints_v1` | `ORION_SOURCE_CONSTRAINTS_V1` |

Boolean values accept `true/false`, `1/0`, `yes/no`, or `on/off`. Unknown file
keys and invalid values fail validation. Disabling external verification or
web search returns current-information requests as unverified; it does not
enable a model-memory fallback. The read-only action boundary is independent
of `claim_guard`.

## Error shape

`src/shared/config_errors.py` provides contextual file/key/expected/received
errors. `src/shared/config_schema.py` provides Pydantic schemas for server,
tool, target, rule, and feature-switch data. `src/backend/app.py` validates all
present schemas before constructing application state.
