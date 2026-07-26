# Task 003: Unified Configuration Accessor (`OrionConfig`)

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 3 (Sprint 1, P0 - Foundation)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

Configuration is spread across **11 sources** (verified by AC against `runtime_factory.py` and `deterministic_agent.py`):
1. `servers.json`
2. `tools.json`
3. `targets.json`
4. `config/secrets.local.json`
5. `config/conversational_patterns.yaml`
6. `config/capability_plans.yaml`
7. `config/concepts.yaml`
8. `config/target_aliases.yaml`
9. Environment variables (`ORION_*`)
10. `_VAGUE_HEALTH_PATTERNS` hardcoded class attribute in `deterministic_agent.py`
11. `_conv_vi_patterns` / `_conv_en_patterns` loaded from YAML with fallback defaults

There is no unified accessor. Each module reads its own config sources via scattered `os.environ.get()` calls and JSON file reads. This makes it impossible to validate complete configuration at startup and hard for developers to discover where a setting is configured.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/shared/config.py` (NEW) | `OrionConfig` dataclass aggregating all 11 sources | ~150 lines |
| 2 | `src/agent/runtime_factory.py` | Migrate all config reads to `OrionConfig` accessor | ~30 lines modified |
| 3 | `src/agent/deterministic_agent.py` | Migrate env var reads + hardcoded patterns | ~40 lines modified |
| 4 | `src/backend/app.py` | Migrate config reads | ~10 lines modified |
| 5 | `src/cli/main.py` | Migrate config reads | ~10 lines modified |
| 6 | `src/pipeline/intent_resolver.py` | Migrate `_VAGUE_HEALTH_PATTERNS` | ~15 lines modified |

**Total estimated change:** ~255 lines

---

## 3. Detailed Instructions

### 3.1 `src/shared/config.py` (NEW)

Create `OrionConfig` as a Pydantic model:

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

@dataclass
class OrionConfig:
    """Single accessor for all Orion configuration sources (11 total).
    
    Usage:
        config = OrionConfig.load()
        model_name = config.active_server.model
    """
    
    # servers.json
    servers: dict[str, Any] = field(default_factory=dict)
    active_server_name: str = ""
    
    # tools.json
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # targets.json
    targets: dict[str, Any] = field(default_factory=dict)
    
    # config/secrets.local.json
    secrets: dict[str, Any] = field(default_factory=dict)
    
    # config/conversational_patterns.yaml
    vi_patterns: list[str] = field(default_factory=list)
    en_patterns: list[str] = field(default_factory=list)
    
    # config/capability_plans.yaml
    capability_plans: dict[str, Any] = field(default_factory=dict)
    
    # config/concepts.yaml
    concepts: dict[str, Any] = field(default_factory=dict)
    
    # config/target_aliases.yaml
    target_aliases: dict[str, str] = field(default_factory=dict)
    
    # Environment variables
    orion_env: dict[str, str] = field(default_factory=dict)  # ORION_* vars
    
    # Hardcoded health patterns (migrated from deterministic_agent.py)
    vague_health_patterns: list[str] = field(default_factory=list)
    
    @classmethod
    def load(cls, project_root: Path | None = None) -> OrionConfig:
        """Load and validate all 11 configuration sources."""
        ...
    
    @property
    def active_server(self) -> dict[str, Any]:
        return self.servers.get(self.active_server_name, {})
```

Key design decisions:
- Lazy-load YAML files (per `07_DEVELOPMENT_RULES.md` rule 12 — no over-engineering)
- Pydantic validation for critical sources (servers, tools, targets) per Task #002
- Environment variables prefixed `ORION_` only
- Single `load()` method reads all sources with consistent error reporting

### 3.2 Migration approach

Replace existing ad-hoc reads:
```python
# OLD in deterministic_agent.py:
config_path = os.environ.get("ORION_CONVERSATIONAL_CONFIG", str(Path(...)))
with open(config_path) as fh:
    data = yaml.safe_load(fh)

# NEW:
config = get_config()  # singleton or passed via constructor
vi_patterns = config.vi_patterns
```

### 3.3 `VAGUE_HEALTH_PATTERNS` migration

Move the 18 hardcoded patterns from `deterministic_agent.py` (lines 434-453) to a YAML config file loaded through `OrionConfig`:
```yaml
# config/health_patterns.yaml (NEW)
vague_health_patterns:
  - "có vấn đề gì không"
  - "có lỗi gì không"
  - ...
```

---

## 4. Dependencies

- **Task #002** (Pydantic config schema) — the accessor uses Pydantic models for validation
- Blocks: Tasks #004, #008, #011 (all need unified config)

---

## 5. Verification Criteria

- [ ] All 11 config sources accessible through single `OrionConfig` object
- [ ] `git grep os.environ.get` returns zero results in `src/agent/`, `src/pipeline/`
- [ ] Existing behavior preserved (all config defaults maintained)
- [ ] Config load time <10ms (measured via `time.perf_counter()`)
- [ ] Old config access paths emit deprecation warnings during transition
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] One atomic commit: `refactor: add unified OrionConfig accessor replacing 11 scattered config sources`