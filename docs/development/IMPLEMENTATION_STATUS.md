# Implementation status — 2026-11-02

The current requirement is [REFACTOR_REQUEST.md](../../REFACTOR_REQUEST.md).
[STATE.json](../refactor/STATE.json) owns task status and dated evidence. Source
R00–R13 changes are prepared for the user-authorized commit/push from baseline
HEAD `3a51f3d`; no release is implied.

## Implemented and checked scope

R00–R13 are recorded Done at their documented implementation/fixture scope.
R12 adds hash-only native owner credentials, durable request admission/resume,
scoped resources and generated shared SDK; [R12 evidence](../refactor/evidence/R12_SESSION_2026-10-31.md)
records unchanged full1597pass/6Windows-host POSIX failures/17skip/23subtests and
final focused repair/static checks. [R13 evidence](../refactor/evidence/R13_SESSION_2026-11-01.md)
records static shared UI adoption, final115 UI tests, type/lint/packaged web checks
and actual desktop/mobile-browser/Stop fixtures. Full backend1600pass/6Windows-host
POSIX failures/17skip/23subtests is retained, with unchanged backend source after
the final UI guard repair. CLI and native platform bridges/artifacts remain their
separate dependent tasks.
Current full backend/source limitations are recorded in the dated evidence below.
A fixture pass does not establish live vendor or packaged/native acceptance.

| Area | Current source | Evidence and remaining work |
| --- | --- | --- |
| One runtime and canonical tools | [bootstrap](../../backend/src/orion/bootstrap/__init__.py), [runtime](../../backend/src/orion/chat/runtime.py), [registry](../../backend/src/orion/tool_runtime/registry.py) | First-turn schemas, scope, mutation modes, transient evidence and recovery have fixtures; broader runtime/client migration remains R12–R14. |
| Three providers | [provider adapters](../../backend/src/orion/models/providers/factory.py) | DeepSeek, Claude and OpenAI protocol/conformance fixtures are in R03–R06 evidence; real credentials/models remain R22–R24. |
| Projects/documents and managed data | [KnowledgeService](../../backend/src/orion/knowledge/service.py), [backup](../../backend/src/orion/persistence/backup.py) | R07 covers isolation, protected blobs, SQLite recovery/migration and managed DB/blob/provider-credential bundles; external SSH/MCP/tool configuration and OS keys are outside those bundles. |
| Paired-worker commands | [command service](../../backend/src/orion/application/commands.py), [worker runner](../../backend/src/orion_endpoint/commands.py) | Canonical run/status/cancel, owned handles, exact confirmation, no replay, output cursors and Windows Job lifecycle have source fixtures. R08 evidence distinguishes them from R25 packaged artifacts and R26 native Linux. |
| SSH commands | [configured SSH router](../../backend/src/orion/integrations/ssh/transport.py) | Actual private Ubuntu/QEMU SSH3/process10 passed, including detached double-fork cleanup and unknown proof handling. Artifact acceptance remains R26; legacy probes remain separate. |
| Skills | [implemented contract](../architecture/SKILLS.md) | Immutable package/catalog/SQLite lifecycle, request guidance/resources and offline CLI implemented;40 focused tests and actual isolated wheel/catalog verification. Current R11 full covers final bounds. |
| MCP | [manager](../../backend/src/orion/integrations/mcp/manager.py) | Explicit revision/schema snapshots, validated reconnect and owner lifecycle/doctor routes/CLI implemented with SDK auto/legacy and permission fixtures. R12–R14 add native auth/shared SDK/UI/headless client integration. |
| Scheduler | [engine](../../backend/src/orion/scheduler/engine.py) | Existing fixtures retain forced read_only; unattended arbitrary commands are not enabled. |
| Remote/UI clients | [API](../../backend/src/orion/api/app.py), [web route](../../ui/src/routes/index.tsx) | R12 native token/shared SDK and R13 static UI, server isolation, durable request observation/Stop, Commands and resource settings have source/web fixtures. Actual native host/vault/platform lifecycle remains R15–R17. |
| Dedicated monitoring adapters | [legacy registrations](../../backend/src/orion/tool_runtime/infrastructure.py) | Still active legacy source/config/test work to remove with the relevant source migration and R19 cleanup; documentation retirement does not disable them. |

## Current verification

[R07 repaired checks](../refactor/evidence/R07_DATA_REPAIRED_2026-10-30.json)
recorded 1400 backend passes, six Linux-host failures, seven skips and 23 subtests;
that run predates R08. R08 has its own
[session evidence](../refactor/evidence/R08_SESSION_2026-10-30.md),
[initial full checks](../refactor/evidence/R08_CHECKS_2026-10-30.json),
[repaired checks](../refactor/evidence/R08_REPAIRED_CHECKS_2026-10-30.json) and
[UI checks](../refactor/evidence/R08_UI_CHECKS_2026-10-30.json).
Read each result's source snapshot and scope; a failed or unfinished check is not
an acceptance pass. Linux installer tests cannot run under this Windows host's
missing POSIX shell. They remain failures rather than being skipped to report green.

[R11 current full](../refactor/evidence/R11_REPAIRED_CHECKS_2026-10-31.json) records
1564pass/6Linuxhostfail/17skip/23subtests and passing static checks. Product source
stayed unchanged; one Linux-only test's PID-disappearance race changed during that
Windows run and then passed the10-case actual Linux suite separately. POSIX
installer/release/credential source fixtures also ran on the guest, retaining
transfer-mode/tooling failures and repairs. None of these source runs replaces
the future exact artifact gates.

R19–R21 and native/live/signing gates remain open. No whole-refactor, live vendor,
packaged Linux/mobile, signed package or published artifact completion is claimed.
