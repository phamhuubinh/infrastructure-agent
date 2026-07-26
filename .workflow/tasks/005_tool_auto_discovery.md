# Task 005: Tool Auto-Discovery / Simplified Registration

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 5 (Sprint 2, P1 - Refactor)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

Adding a new tool currently requires 4 steps across 3+ files:
1. Create `Tool` subclass with `_CAPABILITIES` dict.
2. Add to `_SUPPORTED_TOOL_TYPES` dict in `runtime_factory.py` (line 81-86).
3. Add construction block in `_register_single_tool()` (lines 170-195).
4. Register in `targets.json` / `tools.json`.

Steps 2-3 are the gap: the factory needs explicit knowledge of every tool type. Auto-discovery of `Tool` subclasses that declare `_CAPABILITIES` would reduce registration from 4 steps to 1 (create the file).

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/tool/registry.py` (NEW) | `ToolRegistry` with auto-discovery scanning `src/tool/` subdirectories | ~100 lines |
| 2 | `src/agent/runtime_factory.py` | Integrate auto-discovery alongside existing registration path | ~30 lines modified |
| 3 | `src/tool/` subdirectories | Ensure each tool module has `_CAPABILITIES` attribute | ~5 lines verify |

**Total estimated change:** ~135 lines

---

## 3. Detailed Instructions

### 3.1 `src/tool/registry.py` (NEW)

```python
from __future__ import annotations
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Type

from src.tool.tool import Tool

class ToolRegistry:
    """Auto-discovers Tool subclasses with _CAPABILITIES attribute.
    
    Scans src/tool/ subdirectories for modules with:
    - A Tool subclass
    - A _CAPABILITIES dict at module level
    
    Usage:
        registry = ToolRegistry()
        discovered = registry.discover()
        for tool_cls, caps in discovered:
            tool = tool_cls(url=..., token=...)
            target_registry.register_tool(name, tool)
    """
    
    def discover(self) -> list[tuple[Type[Tool], dict]]:
        """Scan tool/ subdirectories for Tool subclasses with _CAPABILITIES.
        
        Returns list of (ToolClass, capabilities_dict).
        """
        ...
    
    def discover_from_packages(self) -> list[tuple[Type[Tool], dict]]:
        """Future: discover tools from pip entry points."""
        ...
```

### 3.2 Integration in `runtime_factory.py`

Modify `_register_tools()` to also run auto-discovery:

```python
def _register_tools(registry, tools_config):
    # 1. Existing path: register from tools.json entries
    for entry_name, cfg in tools_config.items():
        _register_single_tool(registry, entry_name, cfg)
    
    # 2. NEW: auto-discover tool modules with _CAPABILITIES
    discovered = ToolRegistry().discover()
    for tool_cls, caps in discovered:
        # Tools discovered this way still need config from tools.json
        # for credentials (url, token). If no config entry, skip.
        if tool_cls.__name__.lower() not in tools_config:
            _warn(f"Discovered tool {tool_cls.__name__} has no config entry, skipping")
            continue
        ...
```

### 3.3 Backward compatibility

- Existing `_SUPPORTED_TOOL_TYPES` + `_register_single_tool()` preserved
- Auto-discovery is additive — discovers tools NOT in `_SUPPORTED_TOOL_TYPES`
- Old path takes precedence for already-registered tools

---

## 4. Dependencies

- **Task #004** (Security Pipeline) — auto-discovered tools must pass through inspector chain
- Blocks: None directly

---

## 5. Verification Criteria

- [ ] `python -c "from src.tool.registry import ToolRegistry; print(ToolRegistry().discover())"` lists all 4 tool types
- [ ] Tool registration time <20% increase (existing benchmark path)
- [ ] All existing tools discoverable via auto-discovery
- [ ] Existing `tools.json` registration still works
- [ ] New tool can be added in 1 step (create file with `_CAPABILITIES`)
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] One atomic commit: `feat: add tool auto-discovery via ToolRegistry`