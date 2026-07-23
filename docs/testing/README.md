# Testing Guide

> Testing conventions, fixtures, and best practices for Orion.

---

## Quick Start

```bash
# Run all tests (excluding slow/integration tests)
python3 -m pytest tests/ -q -x -k "not slow"

# Run with coverage
python3 -m pytest tests/ -q --cov=src --cov-report=term

# Run a specific module
python3 -m pytest tests/pipeline/ -q

# Run benchmark suite
python3 -m benchmark --domain all --json
```

---

## Test Structure

```
tests/
├── agent/                    # Agent-level tests
│   ├── test_conversation_store.py
│   ├── test_conversation_store_thread_safety.py
│   ├── test_deterministic_agent.py
│   └── test_runtime_factory.py
├── backend/                  # API & backend tests
│   ├── test_app.py
│   ├── test_auth.py
│   └── test_routers.py
├── benchmark/               # Benchmark runner tests
│   ├── test_assessment_evaluator.py
│   ├── test_get_prompt.py
│   ├── test_main_integration.py
│   ├── test_metadata.py
│   ├── test_registry.py
│   └── test_report_wiring.py
├── data/                     # Test data fixtures
│   ├── grafana_responses.json
│   ├── linux_command_outputs.json
│   └── zabbix_responses.json
├── model/                    # Assessment model tests
│   ├── test_llm_assessment_adapter.py
│   ├── test_llm_client.py
│   ├── test_mock_assessment_adapter.py
│   └── protocol/
├── pipeline/                 # Pipeline component tests
│   ├── test_assessment_adapter.py
│   ├── test_assessment_request.py
│   ├── test_capability_resolver.py
│   ├── test_capability_router.py
│   ├── test_deterministic_responder.py
│   ├── test_evidence_completeness.py
│   ├── test_evidence_merge.py
│   ├── test_evidence_package.py
│   ├── test_evidence_planner.py
│   ├── test_execution_engine.py
│   ├── test_execution_graph.py
│   └── test_execution_planner.py
├── shared/                   # Shared utility tests
└── tool/                     # Tool integration tests
```

---

## Writing Tests

### Naming Convention

- Test files: `test_<module>.py`
- Test classes: `Test<Component>`
- Test methods: `test_<scenario>_<expected_behavior>`

### Example

```python
import pytest
from src.pipeline.intent_resolver import IntentResolver, Intent

class TestIntentResolver:
    def test_resolve_disk_query_returns_disk_intent(self):
        resolver = IntentResolver()
        request = resolver.resolve("Check disk usage on webserver01")
        assert request.intent == Intent.DISK_USAGE
        assert request.confidence > 0.8

    def test_resolve_unknown_query_returns_general(self):
        resolver = IntentResolver()
        request = resolver.resolve("hello world")
        assert request.confidence < 0.5
```

### Mocking External Dependencies

```python
from unittest.mock import MagicMock, patch

@patch("src.tool.internet_tool._fetch_url")
def test_fetch_timeout_handling(self, mock_fetch):
    mock_fetch.side_effect = TimeoutError("Connection timed out")
    tool = InternetTool()
    result = tool.execute({"capability": "web_fetch", "url": "https://slow.example.com"})
    assert result.success is False
    assert "timeout" in result.error.lower()
```

### Thread Safety Tests

Thread safety tests use `threading.Thread` with `threading.Barrier` for synchronization:

```python
import threading

def test_concurrent_writes(self):
    store = ConversationStore(session_id="test")
    barrier = threading.Barrier(4)
    errors = []

    def writer():
        try:
            barrier.wait()
            for _ in range(10):
                store.add_turn("user", "assistant")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
```

---

## Test Categories

| Marker | Description | Command |
|--------|-------------|---------|
| (none) | Standard unit tests | `pytest tests/` |
| `slow` | Integration/container tests | `pytest tests/ -m slow` |
| `benchmark` | Performance benchmarks | `python -m benchmark` |

---

## Coverage Targets

| Module | Target | Current |
|--------|--------|---------|
| `src/pipeline/` | 90% | ✓ |
| `src/agent/` | 85% | ✓ |
| `src/backend/` | 85% | ✓ |
| `src/model/` | 85% | ✓ |
| `src/tool/` | 80% | ✓ |
| `src/shared/` | 90% | ✓ |

---

## CI Integration

Tests run automatically in CI on every push. Failures block merging. See `docs/devops/ci.md` for the full CI pipeline.

---

> **Last updated:** 2026-07-23