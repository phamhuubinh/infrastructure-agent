# Testing

## Testing pyramid

### Unit

Test:

- context assembly;
- deterministic model-input byte proxies for initial, resumed, and long-history turns;
- bounded model-visible ToolResult projection while canonical persistence stays complete;
- aggregate current-turn budgeting across many tool calls;
- complete historical user-turn boundaries, including an oversized tool turn;
- tool-call/result pairing, duplicate-ID rejection, collection counts, and exact
  `SourceRef` preservation under projection;
- registry/provider schema cache mutation isolation;
- tool registry;
- tool schema conversion;
- provider adapters;
- ToolResult normalization;
- project source scoping;
- document parsers/chunking/retrieval components;
- persistence.

### Contract

Verify each registered tool can be serialized to every supported provider adapter and dispatched back to the correct handler.

### Runtime vertical slices

Use fake model + fake tools:

```text
direct chat → final
chat → one tool → final
chat → several tools → final
project → project RAG → final
project → RAG + calculator → final
tool failure → model explains/uses fallback
```

### RAG

Test:

- session-source isolation;
- project-source isolation;
- exact document read;
- semantic search;
- cross-document comparison fixtures;
- deletion/reindex recovery;
- citation metadata.

### Live model

Run narrow live probes only after deterministic runtime tests pass.

Live tests should prove the configured model can naturally use model-facing tool schemas without special keyword routing.

## Current commands

```bash
make test
make lint
```

Backend:

```bash
make test-backend
```

Frontend:

```bash
make test-frontend
```

For manual testing from an editable checkout, start or restart `orion web` after changing
frontend source. Startup builds and replaces the packaged `.orion-ui` automatically; do not
copy `ui/dist/client` by hand. Installed runtime uses the bundle prepared by `install.sh`.

## Required CI checks

The main-branch delivery policy requires the existing `backend`, `ui`, and
`acceptance-extra` GitHub Actions checks. See
[Branch protection](../operations/BRANCH_PROTECTION.md) for the settings payload,
PR requirements, admin behavior, and API verification. These offline checks do not
establish live model stability or answer quality.

## Native Windows installer gate

The **Windows CI / windows-smoke** job runs on `windows-latest` for PRs and
pushes to `main` affecting backend, UI, installers, smoke helpers, or the relevant
workflows. It can also be dispatched manually. It does not rerun Linux unit suites
or change the existing branch-protection requirements.

The job parses the source/release installers with Windows PowerShell, then exercises
the source installer with real Python 3.12 discovery, venv creation/reuse, `npm.cmd`
UI builds, and installation/data paths containing spaces. The source checkout also
lives in a path containing spaces. It builds a wheel and archives with the
existing release payload builder, verifies the Windows archive checksum, extracts
it outside the checkout, and runs the same installer/runtime probes on that bundle.
The **Release bundles / smoke-windows** job uses the same probes.

Before installing dependencies, both Windows jobs execute the actual launcher
filesystem statements from both installers in isolation. This deterministic test
covers first creation, unchanged rerun, replacement with a different managed target,
and refusal of unrelated, empty, and incorrectly cased ownership markers. It checks
temporary-file cleanup and never changes user PATH. Managed launchers use
`File.Replace` with a same-directory staged file; first creation uses `File.Move`.
PowerShell's `[NullString]::Value` supplies the null backup filename required by
`File.Replace` rather than an empty string.

Both installers are run twice successfully, then with a deterministic model
provisioning failure and an unrelated launcher. Checks cover the managed
`%LOCALAPPDATA%\Orion\bin\orion.cmd`, launcher `help`, current-process PATH,
case/quote/environment-variable/trailing-slash user PATH deduplication, retention
of unrelated PATH entries, and failure before publishing a launcher. A snapshot
of the original user PATH registry value and type is restored in `finally`, even
when the installer exits its PowerShell process. Installation/data/launcher paths
are temporary; no preexisting Orion state is required.

A temporary `sitecustomize.py` replaces the model provisioning function only for
`orion model install embeddings`, records each invocation, and deterministically
succeeds or fails. It blocks that process's model download boundary before import,
and aborts on import failure. No E5 files are downloaded. Python dependencies and
source UI dependencies are installed normally; this is not a fully offline gate.

The runtime probe checks Remote Access configuration parsing with a disposable
password hash, verifies the actual listener is only `127.0.0.1`, and fetches
`/api/health`, the packaged HTML, and a JavaScript asset without a login cookie.
Browser opening is suppressed. Release smoke forbids invoking source build tools.

To run on a native Windows machine with Python 3.12 and Node.js 22.12+:

```powershell
.\scripts\windows\installer-check.ps1 -ParseOnly
.\scripts\windows\test-launcher.ps1
python scripts/windows/installer_smoke.py "$PWD"
python scripts/release/smoke.py 'C:\Extracted Release With Spaces\orion-<version>-windows-x64' windows-x64
```

Linux/static checks do not establish Windows acceptance. Issue #159 requires a
successful native GitHub Actions run of these scenarios before it can be closed.
