# Legacy Runtime Removal Plan

## Execution Order

Each step is independently verifiable. Steps must execute in order.

---

### Step 1: Remove `--legacy` flag from CLI

**Files:**
- `src/cli.py` — remove `--legacy` argument, remove `if args.legacy:` branch
- `README.md` — remove `--legacy` documentation

**Dependencies:** None (standalone change)

**Verification:** `python -m src.cli --help` shows no `--legacy`

**Rollback:** Revert the two lines in `cli.py`

---

### Step 2: Remove `--legacy` from benchmark

**Files:**
- `benchmark/__main__.py` — remove `--legacy` argument, remove `_build_legacy_runtime()`

**Dependencies:** Step 1 (benchmark `--legacy` parallels CLI `--legacy`)

**Verification:** `python -m benchmark --help` shows no `--legacy`

---

### Step 3: Remove legacy Agent

**Files:**
- `src/agent/agent.py`
- `src/shared/reasoning/action.py`
- `src/shared/reasoning/final_response.py`
- `src/shared/reasoning/reasoning_state.py`

**Dependencies:** Steps 1-2 (no remaining production code imports these)

**Verification:** `grep -rn "from src.agent.agent\|from src.shared.reasoning" src/ benchmark/` returns nothing

**CAUTION:** Removing `src/agent/agent.py` breaks `src/model/ollama_model_adapter.py` which imports `_VERBOSE` from it.

---

### Step 4: Remove legacy model components

**Files:**
- `src/model/model_adapter.py`
- `src/model/mock_model_adapter.py`
- `src/model/ollama_model_adapter.py`
- `src/model/protocol/action_parser.py`
- `src/model/protocol/prompt_builder.py`
- `src/shared/evidence_extractor.py`
- `src/shared/discovery/observation.py`
- `src/shared/discovery/__init__.py`

**Dependencies:** Step 3 (model components exist only to support legacy Agent)

**Verification:** `grep -rn "ModelAdapter\|MockModelAdapter\|OllamaModelAdapter\|parse_response\|extract_known_facts\|Observation(" src/ benchmark/` returns nothing from non-test files

**CAUTION:** Need to verify `src/agent/agent.py` references in `src/model/ollama_model_adapter.py` (imports `_VERBOSE`). Since both are being removed, order matters — remove agent.py AND ollama_model_adapter.py simultaneously.

---

### Step 5: Remove ToolRegistry

**Files:**
- `src/tool/tool_registry.py`

**Dependencies:** Steps 1-4 (no remaining production code imports ToolRegistry)

**Verification:** `grep -rn "ToolRegistry\|tool_registry" src/ benchmark/` returns nothing

---

### Step 6: Remove legacy tests

**Files:**
- `tests/agent/test_agent.py`
- `tests/tool/test_tool_registry.py`
- `tests/model/protocol/test_action_parser.py`
- `tests/model/protocol/test_prompt_builder.py`
- `tests/model/test_mock_model_adapter.py`
- `tests/model/test_ollama_model_adapter.py`
- `tests/shared/discovery/test_observation.py`

**Dependencies:** Steps 3-5 (tests validate deleted code)

**Verification:** `python -m pytest tests/ -q` — all remaining tests pass

---

### Step 7: Remove legacy benchmark runner

**Files:**
- `benchmark/runner.py`

**Dependencies:** Step 2 (runner is only used by legacy benchmark path)

**Verification:** `python -m pytest tests/ -q` passes

---

### Step 8: Remove legacy script

**Files:**
- `scripts/prompt_benchmark.py`

**Dependencies:** None (script is already broken — imports missing `prompt_loader`)

**Verification:** File no longer exists

---

### Step 9: Remove stale infrastructure

**Files:**
- `src/shared/__init__.py` (empty — but keeps parent package for remaining `capability.py`)
- Actually keep: `src/shared/capability.py` is still used by tools
- Keep: `src/shared/execution/tool_result.py` is still used by pipeline evidence_merge

**Note:** `src/shared/` has two remaining files after cleanup:
- `src/shared/capability.py` — still used by `LinuxTool._CAPABILITIES`
- `src/shared/execution/tool_result.py` — still used by `EvidenceMerge`

These must remain.

---

### Step 10: Final verification

```
python -m pytest tests/ -q               # all tests pass
python -m benchmark --domain scenario_localhost  # benchmark works
python -m src.cli --help                  # no --legacy flag
python -m src.cli <<< "check health"      # deterministic pipeline works
grep -rn "from src.agent.agent\|ToolRegistry\|Action\|FinalResponse\|Observation" src/ benchmark/  # no legacy imports
```
