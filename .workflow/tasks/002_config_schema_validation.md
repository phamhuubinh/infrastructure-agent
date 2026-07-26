# Task 002: Configuration Schema Validation (Pydantic Models)

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 2 (Sprint 1, P0 - Quick Win)
> **Created:** 2026-07-26
> **Status:** completed

---

## 1. Problem Summary

Orion loads configuration from multiple JSON/YAML files without schema validation. Invalid configurations (wrong types, missing required fields, invalid enum values) surface as runtime errors deep in the pipeline.

**Verified issues from source code:**
1. `_build_assessment_adapter()` (`runtime_factory.py` lines 237-243) casts config values with `int()` and `float()` — a non-numeric config value causes a runtime crash.
2. `runtime_factory.py` line 309 accesses `len(tools_config.get("tools", []))` but `tools_config` is built from a flat dict of tool entries — the `"tools"` key doesn't exist, so `len()` always returns 0.
3. `_load_server_config()` raises `RuntimeError` if `servers.json` is missing but `_load_tools_config()` silently returns `{}` if `tools.json` is missing.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/shared/config_schema.py` (NEW) | Pydantic models for all config files | ~80 lines |
| 2 | `src/backend/app.py` | Validate config at FastAPI startup | ~10 lines added |
| 3 | `src/cli/main.py` | Validate config at CLI entry | ~10 lines added |
| 4 | `src/agent/runtime_factory.py` | Replace ad-hoc type casting with validated model access | ~20 lines modified |

**Total estimated change:** ~120 lines

---

## 3. Detailed Instructions

### 3.1 `src/shared/config_schema.py` (NEW)

Create Pydantic v2 models:

```python
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Optional

class ServerConfig(BaseModel):
    base_url: str
    api_key: Optional[str] = None
    model: str = "gpt-4"
    timeout: int = Field(default=60, ge=1, le=300)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)

class ServersConfig(BaseModel):
    active_server: str
    servers: dict[str, ServerConfig]

    @field_validator("active_server")
    @classmethod
    def active_must_exist(cls, v: str, info) -> str:
        servers = info.data.get("servers", {})
        if v not in servers:
            raise ValueError(f"active_server '{v}' not in servers dict")
        return v

class ToolEntry(BaseModel):
    tool: str
    url: Optional[str] = None
    token: Optional[str] = None
    target: Optional[str] = None
    timeout: Optional[int] = None

class ToolsConfig(BaseModel):
    # Top-level keys are tool entry names; values are ToolEntry
    pass  # validated as dict[str, ToolEntry]

class TargetEntry(BaseModel):
    hostname: str
    port: int = Field(default=22, ge=1, le=65535)
    username: str = "root"
    # ... other fields per targets.json schema

class TargetsConfig(BaseModel):
    targets: dict[str, TargetEntry]
```

### 3.2 `src/backend/app.py`

Add at startup (in `create_app()` or lifespan):

```python
from src.shared.config_schema import ServersConfig, ToolsConfig, TargetsConfig
# ... validate all three configs, log any errors, fail fast
```

### 3.3 `src/cli/main.py`

Add at CLI entry before agent construction:

```python
from src.shared.config_schema import validate_all_configs
# ... call validate_all_configs(); exit(1) on failure
```

### 3.4 `src/agent/runtime_factory.py`

Replace ad-hoc type casting in `_build_assessment_adapter()`:

```python
# OLD (line 241):
timeout=int(config.get("timeout", 60)),
# NEW:
cfg = ServerConfig.model_validate(config)
timeout=cfg.timeout,
```

---

## 4. Verification Criteria

- [x] All three config files validated at startup
- [x] Invalid config fails with clear Pydantic error message (field, file, expected type)
- [x] `_build_assessment_adapter()` uses validated model instead of `int()`/`float()` casts
- [ ] JSON Schema exported for IDE autocompletion (deferred — not blocking)
- [x] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [x] New tests: valid + invalid config variants for each file
- [ ] One atomic commit: `feat: add Pydantic config schema validation at startup`
