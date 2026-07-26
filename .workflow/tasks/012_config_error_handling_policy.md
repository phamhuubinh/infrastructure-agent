# Task 012: Configuration Error Handling Policy

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 12 (Sprint 1, P3 - Foundation)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

Orion's configuration error handling is inconsistent across sources (verified by AC):
1. `_load_server_config()` raises `RuntimeError` if `servers.json` is missing.
2. `_load_tools_config()` silently returns `{}` if `tools.json` is missing.
3. `_build_assessment_adapter()` casts config values with `int()` and `float()` — non-numeric values crash.
4. Some env vars have defaults, others don't — no documented policy.

The same class of error (missing/invalid config) produces three different behaviors: crash, silent default, or wrong behavior. Task #002 (Pydantic validation) catches schema errors, but a consistent policy is needed for what happens when validation fails and how errors are reported.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/shared/config_errors.py` (NEW) | `ConfigurationError` exception hierarchy + error formatter | ~40 lines |
| 2 | `src/shared/config.py` | Apply consistent error handling through the unified accessor (Task #003) | ~20 lines modified |
| 3 | `src/agent/runtime_factory.py` | Replace ad-hoc error handling (RuntimeError, silent returns) | ~15 lines modified |
| 4 | `docs/devops/configuration.md` (NEW) | Document configuration error handling policy | ~30 lines |

**Total estimated change:** ~105 lines

---

## 3. Detailed Instructions

### 3.1 `src/shared/config_errors.py` (NEW)

```python
from __future__ import annotations

class ConfigurationError(Exception):
    """Base class for all configuration errors."""
    
    def __init__(self, file: str, key: str, expected: str, received: str):
        self.file = file
        self.key = key
        self.expected = expected
        self.received = received
        super().__init__(self.format())
    
    def format(self) -> str:
        return (
            f"Configuration error in {self.file}:\n"
            f"  Key: {self.key}\n"
            f"  Expected: {self.expected}\n"
            f"  Received: {self.received}"
        )

class MissingConfigFileError(ConfigurationError):
    """Config file does not exist."""

class InvalidConfigValueError(ConfigurationError):
    """Config value has wrong type or invalid value."""

class MissingRequiredKeyError(ConfigurationError):
    """Required key is missing from config."""
```

### 3.2 Consistent error behavior policy

**Policy (documented in `docs/devops/configuration.md`):**

1. **Missing required config** → `MissingConfigFileError` at startup. Fail fast, fail loud, fail with context.
2. **Missing optional config** → Warn via `_warn()`, continue with safe defaults.
3. **Invalid config value** → `InvalidConfigValueError` at startup. Report file, key, expected type, received value.
4. **All errors collected before exit** → Don't fail on first error. Validate all configs, report all errors together, then exit.

### 3.3 Integration with Task #002 and Task #003

```python
# In OrionConfig.load():
errors = []
try:
    servers = ServersConfig.model_validate_json(servers_path.read_text())
except ValidationError as e:
    for err in e.errors():
        errors.append(InvalidConfigValueError(
            file="servers.json",
            key=".".join(str(loc) for loc in err["loc"]),
            expected=err["type"],
            received=str(err.get("input", "N/A")),
        ))
# ... repeat for tools, targets

if errors:
    for err in errors:
        _warn(err.format())
    raise SystemExit(1)
```

---

## 4. Dependencies

- **Task #002** (Pydantic validation) — error policy is applied through validated models
- **Task #003** (Unified Config Accessor) — policy is applied in the unified accessor

---

## 5. Verification Criteria

- [ ] All 4 error behaviors unified (missing required → error, missing optional → warn + default, invalid → error)
- [ ] Error messages include file, key, expected type, received value (within 3 lines)
- [ ] All config errors collected before exit (not fail-on-first)
- [ ] Existing `servers.json` handling unchanged for valid config
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] New tests: `tests/shared/test_config_errors.py`
- [ ] One atomic commit: `feat: add consistent configuration error handling policy`