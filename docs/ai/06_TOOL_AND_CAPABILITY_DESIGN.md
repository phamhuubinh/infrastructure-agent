# 06 - Tool and Capability Design
Defines how Child Tools and capabilities are designed. Applies regardless of local or platform deployment (`03_PLATFORM_ARCHITECTURE.md` does not change this contract).
## Purpose
Child Tools collect operational evidence, deterministically. They are never responsible for reasoning, planning, assessment, or workflow decisions.
## Tool responsibilities
Every Child Tool should: collect operational evidence, normalize outputs, expose capability metadata, validate parameters, return deterministic results.
Child Tools should never: interpret evidence, make recommendations, generate conclusions, or communicate with the Assessment Model directly. All Child Tool output flows back through the pipeline (`05_EXECUTION_PIPELINE.md`), not to the model.
## Domain ownership
Each Child Tool owns exactly one infrastructure domain and must never access another domain.
Implemented today (`src/tool/`): `LinuxTool` (SSH execution), `GrafanaTool`, `ZabbixTool`, `InternetTool` (HTTP fetch with SSRF protection), `KnowledgeBaseTool` (RAG service proxy), all behind `KnowledgeTool`.
Possible future domains (not implemented, listed only as examples of the pattern — do not build until there is a real need): `DockerTool`, `VMwareTool`, `GraylogTool`.
## InternetTool and SSRF protection
`InternetTool` (`src/tool/internet_tool.py`) fetches external URLs and returns content as text or parsed JSON. It is **opt-in per request** — never invoked automatically by the pipeline (see `04_ROADMAP.md`, WP4 rule). SSRF protection is built-in at two levels:
1. Direct address check: rejects RFC 1918, RFC 6890, and other private address ranges before making any request.
2. DNS resolution guard: resolves the hostname and blocks the request if any resolved address falls within private ranges.
This is the only Child Tool that makes outbound network calls beyond the local infrastructure domain.

## KnowledgeTool is the single entry point
`KnowledgeTool` (`src/tool/knowledge_tool.py`) aggregates Child Tool capability metadata and dispatches execution. The pipeline never calls a Child Tool directly. This is intentional — it keeps capability metadata as a single source of truth and avoids duplicated dispatch logic across the pipeline.
## Capability ownership
Every capability belongs to exactly one Child Tool (e.g. `running_services` belongs to `LinuxTool`). Capability implementations must never be duplicated across tools.
## Deterministic execution
A capability should produce the same result when run against the same infrastructure state. No hidden state — output depends only on input parameters and infrastructure state.
## Operational evidence, not raw output
Prefer normalized fields (`running`, `enabled`, `pid`, `port`, `version`) over large raw command dumps, unless raw output was explicitly requested.
## Composite vs atomic capabilities
Prefer composite, operational capabilities (`assess_machine()`) over forcing callers to chain low-level wrappers (`cpu()`, `memory()`, `disk()`, `filesystem()`, `network()`) — this reduces execution overhead, model interaction, and token usage. Composite capabilities should internally reuse atomic, reusable capabilities (`running_services`, `installed_packages`, `filesystem_usage`) rather than duplicate logic.
## Parameter validation & error handling
Validate before execution (missing target, unsupported capability, invalid arguments) and fail with structured errors. One capability failure should not terminate an entire investigation unless the failure prevents meaningful assessment — preserve whatever evidence was already collected and continue where possible (see `05_EXECUTION_PIPELINE.md`, Failure Handling).
## Capability metadata
Every capability should expose: name, description, supported targets, parameters, produced evidence, estimated execution cost, execution characteristics. Metadata describes behavior, not implementation.
## Performance & parallelism
Minimize unnecessary work — batch, cache within a single execution, run independent capabilities in parallel, prefer lightweight queries. Avoid duplicate infrastructure access.
## Source of truth
Child Tools should always prefer live infrastructure (the actual Linux host, the actual Grafana/Zabbix API) over cached information. Cached information never replaces live evidence.
## Stateless design
Child Tools must not retain execution history, previous observations, previous responses, or investigation state. Each execution is independent — this is what makes the pipeline benchmarkable and safe to run concurrently.
## Benchmarkability and evolution
Capability quality should be measurable via correctness, completeness, execution time, evidence quality, and failure behavior — capabilities should evolve through benchmark improvements, not feature expansion for its own sake (see `08_PROJECT_STATE.md` for current benchmark status). New capabilities should only be added when a benchmark scenario requires more evidence, an existing capability cannot answer an operational question, or reuse is clearly expected. Avoid speculative capability design.
## Final principle
A Child Tool exists to collect evidence, never to explain it. Evidence collection belongs to Child Tools. Evidence interpretation belongs to the Assessment Model (`05_EXECUTION_PIPELINE.md`, Step 9 — Assessment).
