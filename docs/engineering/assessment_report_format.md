# Assessment Report Format

## JSON Report Structure

```json
{
  "benchmark": "health_check_assessment",
  "domain": "assessment",
  "request": "Kiểm tra sức khỏe của localhost",
  "assessment": {
    "content": "Summary: ...",
    "success": true,
    "model": "gpt-4",
    "latency_ms": 1234.5,
    "prompt_size": 2764,
    "completion_size": 892
  },
  "metrics": {
    "evidence_coverage": 0.80,
    "recommendation_coverage": 0.50,
    "grounding": 0.75,
    "completeness": 1.0,
    "consistency": 1.0,
    "length": 892,
    "overall": 0.81
  },
  "errors": []
}
```

## Fields

| Path | Type | Description |
|---|---|---|
| `benchmark` | str | Benchmark scenario name |
| `domain` | str | Benchmark domain |
| `assessment.content` | str | Full assessment text |
| `assessment.success` | bool | Whether assessment completed |
| `assessment.model` | str | Model used |
| `assessment.latency_ms` | float | Wall-clock time |
| `assessment.prompt_size` | int | Prompt bytes |
| `assessment.completion_size` | int | Response bytes |
| `metrics.evidence_coverage` | float | 0.0–1.0 |
| `metrics.recommendation_coverage` | float | 0.0–1.0 |
| `metrics.grounding` | float | 0.0–1.0 |
| `metrics.completeness` | float | 0.0–1.0 |
| `metrics.overall` | float | Weighted composite 0.0–1.0 |
| `errors` | list[str] | Any errors encountered |

## Human Report Extension

The human report should add assessment-specific metrics alongside existing investigation scores:

```
  health_check_assessment    OK total=0.81 ev_cov=0.80 rec_cov=0.50 grounding=0.75 completeness=1.0 lat=1234ms
```
