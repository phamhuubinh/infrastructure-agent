# Assessment Benchmark

## Purpose

Measure LLM assessment performance independently from investigation.

## Metrics

| Metric | Description |
|---|---|
| Assessment latency | Time from prompt construction to response |
| Prompt size | Bytes sent to LLM |
| Response size | Bytes received from LLM |
| Success rate | Percentage of successful assessments |
| Error rate | Percentage of failed assessments |
| Token usage | Estimated tokens (if model reports usage) |

## Baseline (Mock)

| Metric | Value |
|---|---|
| Assessment latency | ~0.001s |
| Prompt size | ~2.7KB |
| Response size | ~0.2KB |
| Success rate | 100% |
| Error rate | 0% |
| Evidence coverage | 0.00–1.00 (0 for most, 1.0 for "performance_assessment") |
| Grounding | 0.00–1.00 |
| Completeness | 0.25 (only "Evidence" section present) |

## Baseline (deepseek-ai/DeepSeek-V4-Flash via sv1)

### Assessment domain (4 scenarios, --repeat 3)

| Metric | Value | Variance (std) |
|---|---|---|
| Assessment latency | 25–50s per scenario | — |
| Prompt size | ~2.7KB | — |
| Response size | ~0.5-1KB | — |
| Success rate | 100% | — |
| Error rate | 0% | — |
| Evidence coverage | 0.80–1.00 | **0.0** (perfectly stable) |
| Grounding | 1.00 | **0.0** (perfectly stable) |
| Completeness | 1.00 | **0.0** (perfectly stable) |
| Overall (assessment) | 0.80–0.93 | 0.0–0.03 |

**Key finding**: Assessment metrics are perfectly reproducible (std=0.0 for evidence_coverage, grounding, completeness). The small variance in `overall` comes from the `_score_evidence()` keyword check, not the assessment evaluator.

### Scenario_localhost domain (1 scenario)

| Metric | Value |
|---|---|
| Evidence coverage | N/A (no assessment metrics for this domain) |
| Investigation score | 0.65 (WARN — reason=0.00 due to empty capability sequence) |

### Scenario_investigation domain (6 scenarios)

| Metric | Value |
|---|---|
| Investigation scores | 0.65–0.70 |
| Average | 0.69 |

## Running

```bash
# Mock assessment benchmark
python -m benchmark --domain assessment

# LLM assessment benchmark (requires configured server)
python -m benchmark --domain assessment --server sv1

# LLM assessment with reproducibility measurement
python -m benchmark --domain assessment --server sv1 --repeat 3

# Save results and check regressions
python -m benchmark --domain assessment --server sv1 --save

# Other domains with real-model baseline
python -m benchmark --domain scenario_investigation --server sv1 --save
```

## Regression Detection

Regression detection is model/server-aware. When `--save` is used, the new run is compared against the most recent historical run with the same `model` and `server`. Runs with different models are not compared (would produce meaningless deltas).

Historical runs without metadata fall back to comparing against the last run in history (backward compatible).

## Known Capability-Routing Gap

Run #3 (scenario_localhost, real model) surfaced a discrepancy between tool `covers` tags and the `_COVERS_TO_OPERATIONAL` convention mapping:

| Operational Capability | Tool Capability | covers tag | convention key |
|---|---|---|---|
| CPU Information | `get_cpu` | `cpu` | `cpu` → CPU Information |
| CPU Utilization | `get_cpu_usage` | `cpu` | `cpu_usage` → CPU Utilization |
| Memory Information | `get_memory` | `memory` | `memory` → Memory Information |
| Memory Utilization | `get_memory` | `memory` | `memory_usage` → Memory Utilization |
| Disk Usage | `get_disk_usage` | `storage` | `disk_usage` → Disk Utilization |

Both `get_cpu` and `get_cpu_usage` cover `"cpu"`, so the router registers only one route (CPU Information). CPU Utilization never gets a route because no tool emits `covers=("cpu_usage",)`. Same pattern for Memory Utilization and Disk Utilization.

**Impact**: The pipeline collects the evidence (the underlying tool calls succeed), but the CapabilityRouter has no entry for these capabilities. The assessment model sees a failure entry in the evidence and reports "CPU/memory/disk usage were not collected."

**Fix**: Either (a) add `"cpu_usage"`, `"memory_usage"`, `"disk_usage"` to `get_cpu_usage`, `get_memory`, `get_disk_usage` covers tuples, or (b) add the missing routes directly to `_COVERS_TO_OPERATIONAL` mapping. This is a candidate for a future capability-routing cleanup milestone, out of scope for benchmark infrastructure work.
