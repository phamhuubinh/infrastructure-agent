# Assessment Metrics

## Metric Definitions

### Evidence Coverage
- **Definition**: Fraction of expected evidence topics mentioned in the response
- **Calculation**: `matched_evidence / total_expected_evidence`
- **Range**: 0.0 – 1.0
- **Method**: Case-insensitive keyword matching against expected evidence names

### Recommendation Coverage
- **Definition**: Fraction of expected recommendations mentioned in the response
- **Calculation**: `matched_recommendations / total_expected_recommendations`
- **Range**: 0.0 – 1.0
- **Method**: Case-insensitive keyword matching

### Grounding
- **Definition**: Whether assessment statements reference specific evidence
- **Calculation**: Weighted checks for evidence names, capability names, data values in response
- **Range**: 0.0 – 1.0

### Completeness
- **Definition**: Whether response covers required sections (Summary, Assessment, Risks, Unknowns, Recommendations)
- **Calculation**: Keyword presence for each section header
- **Range**: 0.0 – 1.0

### Consistency
- **Definition**: Whether response is internally consistent (placeholder for future improvement)
- **Calculation**: Currently always 1.0 (reserved for future semantic analysis)
- **Range**: 0.0 – 1.0

### Assessment Length
- **Definition**: Character count of assessment content
- **Range**: 0 – unlimited
- **Purpose**: Monitor response size changes

### Prompt Size
- **Definition**: Byte size of prompt sent to LLM
- **Range**: 0 – unlimited
- **Purpose**: Track token usage

### Completion Size
- **Definition**: Byte size of LLM response
- **Range**: 0 – unlimited
- **Purpose**: Track token usage

### Latency
- **Definition**: Wall-clock time for complete assessment (prompt + LLM + parsing)
- **Range**: 0 – unlimited (milliseconds)
- **Purpose**: Track performance

### Success
- **Definition**: Whether assessment completed without error
- **Range**: 0 or 1
- **Purpose**: Track reliability

## Overall Score

```
overall = evidence_coverage * 0.30
        + recommendation_coverage * 0.20
        + grounding * 0.20
        + completeness * 0.20
        + success * 0.10
```

Weights are configurable. Defaults prioritize evidence coverage and grounding.
