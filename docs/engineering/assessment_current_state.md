# Assessment Current State

## Execution Flow

```
User
  ↓
CLI
  ↓
create_deterministic_agent()
  ↓
DeterministicAgent
  ├── ExecutionEngine (investigation)
  └── MockAssessmentAdapter (assessment)
        └── deterministic summary (no LLM)
```

## Current Components

| Component | Status | Purpose |
|---|---|---|
| `AssessmentRequest` | Stable | Immutable input to assessment. Contains raw_request, intent, evidence, completeness. |
| `EvidencePackage` | Stable | Typed evidence item. capability_name, evidence_name, data, success, error. |
| `AssessmentModelAdapter` | Stable | Abstract interface: `assess(AssessmentRequest) -> str`. |
| `MockAssessmentAdapter` | Active | Implements AssessmentModelAdapter. Returns structured summary without LLM. |
| `PromptBuilderV2` | Active | Builds JSON prompt from AssessmentRequest. ~2.7KB. |
| `RuntimeFactory` | Active | Wires DeterministicAgent with MockAssessmentAdapter. |

## Missing Infrastructure

| Gap | Impact |
|---|---|
| No LLM client | Cannot call any model API |
| No LLM adapter | AssessmentModelAdapter has no real implementation |
| No configuration | Model server, API key, model name are hardcoded |
| No error handling | Network failures, timeouts, API errors are unhandled |
| No retry | Transient failures abort assessment |
| No assessment result type | `assess()` returns raw `str` |
| CLI has no --server/--model | No way to select model configuration |

## Integration Point

The production adapter must integrate between:

```
AssessmentRequest
  ↓
PromptBuilderV2 (already exists)
  ↓
[LLM Client] (NEW)
  ↓
[LLMAssessmentAdapter] (NEW)
  ↓
AssessmentResult (NEW)
```

`RuntimeFactory.create_deterministic_agent()` must accept an optional configuration
to select between `MockAssessmentAdapter` and `LLMAssessmentAdapter`.
