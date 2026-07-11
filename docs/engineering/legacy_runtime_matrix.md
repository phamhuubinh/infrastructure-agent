# Legacy Runtime Matrix

| Legacy Component | Responsibility | Production Used | Benchmark Used | Test Used | CLI Used | Deterministic Replacement | Status |
|---|---|---|---|---|---|---|---|
| `agent.py` (Agent) | ReAct orchestration loop | NO | _legacy only | YES | _legacy only | `DeterministicAgent` | **REMOVE** |
| `tool_registry.py` (ToolRegistry) | Tool lookup for ReAct | NO | _legacy only | YES | _legacy only | `TargetRegistry` + `CapabilityRouter` | **REMOVE** |
| `action.py` (Action) | Model decision dataclass | NO | _legacy only | YES | NO | `AssessmentRequest` | **REMOVE** |
| `final_response.py` (FinalResponse) | Model output dataclass | NO | _legacy only | YES | NO | `AssessmentModelAdapter.assess()` → str | **REMOVE** |
| `reasoning_state.py` (ReasoningState) | Execution state for ReAct | NO | NO | NO | NO | `InvestigationRequest` (pipeline state) | **REMOVE** |
| `action_parser.py` (parse_response) | LLM JSON → Action/FinalResponse | NO | NO | YES | NO | `AssessmentModelAdapter.assess()` → str | **REMOVE** |
| `prompt_builder.py` (build_prompt) | ReAct prompt assembly (22KB) | NO | NO | YES | NO | `prompt_builder_v2.build_assessment_prompt()` (2.7KB) | **REMOVE** |
| `evidence_extractor.py` (extract_known_facts) | Known facts for prompt context | NO | NO | NO | NO | `EvidencePackage` + `AssessmentRequest` | **REMOVE** |
| `model_adapter.py` (ModelAdapter) | Abstract model interface | NO | _legacy only | YES | NO | `AssessmentModelAdapter` | **REMOVE** |
| `mock_model_adapter.py` | Mock for legacy testing | NO | _legacy only | YES | NO | `MockAssessmentAdapter` | **REMOVE** |
| `ollama_model_adapter.py` | Ollama LLM wrapper | NO | NO | YES | _legacy only | `AssessmentModelAdapter` (future impl) | **REMOVE** |
| `observation.py` (Observation) | Tool result wrapper | NO | _legacy only | YES | NO | `EvidencePackage` | **REMOVE** |
| `benchmark/runner.py` | Benchmark runner wrapper | NO | NO (default uses __main__.py directly) | NO | NO | `benchmark/__main__.py` (deterministic) | **REMOVE** |
| `scripts/prompt_benchmark.py` | Prompt benchmarking script | NO | NO | NO | NO | None needed (prompt size 2.7KB vs 22KB) | **REMOVE** |
| `tests/agent/test_agent.py` | Legacy Agent tests | N/A | N/A | YES | N/A | `test_deterministic_agent.py` | **REMOVE** |
| `tests/tool/test_tool_registry.py` | ToolRegistry tests | N/A | N/A | YES | N/A | `test_capability_router.py` covers routing | **REMOVE** |
| `tests/model/protocol/test_action_parser.py` | Action parser tests | N/A | N/A | YES | N/A | No replacement needed (format changed) | **REMOVE** |
| `tests/model/protocol/test_prompt_builder.py` | ReAct prompt tests | N/A | N/A | YES | N/A | `test_prompt_builder_v2.py` | **REMOVE** |
| `tests/model/test_mock_model_adapter.py` | Mock adapter tests | N/A | N/A | YES | N/A | `test_assessment_request.py` (tests mock assessment) | **REMOVE** |
| `tests/model/test_ollama_model_adapter.py` | Ollama adapter tests | N/A | N/A | YES | N/A | `prompt_builder_v2 tests` + future assessment adapter | **REMOVE** |
| `tests/shared/discovery/test_observation.py` | Observation tests | N/A | N/A | YES | N/A | No replacement needed (data class) | **REMOVE** |

**Total files to remove: 22** (12 source, 7 test, 1 benchmark, 1 script, 1 empty package remnants)

**Shared infrastructure files that must REMAIN:**

| File | Reason |
|---|---|
| `src/infrastructure/ollama/ollama_client.py` | Still used by `_build_client()` in CLI legacy path |
| `src/infrastructure/openai/openai_client.py` | Same — used by CLI legacy path |
| `src/tool/knowledge_tool.py` | Used by BOTH deterministic and legacy paths |
| `src/tool/target_registry.py` | Used by BOTH paths |
| `src/tool/target_store.py` | Used by BOTH paths |
| `src/tool/execution_backend.py` | Used by BOTH paths |
| `src/tool/linux_tool.py` | Used by BOTH paths |
| `src/tool/zabbix_tool.py` | Used by BOTH paths |
| `src/tool/grafana_tool.py` | Used by BOTH paths |
| `src/tool/tool.py` | Used by BOTH paths |
| `src/tool/shell_tool.py` | Used by legacy path only (deterministic doesn't use shell tool) |
