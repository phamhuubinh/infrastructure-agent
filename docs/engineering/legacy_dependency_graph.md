# Legacy Runtime Dependency Graph

## Production Path (CLI default)

```
CLI (no --legacy)
    ↓
runtime_factory.create_deterministic_agent()
    ↓
DeterministicAgent
    ↓
ExecutionEngine
    ↓
Pipeline (7 components)
    ↓
KnowledgeTool → Child Tools
    ↓
EvidencePackage
    ↓
AssessmentModelAdapter.assess()
```

**Zero legacy dependencies.** This is the sole production path.

## Legacy Path (CLI --legacy)

```
CLI (--legacy)
    ↓
Agent.__init__()
    ├── ModelAdapter (abstract)
    │     ├── Action
    │     ├── FinalResponse
    │     └── Observation
    ├── ToolRegistry
    │     └── Tool (ShellTool, KnowledgeTool)
    └── KnowledgeTool.get_capability_metadata()
          └── (existing tool metadata)

Agent.run()
    ↓
ModelAdapter.reason()  [OllamaModelAdapter or MockModelAdapter]
    ├── prompt_builder.build_prompt()
    │     └── observation → str
    ├── action_parser.parse_response()
    │     └── JSON → Action | FinalResponse
    └── Action(tool, arguments)

    ↓
ToolRegistry.get(tool_id)
    ↓
Tool.execute(arguments)
    ↓
Observation(data, success, error)

    ↓
evidence_extractor.extract_known_facts()
    ↓
ReasoningState.add_observation()

    ↓
loop until FinalResponse
```

## Complete Dependency Table

```
Component                          Imported By                                      Is Legacy?
────────────────────────────────── ─────────────────────────────────────────────── ───────────
agent.py (Agent)                   cli.py (if args.legacy), benchmark (--legacy)   YES
tool_registry.py (ToolRegistry)    agent.py, cli.py, benchmark (_legacy)           YES
action.py (Action)                 agent.py, model_adapter.py, action_parser.py,   YES
                                   ollama_model_adapter.py, mock_model_adapter.py,
                                   reasoning_state.py
final_response.py (FinalResponse)  agent.py, model_adapter.py, action_parser.py,   YES
                                   ollama_model_adapter.py, mock_model_adapter.py
reasoning_state.py (ReasoningState) agent.py                                        YES
action_parser.py (parse_response)  ollama_model_adapter.py                         YES
prompt_builder.py (build_prompt)   ollama_model_adapter.py                         YES
evidence_extractor.py (extract)    agent.py                                        YES
model_adapter.py (ModelAdapter)    agent.py, ollama_model_adapter.py,              YES
                                   mock_model_adapter.py
mock_model_adapter.py              benchmark (_legacy), test_agent.py              YES
ollama_model_adapter.py            cli.py (if args.legacy)                         YES
observation.py (Observation)       agent.py, model_adapter.py, action_parser.py,  YES
                                   ollama_model_adapter.py, mock_model_adapter.py,
                                   evidence_extractor.py
```

## Shared (Non-Legacy) Files Used by Both Paths

```
KnowledgeTool       — used by both legacy and deterministic paths
TargetRegistry      — used by both (but differently: legacy via cli, deterministic via factory)
LinuxTool           — used by both
ZabbixTool          — used by both
GrafanaTool         — used by both
Tool (base)         — used by both
execution_backend   — used by both
target_store        — used by both (legacy via cli, deterministic via factory)
CLI (--target-file) — used by both (deterministic: passed to factory; legacy: used directly)
```

## Isolation Verification

Every legacy component has been confirmed to be:

1. **Not imported by `src/agent/runtime_factory.py`** — the deterministic composition root
2. **Not imported by `src/agent/deterministic_agent.py`** — the production agent
3. **Not imported by any `src/pipeline/` component** — the deterministic pipeline
4. **Not imported by `src/model/assessment_model_adapter.py`** or `mock_assessment_adapter.py`
5. **Not imported by any benchmark file's default (non-legacy) code path**

The legacy subgraph is fully isolated and entirely opt-in via `--legacy`.
