# Repository Cleanup Audit

## Dead Code Found

### Empty packages (already removed in earlier sprint, confirming no remnants):
- `src/planner/` — **removed**
- `src/knowledge_model/` — **removed**
- `src/prompts/` — **removed** (but reference remains in scripts)
- `src/capability/` — **removed**
- `src/discovery/` — **removed**
- `src/executor/` — **removed**
- `src/agent_core/` — **removed**
- `src/verification/` — **removed**
- `src/execution/` — **removed**
- `src/shared/reasoning/__init__.py` — **removed**

### Broken files:

1. **`scripts/prompt_benchmark.py`** — imports `from src.prompts.prompt_loader import load_prompt` which doesn't exist. The `src/prompts/` package was removed. This script is already broken and unreachable.

### Stale cache files:

2. **`__pycache__/` directories** — 29 directories exist across the source tree. These are automatically generated and can be cleaned with `find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null`.

### Orphan test references:

3. **`tests/runtime/` and `tests/schema/`** — Only `.pyc` files remain (no `.py` source). These are completely orphaned. The directories should be cleaned up.

## Unused Imports in Legacy Code

The following imports will be resolved automatically when legacy files are removed:

| File | Import | Used? |
|---|---|---|
| `src/cli.py` | `Agent`, `OllamaModelAdapter`, `ToolRegistry`, `ShellTool` | Only in `if args.legacy:` |
| `src/cli.py` | `OllamaClient`, `OpenAIClient` | Only in `_build_client()` inside `if args.legacy:` |
| `benchmark/__main__.py` | `Agent`, `ToolRegistry`, `MockModelAdapter` | Only in `_build_legacy_runtime()` |

## Duplicate Implementations

| Concept | Legacy Implementation | Deterministic Replacement |
|---|---|---|
| State management | `ReasoningState` | `InvestigationRequest` |
| Evidence storage | `Observation` | `EvidencePackage` |
| Model interface | `ModelAdapter` | `AssessmentModelAdapter` |
| Tool dispatch | `ToolRegistry` | `CapabilityRouter` |
| Prompt | `prompt_builder.py` (22KB) | `prompt_builder_v2.py` (2.7KB) |
| Output parsing | `action_parser.py` | None needed (model returns str) |
| Known facts | `evidence_extractor.py` | `EvidencePackage` + `AssessmentRequest` |
| Agent loop | `Agent` (ReAct) | `DeterministicAgent` (single pass) |
| Benchmark runner | `runner.py` | Direct in `__main__.py` |

## Obsolete Documentation

The following directories contain documentation for the legacy ReAct architecture that is no longer current:

| Directory | Content |
|---|---|
| `docs/component_specifications/` | 11+ files describing legacy components (Agent, ToolRegistry, execution_environment, lifecycle_manager, result_collector, result_dispatcher, transition_policy) |
| `docs/tool_behavior/` | 3 files describing legacy tool execution patterns |
| `docs/runtime_behavior/` | 6 files describing legacy runtime behavior |
| `docs/api_specifications/` | 2 files describing legacy API contracts |
| `docs/adr/` | 4 ADR files describing legacy architectural decisions |

These should be archived or removed after the legacy retirement is complete. The `docs/ai/` directory is the current Source of Truth.

## Aider Artifacts

| File | Size | Description |
|---|---|---|
| `.aider.chat.history.md` | 167 KB | Aider chat history — not source code |
| `.aider.input.history` | 6 KB | Aider input history |
| `.aider.tags.cache.v4/` | 127 KB | Aider cache directory |

These should be added to `.gitignore` if not already. They are not part of the repository source.
