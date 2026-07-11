# Assessment Benchmark Current State

## Current Benchmark Architecture

```
benchmark/dataset.py     → defines BENCHMARKS list (investigation scenarios)
benchmark/__main__.py    → runs agent, calls scoring
benchmark/scoring.py     → scores investigation quality (reasoning, efficiency, evidence, safety)
benchmark/report.py      → generates human/JSON reports
benchmark/registry.py    → saves/loads history, detects regressions
```

## What the Current Benchmark Evaluates

| Metric | What it measures | Assessment-specific? |
|---|---|---|
| `reasoning` | Whether correct capabilities were selected | No (investigation) |
| `efficiency` | Whether capability calls were reasonable | No (investigation) |
| `evidence` | Whether response contains evidence/assessment keywords | Weak — checks text keywords |
| `safety` | Whether destructive actions were refused | No (safety) |

## What Is Missing

The current benchmark:
- Cannot evaluate assessment quality independently
- Does not compare expected vs actual assessment content
- Cannot detect assessment regressions (coverage decreasing, grounding failing)
- Does not measure prompt size, completion size, or token usage
- Does not have assessment-specific benchmark scenarios
- The `_score_evidence()` function only checks for keyword presence, not semantic coverage

## What We Need

```
AssessmentRequest
    ↓
LLMAssessmentAdapter
    ↓
AssessmentResult        [content, success, latency, model]
    ↓
AssessmentEvaluator     [deterministic, no AI]
    ↓
AssessmentMetrics       [coverage, grounding, completeness, length, latency]
    ↓
Benchmark Report + Regression Detection
```
