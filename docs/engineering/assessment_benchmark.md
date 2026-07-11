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

## Baseline (deepseek-ai/DeepSeek-V4-Flash via sv1)

| Metric | Value |
|---|---|
| Assessment latency | 27–46s (4 scenarios) |
| Prompt size | ~2.7KB |
| Response size | ~0.5-1KB |
| Success rate | 100% |
| Error rate | 0% |
| Evidence coverage | 0.80–1.00 |
| Grounding | 1.00 |
| Completeness | 1.00 |

Baseline captured in `.benchmark_history.json` run #2 with full metadata (model, server, git commit, timestamp, provider).

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
```

## Regression Detection

Regression detection is model/server-aware. When `--save` is used, the new run is compared against the most recent historical run with the same `model` and `server`. Runs with different models are not compared (would produce meaningless deltas).

Historical runs without metadata fall back to comparing against the last run in history (backward compatible).
