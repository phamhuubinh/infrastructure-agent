# Assessment Evaluation Architecture

## Principles

1. **No AI in evaluation** — The evaluator is deterministic code only.
2. **No prompt generation** — The evaluator never builds prompts.
3. **No HTTP** — The evaluator never makes network calls.
4. **Content-agnostic where possible** — Evaluate structure, coverage, and completeness, not writing style.

## Data Flow

```
Benchmark Dataset
  └─ expected_evidence: list[str]       # what evidence should be covered
  └─ expected_recommendations: list[str] # what recommendations should appear
  └─ expected_risks: list[str]           # what risks should be identified
  └─ ...
       ↓
AssessmentEvaluator.evaluate(response, expected)
       ↓
AssessmentMetrics
  ├── evidence_coverage       # fraction of expected evidence mentioned
  ├── recommendation_coverage # fraction of expected recommendations mentioned
  ├── grounding               # whether statements reference evidence (keyword-based)
  ├── completeness            # whether response covers all required sections
  ├── consistency             # whether response is self-consistent
  ├── length                  # character count
  ├── prompt_size             # bytes of prompt sent
  ├── completion_size         # bytes of response received
  ├── latency_ms              # milliseconds
  ├── success                 # whether assessment completed without error
  └── overall                 # weighted composite score
```

## Responsibilities

| Component | Responsibility | Never |
|---|---|---|
| `AssessmentEvaluator` | Compute deterministic metrics from response + expected | AI, HTTP, prompts |
| `AssessmentMetrics` | Typed score dataclass | Persistence |
| `Benchmark dataset` | Define expected characteristics per scenario | Evaluation logic |
