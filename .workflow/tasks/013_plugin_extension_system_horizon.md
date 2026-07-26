# Task 013: Plugin/Extension System [HORIZON]

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 13 (Horizon - Future)
> **Created:** 2026-07-26
> **Status:** horizon (not for immediate implementation)

---

## 1. Problem Summary

Orion has no plugin system for community-contributed monitoring platform integrations (Datadog, Prometheus, AWS CloudWatch, New Relic). Adding a new monitoring platform requires code changes in `runtime_factory.py`.

**Why this is HORIZON, not backlog:**
- FAR correctly classified this as ROADMAP — Orion is a vertical tool with a bounded domain
- High implementation cost (800-1200 LOC) with uncertain ecosystem return
- Must enforce `Capability` metadata contract on plugins — non-trivial constraint for plugin authors
- Security implications: plugins introduce untrusted code, requiring Task #004 (Security Pipeline) as prerequisite
- Task #005 (Tool Auto-Discovery) achieves 80% of the plugin value at 20% of the cost

---

## 2. Gates for Promotion to Backlog

Before this item can be moved to active backlog, ALL 5 gates must be met:

1. **Community demand** — ≥3 specific monitoring platform integrations requested
2. **Security Pipeline** (Task #004) — complete and proven in production
3. **Tool Auto-Discovery** (Task #005) — complete and proven in production
4. **Plugin API design** — a design that enforces the `Capability` metadata contract exists and is reviewed
5. **API stability commitment** — a commitment to backward compatibility for the plugin API is made

---

## 3. Implementation Outline (if promoted)

### 3.1 Architecture

```
ToolProvider (ABC)
├── defines plugin contract: capabilities(), execute(), health_check()
│
PluginManager
├── discovery: scan configured paths for ToolProvider implementations
├── lifecycle: load → validate → register → unload
├── isolation: sandbox capability (read-only enforcement)
│
Plugin Registry
├── stores: (provider_name, ToolProvider, metadata, signature)
└── validates: capability uniqueness, version compatibility
```

### 3.2 Files (estimated)

| # | File | LOC |
|---|------|-----|
| 1 | `src/tool/plugin/tool_provider.py` — ABC | ~40 lines |
| 2 | `src/tool/plugin/plugin_manager.py` — discovery + lifecycle | ~150 lines |
| 3 | `src/tool/plugin/plugin_registry.py` — registration + validation | ~80 lines |
| 4 | `src/tool/plugin/plugin_loader.py` — import hooks + isolation | ~100 lines |
| 5 | `src/tool/plugin/plugin_config.py` — plugin configuration schema | ~50 lines |
| 6 | `docs/tools/plugin-development.md` — plugin author guide | ~200 lines |
| 7 | Tests: `tests/tool/plugin/` | ~200 lines |

**Total estimated:** ~820 lines

### 3.3 Plugin contract

```python
class ToolProvider(ABC):
    """Contract for plugin-provided monitoring platform integrations."""
    
    @property
    @abstractmethod
    def provider_name(self) -> str: ...
    
    @property
    @abstractmethod
    def version(self) -> str: ...
    
    @abstractmethod
    def capabilities(self) -> dict[str, Capability]:
        """Return capabilities this provider supports. Must include:
        - name, evidence_name, covers, category, intents, mutation_risk
        """
        ...
    
    @abstractmethod
    def execute(self, capability_name: str, params: dict) -> ToolResult:
        """Execute a capability. Must be read-only (mutation_risk=0)."""
        ...
    
    @abstractmethod
    def health_check(self) -> bool: ...
```

---

## 4. Current Status

- **Status:** HORIZON — not in active backlog
- **Estimated effort:** 800-1200 LOC
- **Prerequisites:** Tasks #004, #005 complete
- **Gate status:** 0/5 gates met
- **No action required** at this time

---

## 5. Relationship to Tool Auto-Discovery (Task #005)

Task #005 reduces internal tool registration from 4 steps to 1. This achieves 80% of the plugin system's value proposition (easier tool registration) at 20% of the cost. The plugin system adds the remaining 20% (external distribution, pip-installable tools, community contribution) — but this value only materializes when there is an external community.

If Task #005 is implemented, re-evaluate whether the horizon item is still needed against the 5 gates. It may be that auto-discovery alone satisfies the tool extension needs indefinitely.