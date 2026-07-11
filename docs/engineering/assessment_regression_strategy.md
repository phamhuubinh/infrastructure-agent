# Assessment Regression Strategy

## What Constitutes a Regression

| Metric | Regression Threshold | Rationale |
|---|---|---|
| `evidence_coverage` | Decrease > 0.15 | Evidence coverage should be stable |
| `recommendation_coverage` | Decrease > 0.15 | Recommendation quality should not degrade |
| `grounding` | Decrease > 0.15 | Grounding is critical for reliability |
| `completeness` | Decrease > 0.15 | Response structure should be consistent |
| `overall` | Decrease > 0.15 | Composite quality should not degrade |
| `latency_ms` | Increase > 2x | Performance regression (network variance expected) |
| `success` | Decrease from 1.0 | Reliability regression |

## Detection Mechanism

The existing `benchmark/registry.py` already supports regression detection:

```python
regressions = detect_regressions(new_results)
```

It compares the current run against the most recent previous run.
A regression is flagged when a metric decreases below the threshold (default 0.15).

## Configuration

Thresholds are defined as constants in the evaluator module and can be overridden:

```python
REGRESSION_THRESHOLD = 0.15  # default threshold for all quality metrics
```

## What Is NOT a Regression

- Style changes (the evaluator does not compare language)
- Length changes within 2x (variance is expected with different models)
- Different wording for the same concept (keyword matching allows synonyms)
