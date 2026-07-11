# Assessment Sequence

## Normal Flow

```
DeterministicAgent.run(user_request)
  │
  ├── ExecutionEngine.execute(user_request)
  │     └── returns InvestigationRequest with evidence
  │
  ├── AssessmentAdapter.build(investigation)
  │     └── returns AssessmentRequest
  │
  ├── LLMAssessmentAdapter.assess(assessment_request)
  │     ├── PromptBuilderV2.build_assessment_prompt(req)
  │     │     └── returns JSON prompt string (~2.7KB)
  │     ├── LLMClient.generate(prompt)
  │     │     ├── POST /v1/chat/completions
  │     │     ├── Receive response
  │     │     └── Return content string
  │     └── Return AssessmentResult
  │
  └── Return assessment string to caller
```

## Error Flow

```
LLMAssessmentAdapter.assess(assessment_request)
  │
  ├── PromptBuilderV2 (always succeeds — pure function)
  │
  ├── LLMClient.generate(prompt)
  │     ├── HTTP error → raise AssessmentError
  │     ├── Timeout → raise AssessmentError
  │     ├── Invalid response → raise AssessmentError
  │     └── Success → return string
  │
  ├── On AssessmentError:
  │     └── Return AssessmentResult with:
  │           content = error message
  │           success = False
  │           error = str(exception)
  │
  └── Assessment never modifies investigation results
```

## Retry Strategy

- No retry in this phase.
- Transient failures return `AssessmentResult(success=False)`.
- Caller (DeterministicAgent) decides whether to retry.
- Retry belongs to future infrastructure, not the adapter.
