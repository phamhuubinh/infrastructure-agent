# ADR-0002
# Status
Accepted
---
# Context
The investigation pipeline is primarily deterministic: intent resolution, target resolution, evidence planning, capability selection, execution scheduling, and evidence collection all run without any LLM call. Only the final step — interpreting the collected evidence — needs the reasoning capability of a language model.

The original architecture allowed the model to participate in earlier pipeline stages (intent recognition, execution planning). This created several problems:
- The model needed access to tool metadata, capability lists, and infrastructure context, coupling the model layer to execution internals.
- Token usage grew because prompts had to include tool schemas and capability metadata.
- Latency increased because the model was consulted before execution could begin.
- Non-determinism in planning made benchmarking and regression testing unreliable.
- The pipeline could not complete offline (without an LLM) because the model was required to plan, not just assess.

The Assessment Layer — the final step that transforms evidence into findings and recommendations — is the only part of the pipeline that genuinely benefits from LLM-level reasoning. All earlier stages can and should be deterministic.
---
# Decision
The LLM is used exclusively for assessment.

Specifically:

1. **The LLM receives completed evidence only.** It never sees tool schemas, capability metadata, execution plans, or raw infrastructure access. The pipeline delivers a finished `AssessmentRequest` containing only the evidence that was collected, plus the original user request and the resolved intent.

2. **The LLM never participates in execution.** It does not choose targets, plan evidence collection, select capabilities, or schedule execution. All of those stages are deterministic code.

3. **The LLM has no access to tools.** The `AssessmentModelAdapter` interface (`src/model/assessment_model_adapter.py`) exposes only `assess()` — it has no tool registry, no capability library, and no execution context. The `LLMAssessmentAdapter` (`src/model/llm_assessment_adapter.py`) uses a `PromptBuilderV2` to construct a prompt from the evidence package alone.

4. **The pipeline can run without an LLM.** A `MockAssessmentAdapter` (`src/model/mock_assessment_adapter.py`) provides deterministic output for testing and offline mode, proving that the pipeline does not depend on the model for execution.

5. **The boundary is enforced by the adapter contract.** `AssessmentAdapter` (`src/pipeline/assessment_adapter.py`) is the only bridge between the deterministic pipeline and the model layer. It constructs an `AssessmentRequest` from the investigation's evidence — and nothing else. The model layer never imports from `src/pipeline/`, `src/tool/`, or `src/execution/`.

6. **The `assess_raw()` method is a narrow escape hatch.** It exists on the interface for general chat and question classification where no evidence package exists. It is not used in the investigation pipeline.
---
# Consequences

## Positive
- Token usage is minimized: prompts contain only evidence, not tool schemas or capability metadata.
- Latency is reduced because the model is called only once per investigation, not multiple times during planning.
- The pipeline is deterministic and testable without an LLM.
- The model layer is decoupled from execution internals. A model swap requires no change to the pipeline.
- Regression testing is reliable because evidence collection always produces the same result regardless of model choice.

## Negative
- The model cannot recover from incomplete evidence by requesting more data — it must assess what it receives.
- The model cannot adapt its assessment strategy based on tool availability or infrastructure context.

## Mitigations
- The `EvidenceCompleteness` stage (before assessment) ensures the evidence package is as complete as possible, reducing recovery need.
- The assessment output can flag insufficient evidence and recommend re-investigation, which is handled as a new pipeline invocation.
---
# Referenced files
- `src/pipeline/assessment_adapter.py` — adapter that builds AssessmentRequest from pipeline evidence
- `src/model/assessment_model_adapter.py` — abstract interface for assessment-only models
- `src/model/llm_assessment_adapter.py` — real LLM adapter (no tool access)
- `src/model/mock_assessment_adapter.py` — deterministic stand-in for testing
- `src/pipeline/assessment_request.py` — data class for assessment input
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` — short-form AD-002 summary of this decision
