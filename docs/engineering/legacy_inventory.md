# Legacy Runtime Inventory

## Source Files

| # | File | Lines | Type | Responsibility |
|---|---|---|---|---|
| 1 | `src/agent/agent.py` | 163 | Legacy Agent | ReAct loop: model → tool → observation → model |
| 2 | `src/tool/tool_registry.py` | 34 | Tool Registry | Maps tool_id → Tool instance for ReAct dispatch |
| 3 | `src/shared/reasoning/action.py` | 13 | Dataclass | `Action(tool, arguments)` — model decision for next tool call |
| 4 | `src/shared/reasoning/final_response.py` | 14 | Dataclass | `FinalResponse(content)` — model terminal output |
| 5 | `src/shared/reasoning/reasoning_state.py` | 60 | State Manager | Tracks observations and deduplicates tool calls |
| 6 | `src/model/protocol/action_parser.py` | 96 | Parser | Parses LLM JSON response into `Action` or `FinalResponse` |
| 7 | `src/model/protocol/prompt_builder.py` | 404 | Prompt Builder | Builds ReAct prompt with RULES, capability descriptions, examples |
| 8 | `src/shared/evidence_extractor.py` | 42 | Fact Extractor | Extracts known facts from observations for prompt context |
| 9 | `src/model/model_adapter.py` | 27 | Abstract Base | `ModelAdapter.reason()` → `Action | FinalResponse` |
| 10 | `src/model/mock_model_adapter.py` | 28 | Mock Adapter | Mock for testing legacy Agent |
| 11 | `src/model/ollama_model_adapter.py` | 74 | Ollama Adapter | Wraps Ollama client in ModelAdapter interface |
| 12 | `src/shared/discovery/observation.py` | 19 | Dataclass | `Observation(data, success, error, tool, arguments)` |

## Test Files

| # | File | Lines | Tests |
|---|---|---|---|
| 13 | `tests/agent/test_agent.py` | 640 | Legacy Agent behavior (10+ test classes) |
| 14 | `tests/tool/test_tool_registry.py` | 49 | ToolRegistry registration/retrieval |
| 15 | `tests/model/protocol/test_action_parser.py` | 242 | JSON response parsing |
| 16 | `tests/model/protocol/test_prompt_builder.py` | 163 | ReAct prompt construction |
| 17 | `tests/model/test_mock_model_adapter.py` | 37 | Mock adapter behavior |
| 18 | `tests/model/test_ollama_model_adapter.py` | 61 | Ollama adapter behavior |
| 19 | `tests/shared/discovery/test_observation.py` | 59 | Observation dataclass |

## Benchmark Files

| # | File | Lines | Notes |
|---|---|---|---|
| 20 | `benchmark/__main__.py` (_build_legacy_runtime) | ~40 lines | Only inside `--legacy` branch |
| 21 | `benchmark/runner.py` | 77 | Legacy runner — accepts `agent_run` callable |

## Infrastructure Files

| # | File | Lines | Notes |
|---|---|---|---|
| 22 | `src/infrastructure/ollama/ollama_client.py` | 53 | HTTP client — used by legacy Ollama adapter |
| 23 | `src/infrastructure/openai/openai_client.py` | 105 | HTTP client — used by legacy client builder |
| 24 | `src/cli.py` (_run_agent legacy branch) | ~30 lines | Only inside `if args.legacy:` |

## Documentation Files Referencing Legacy Architecture

| # | File | Path |
|---|---|---|
| 25 | `README.md` | Repository root (mentions `--legacy` flag) |
| 26 | Various `.md` in `docs/` | `docs/component_specifications/`, `docs/tool_behavior/`, `docs/runtime_behavior/`, `docs/api_specifications/`, `docs/adr/` |

**Total legacy source lines:** ~937 (excluding infrastructure clients)
**Total legacy test lines:** ~1,281
**Total files:** 24 (including tests, excluding infrastructure and docs)
