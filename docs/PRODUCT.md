# Product

> Current full-product target is [DESIGN.md](refactor/DESIGN.md) under
> [REFACTOR_REQUEST.md](../REFACTOR_REQUEST.md): DeepSeek/Claude/OpenAI, Windows app,
> Linux headless CLI/service, web and Android/iOS clients sharing one runtime.
> Existing detailed sections below are migration inputs where compatible.

## Mission

Orion is a local-first assistant for personal and technical work, accessible through
a browser. One main model/runtime reasons over conversation, project knowledge and
tool results. Customer devices are execution targets, not additional AI agents.

This is the target product for the [2026-10-29 redesign](architecture/BASELINE_2026-10-29.md).
The latest amendment prioritizes Windows/Linux commands and removes dedicated
Grafana/Zabbix integrations from the target product (ADR 0017).
Source coverage and remaining verification are tracked separately in the
[implementation inventory](development/IMPLEMENTATION_STATUS.md).

## Primary navigation

```text
Chat | Projects | Remote Control
```

Settings configures the model/provider; it is not another assistant or a tool mode.

| Surface | Owns | Does not inherit |
| --- | --- | --- |
| Chat | Conversation, current attachments, model settings and mutation mode | Other conversations' private data |
| Project | Metadata/instructions, persistent documents and project conversations | Other projects' documents or authority |
| Device Chat in Remote Control | Endpoint-owned history and independent mutation mode | Ordinary Chat history/attachments or Project instructions/documents |

Projects use the Chat runtime with a bound project knowledge source. Each device
also uses that runtime, with a server-owned endpoint binding instead of a Project.
Selecting a different device opens its own workspace; it does not retarget an
existing Device Chat.

## Chat and Projects

Users state their goals without choosing tools or enabling a RAG mode. All
registered model-callable tool schemas are available on the first model turn.
The model can answer directly, retrieve documents, calculate, research the web,
inspect configured infrastructure, or combine sources in the same loop.

The application binds session/project/attachment identity, validates calls and
enforces permission. No keyword, regex or intent classifier chooses a tool before
the model. Project instructions provide task context and cannot widen permissions.

Project documents show upload, ingestion, ready or failed state and support source
navigation. A ready document must be queryable; semantic indexing has its own
readiness and must not hide usable lexical/exact reads. Document names and IDs
are knowledge identities, not remote filesystem paths.

## Remote Control

The landing page provides:

- Windows/Linux portable worker download for the compatible server release, with
  version and integrity metadata; unavailable builds show that state explicitly;
- one-use temporary pairing code with expiry;
- devices with display name, OS, online/offline state, capabilities and last seen.

The redesign prioritizes **Chat | Commands | Connection** in the device workspace.
Commands shows execution activity and bounded stdout/stderr. Existing Desktop,
Files, Processes and Browser views remain secondary conveniences, not prerequisites
for OS commands. Device Chat remains accessible offline; unavailable tools report
a bounded error. Manual desktop
control is a direct owner action with its own control-session authorization,
separate from model-call mutation approval.

The normal onsite workflow is download/extract → run → enter name and pairing
code → work → Disconnect/Exit. The worker initiates outbound HTTPS/WSS, has visible
status and requires no OS installation, Python/Node/npm, service, PATH change,
autostart or inbound listener. Local policy and OS rights limit capabilities;
running a worker does not guarantee desktop/browser support on every machine.

Temporary mode is the default: the credential stays in process memory, clean exit
ends it, and heartbeat expiry handles crashes or unreachable servers. Orion cleans
its own session files, not OS/security history. Explicit browser-runtime
provisioning may create a separate reusable cache; it must be disclosed rather
than described as session cleanup. Remembered mode remains an explicit optional
path for owned devices in the same worker/protocol.

Device Chat has no Project/RAG/attachment scope. Ordinary non-knowledge tools may
remain available. Every endpoint call is restricted to its bound endpoint at the
server; supplying another target reference cannot switch authority.
**End & forget** explicitly confirms removal of endpoint-owned identity/history
after checking active requests and runs.

## Tool, skill and mutation behavior

Tools are schema-defined operations. Skills are reusable task instructions that
use those tools; they have no independent AI runtime and grant no additional
permission. The skill-loading contract is a design target, not a verified current
feature. MCP connects external tools to the canonical registry.

Each Chat, Project and Device Chat has its own persisted permission:

| Mode | Effect |
| --- | --- |
| `read_only` (default) | Read operations only; mutations are blocked |
| `confirm` | Pause the same request for approval of one exact mutation |
| `auto` | Execute eligible mutations within server and worker policy ceilings |

Seeing a tool, selecting auto, or approving a call cannot widen server/worker/OS
policy. Cancellation is not rollback. A dispatched mutation with an unverified
result is reported as `outcome_unknown`; reconnect must not replay it.

The primary OS path accepts actual PowerShell/cmd commands on Windows and sh/bash
commands on Linux, including scripts/pipelines, using the same runtime. The shared
system.command.run/status/cancel contract targets workers or configured SSH and
captures stdout/stderr, exit state, duration, truncation, timeout and cancellation.
See [Commands](architecture/SYSTEM_COMMANDS.md).

Arbitrary command text is mutation-capable: read_only/scheduler cannot dispatch it.
confirm approves an exact command payload; auto uses explicit target command
capability and OS rights. No keyword/model read-only classifier, implicit elevation
or target switching is added. cwd/file-tool roots are not a shell sandbox.
These tools are design-only; current restricted worker/SSH operations require
a source migration before generic command execution is available.

## Knowledge and evidence

RAG is a tool/source subsystem rather than an independent assistant. Retrieve
current document evidence when the answer depends on document content.
`knowledge.search` discovers scoped content unless an exact visible document
identity supports a direct read. Listing metadata is not a required QA step.

Internet search discovers candidate pages; `internet.fetch` supplies citable web
evidence. Current-state claims need refreshed applicable results. Citation
validation establishes identity/visibility/provenance, not whether a claim follows
logically from a source. External content remains untrusted data.

## Automation and deployment

Existing scheduler tasks use the same runtime in dedicated execution sessions.
Execution remains read-only, retains its legitimate Project/endpoint binding and
does not copy ordinary conversation attachments. A job is not another AI agent.
See [Scheduler](architecture/SCHEDULER.md).

Orion server owns the control plane, persistence and tools. Model inference can
use the configured local or remote provider adapter. No particular model, GPU,
provider, domain or tunnel vendor is required by this product design. The
customer worker does not host inference.

## Completion boundary

Complete the [acceptance criteria](development/ACCEPTANCE_CRITERIA.md) for any
implementation change. Closing an old issue resets planning; it does not certify
a feature or delete existing source. This documentation redesign changes the
specification and reconciliation plan, not runtime behavior.
