# Legacy Runtime Retirement Checklist

## Prerequisites

- [ ] All tests pass (`python -m pytest tests/ -q`)
- [ ] Benchmark passes (`python -m benchmark --domain scenario_localhost`)
- [ ] Deterministic pipeline verified in production

## Step 1: Remove CLI `--legacy` flag

- [ ] Remove `--legacy` argument from `src/cli.py`
- [ ] Remove `if args.legacy:` branch (lines 145-172)
- [ ] Remove `from src.agent.agent import Agent` top-level import
- [ ] Remove `from src.tool.tool_registry import ToolRegistry` top-level import
- [ ] Remove `from src.tool.shell_tool import ShellTool` top-level import
- [ ] Verify: `grep -rn "ToolRegistry\|ShellTool\|Agent(" src/cli.py` → only `DeterministicAgent` remains
- [ ] Run tests: `python -m pytest tests/ -q`
- [ ] Verify help: `python -m src.cli --help | grep legacy` → no output

## Step 2: Remove benchmark `--legacy` flag

- [ ] Remove `--legacy` argument from `benchmark/__main__.py`
- [ ] Remove `_build_legacy_runtime()` function
- [ ] Verify: `python -m benchmark --help | grep legacy` → no output
- [ ] Run tests: `python -m pytest tests/ -q`

## Step 3: Remove `benchmark/runner.py`

- [ ] Delete `benchmark/runner.py`
- [ ] Verify: `python -m pytest tests/ -q`

## Step 4: Remove legacy Agent and reasoning

- [ ] Delete `src/agent/agent.py`
- [ ] Delete `src/shared/reasoning/action.py`
- [ ] Delete `src/shared/reasoning/final_response.py`
- [ ] Delete `src/shared/reasoning/reasoning_state.py`
- [ ] Verify: `grep -rn "from src.agent.agent\|from src.shared.reasoning" src/ benchmark/` → no output
- [ ] Run tests: `python -m pytest tests/ -q`

## Step 5: Remove legacy model components

- [ ] Delete `src/model/model_adapter.py`
- [ ] Delete `src/model/mock_model_adapter.py`
- [ ] Delete `src/model/ollama_model_adapter.py`
- [ ] Delete `src/model/protocol/action_parser.py`
- [ ] Delete `src/model/protocol/prompt_builder.py`
- [ ] Delete `src/shared/evidence_extractor.py`
- [ ] Delete `src/shared/discovery/observation.py`
- [ ] Delete `src/shared/discovery/__init__.py`
- [ ] Verify: `grep -rn "ModelAdapter\|MockModelAdapter\|OllamaModelAdapter\|action_parser\|prompt_builder\|extract_known_facts\|Observation(" src/ benchmark/` → no output
- [ ] Run tests: `python -m pytest tests/ -q`

## Step 6: Remove ToolRegistry

- [ ] Delete `src/tool/tool_registry.py`
- [ ] Verify: `grep -rn "ToolRegistry\|tool_registry" src/ benchmark/` → no output
- [ ] Run tests: `python -m pytest tests/ -q`

## Step 7: Remove legacy tests

- [ ] Delete `tests/agent/test_agent.py`
- [ ] Delete `tests/tool/test_tool_registry.py`
- [ ] Delete `tests/model/protocol/test_action_parser.py`
- [ ] Delete `tests/model/protocol/test_prompt_builder.py`
- [ ] Delete `tests/model/test_mock_model_adapter.py`
- [ ] Delete `tests/model/test_ollama_model_adapter.py`
- [ ] Delete `tests/shared/discovery/test_observation.py`
- [ ] Run tests: `python -m pytest tests/ -q`

## Step 8: Remove broken script

- [ ] Delete `scripts/prompt_benchmark.py`
- [ ] Verify: `ls scripts/` → empty (or removed)

## Step 9: Remove orphan test directories

- [ ] Delete `tests/runtime/`
- [ ] Delete `tests/schema/`
- [ ] Run tests: `python -m pytest tests/ -q`

## Step 10: Clean up __pycache__

- [ ] Run: `find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null`
- [ ] Run tests: `python -m pytest tests/ -q`

## Step 11: Update README

- [ ] Remove `--legacy` documentation
- [ ] Verify README describes only deterministic pipeline
- [ ] Update architecture diagram if stale

## Step 12: Final verification

- [ ] Full test suite: `python -m pytest tests/ -q`
- [ ] Benchmark: `python -m benchmark --domain scenario_localhost`
- [ ] Import scan: `grep -rn "from src.agent.agent\|ToolRegistry\|Action\|FinalResponse\|Observation(" src/ benchmark/` → no output
- [ ] CLI verification: `python -m src.cli --help`
- [ ] Runtime verification: `python -c "from src.agent.runtime_factory import create_deterministic_agent; a=create_deterministic_agent(False,False); print(a.run('test')[:50])"`
- [ ] Architecture verification: No legacy files remain in `src/`

## Files Expected to Be Removed (22 total)

```
src/agent/agent.py
src/model/model_adapter.py
src/model/mock_model_adapter.py
src/model/ollama_model_adapter.py
src/model/protocol/action_parser.py
src/model/protocol/prompt_builder.py
src/shared/evidence_extractor.py
src/shared/reasoning/action.py
src/shared/reasoning/final_response.py
src/shared/reasoning/reasoning_state.py
src/shared/discovery/observation.py
src/shared/discovery/__init__.py
src/tool/tool_registry.py
benchmark/runner.py
scripts/prompt_benchmark.py
tests/agent/test_agent.py
tests/tool/test_tool_registry.py
tests/model/protocol/test_action_parser.py
tests/model/protocol/test_prompt_builder.py
tests/model/test_mock_model_adapter.py
tests/model/test_ollama_model_adapter.py
tests/shared/discovery/test_observation.py
```

## Files Expected to Remain (shared infrastructure)

```
src/infrastructure/ollama/ollama_client.py
src/infrastructure/openai/openai_client.py
src/tool/knowledge_tool.py
src/tool/target_registry.py
src/tool/target_store.py
src/tool/execution_backend.py
src/tool/linux_tool.py
src/tool/zabbix_tool.py
src/tool/grafana_tool.py
src/tool/tool.py
src/tool/shell_tool.py
```

**Note:** `ollama_client.py` and `openai_client.py` become dead code after legacy removal. They are only used by `_build_client()` in the CLI's `--legacy` path. They should be kept in this sprint but flagged for removal in a future cleanup.

**Note:** `shell_tool.py` is only used by the legacy path (`ToolRegistry.register("shell", ShellTool())`). It should be kept but flagged for removal.
