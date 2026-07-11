# Assessment Benchmark Dataset

## Design

Each assessment benchmark extends the existing `Benchmark` dataclass with:

| Field | Type | Purpose |
|---|---|---|
| `expected_evidence` | `list[str]` | Evidence topics the assessment should cover |
| `expected_recommendations` | `list[str]` | Recommendations the assessment should include |
| `expected_risks` | `list[str]` | Risks the assessment should identify |
| `expected_sections` | `list[str]` | Required response sections |

## Example

```python
Benchmark(
    domain="assessment",
    name="health_check_assessment",
    request="Kiểm tra sức khỏe của localhost",
    expected_evidence=[
        "CPU Information",
        "Memory Information",
        "Disk Usage",
        "Services",
        "System Information",
    ],
    expected_recommendations=[
        "high disk usage",
        "memory pressure",
    ],
    expected_sections=[
        "Summary",
        "Assessment",
        "Risks",
        "Recommendations",
    ],
)
```

The evaluator checks whether each expected item is mentioned in the response using case-insensitive keyword matching. No exact wording comparison.
