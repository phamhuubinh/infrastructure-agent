# Task 008: Multi-Provider LLM Support with Failover

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 8 (Sprint 3, P2 - Foundation)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

`LLMClient` supports only OpenAI-compatible endpoints with a single server configuration. No failover, no multi-provider abstraction, no credential pool. ADR-0001 states the architecture should be "model-agnostic" — the `AssessmentModelAdapter` ABC exists (with `LLMAssessmentAdapter` and `MockAssessmentAdapter`), proving the abstraction works. But only one production implementation exists.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/model/providers/registry.py` (NEW) | `ProviderRegistry` mapping names to adapters | ~60 lines |
| 2 | `src/model/providers/credential_pool.py` (NEW) | `CredentialPool` for multi-key provider support | ~40 lines |
| 3 | `src/model/providers/fallback_chain.py` (NEW) | `FallbackChain` with configurable fallback order | ~50 lines |
| 4 | `src/model/providers/anthropic_adapter.py` (NEW) | Second `AssessmentModelAdapter` implementation (Anthropic) | ~80 lines |
| 5 | `src/model/llm_client.py` | Refactor to support multiple providers | ~30 lines modified |
| 6 | `src/agent/runtime_factory.py` | Integrate provider registry + fallback chain | ~25 lines modified |
| 7 | `config/servers.json` | Extend schema for multiple providers | ~10 lines |

**Total estimated change:** ~295 lines

---

## 3. Detailed Instructions

### 3.1 `ProviderRegistry`

```python
@dataclass
class ProviderRegistry:
    providers: dict[str, AssessmentModelAdapter] = field(default_factory=dict)
    fallback_chain: list[str] = field(default_factory=list)
    
    def get_adapter(self, name: str | None = None) -> AssessmentModelAdapter:
        if name and name in self.providers:
            return self.providers[name]
        # Fallback: try each provider in order
        for provider_name in self.fallback_chain:
            adapter = self.providers.get(provider_name)
            if adapter and adapter.health_check(timeout=2.0):
                return adapter
        raise RuntimeError("No available LLM provider")
```

### 3.2 `FallbackChain`

```python
class FallbackChain:
    def execute_with_fallback(self, fn: Callable) -> Any:
        for provider in self.chain:
            try:
                return fn(provider)
            except (ConnectionError, TimeoutError):
                continue
        raise RuntimeError("All providers exhausted")
```

### 3.3 `AnthropicAdapter`

```python
class AnthropicAssessmentAdapter(AssessmentModelAdapter):
    """Anthropic Claude adapter — second production implementation proving ABC works."""
    
    def __init__(self, api_key: str, model: str = "claude-3-haiku"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
    
    def assess(self, request: AssessmentRequest) -> AssessmentResult:
        prompt = build_assessment_prompt(request)  # reuse existing prompt builder
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return AssessmentResult(
            assessment=response.content[0].text,
            token_usage=TokenUsage(...)
        )
    
    def assess_raw(self, prompt: str) -> str: ...
    def health_check(self, timeout: float = 5.0) -> bool: ...
```

### 3.4 Config schema extension

```json
// servers.json (extended)
{
  "active_server": "sv1",
  "servers": {
    "sv1": {
      "provider": "openai",
      "base_url": "http://localhost:8000",
      "model": "gpt-4",
      "api_key": "..."
    },
    "sv2": {
      "provider": "anthropic",
      "model": "claude-3-haiku",
      "api_key": "..."
    }
  },
  "fallback_chain": ["sv1", "sv2"],
  "credential_pool": {
    "openai": ["key1", "key2"],
    "anthropic": ["key1"]
  }
}
```

---

## 4. Dependencies

- **Task #002** (Config Schema) — provider config must be validated
- **Task #007** (Prompt Templates) — strongly recommended; templates easier to tune per provider

---

## 5. Verification Criteria

- [ ] Anthropic adapter passes same assessment quality benchmark (≥90% of baseline)
- [ ] Provider failover works (kill sv1 → sv2 picks up)
- [ ] New provider ≥90% assessment quality vs. baseline
- [ ] Provider failover latency <timeout (2s health check)
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] One atomic commit: `feat: add multi-provider LLM support with Anthropic adapter + failover chain`