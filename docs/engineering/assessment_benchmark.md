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

## LLM Assessment (v1)

To be measured after deployment with real model.

## Running

```bash
# Mock assessment benchmark
python -m benchmark --domain assessment

# LLM assessment benchmark (requires configured server)
python -m benchmark --domain assessment --server sv1
```
