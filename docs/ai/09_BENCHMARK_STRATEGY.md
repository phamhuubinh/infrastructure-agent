# 09 - Benchmark Strategy
This document defines how the platform measures investigation quality.
Benchmarks evaluate the complete investigation pipeline rather than the language model alone.
Every significant platform improvement should be validated through benchmarks.
---
# Purpose
Benchmarking ensures that platform evolution is measurable.
Every architectural or implementation change should improve one or more measurable metrics.
The platform should evolve through evidence rather than assumptions.
---
# What Is Being Measured
Benchmarks evaluate the investigation process.
They do not evaluate writing style.
They do not evaluate prompt quality alone.
The objective is to measure how effectively the platform performs infrastructure investigations.
---
# Investigation Pipeline
Every benchmark evaluates the following pipeline.
```
User Request
↓
Intent Resolution
↓
Target Resolution
↓
Evidence Planning
↓
Execution
↓
Evidence Collection
↓
Assessment
↓
Final Response
```
The benchmark may evaluate any stage independently or the pipeline as a whole.
---
# Benchmark Categories
The platform measures multiple quality dimensions.
## Intent Resolution
Measures whether the correct investigation objective is selected.
Examples
- Machine Assessment
- Application Discovery
- Monitoring Assessment
- Security Assessment
Metrics
- accuracy
- ambiguity rate
- incorrect classification rate
---
## Target Resolution
Measures whether the correct investigation target is identified.
Examples
```
localhost
```
```
monitor
```
```
database
```
Metrics
- resolution accuracy
- missing target rate
- incorrect target rate
---
## Evidence Planning
Measures whether the correct evidence template is selected.
Metrics
- required evidence coverage
- unnecessary evidence collection
- missing required evidence
---
## Capability Selection
Measures whether the correct capabilities are executed.
Metrics
- capability precision
- capability recall
- redundant capability execution
---
## Execution
Measures execution quality.
Metrics
- execution latency
- parallel execution ratio
- successful capability rate
- failed capability rate
---
## Evidence Quality
Measures the quality of collected evidence.
Metrics
- completeness
- correctness
- normalization quality
- duplicate evidence
- missing evidence
---
## Assessment
Measures assessment quality.
Metrics
- factual accuracy
- explanation quality
- recommendation quality
- hallucination rate
---
## Token Efficiency
Measures language model efficiency.
Metrics
- prompt tokens
- completion tokens
- total tokens
- token reduction compared to baseline
The platform should reduce token usage over time.
---
## Iteration Efficiency
Measures execution efficiency.
Metrics
- model calls
- tool calls
- execution iterations
- average investigation depth
Fewer iterations are preferred whenever investigation quality is preserved.
---
## Runtime Performance
Measures platform performance.
Metrics
- response latency
- execution time
- infrastructure calls
- parallel execution efficiency
---
# Benchmark Dataset
Every benchmark should define:
- user request
- expected intent
- expected target
- expected evidence
- expected assessment
Expected behaviour must be deterministic whenever possible.
---
# Regression Testing
Every benchmark should be rerunnable.
Regression occurs when:
- investigation accuracy decreases
- evidence quality decreases
- token usage increases
- iterations increase
- latency increases
without an intentional architectural decision.
---
# Platform Evolution
New functionality should be introduced because benchmark results reveal missing capabilities.
Avoid adding features based solely on assumptions.
Benchmark results should guide platform evolution.
---
# Benchmark Principles
Benchmarks should be:
- deterministic
- repeatable
- automated
- measurable
- implementation independent
They should evaluate observable behaviour rather than internal implementation.
---
# Success Criteria
A platform improvement is considered successful only if it produces measurable benefits.
Examples include:
- higher investigation accuracy
- better evidence quality
- lower token usage
- fewer iterations
- lower latency
- improved capability reuse
Architectural complexity without measurable improvement is not considered progress.
---
# Final Principle
The platform should evolve through benchmark-driven improvements.
Every significant change should demonstrate measurable value before becoming part of the architecture.
If a change cannot improve benchmark results, it should be questioned before implementation.
