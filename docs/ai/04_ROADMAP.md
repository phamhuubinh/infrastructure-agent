# 04 - Roadmap
> This is the sequencing plan from the current local architecture (`02_CURRENT_ARCHITECTURE.md`) to the target platform architecture (`03_PLATFORM_ARCHITECTURE.md`). It only starts once public VM access is available. Update `08_PROJECT_STATE.md` as each work package lands — this file describes intended order, not current status.
## WP1 — AI Platform running publicly on a VM
- AI Platform reachable over the public internet.
- HTTPS termination.
- Reverse proxy in front of API/Web UI.
- Docker Compose defining the running services.
- PostgreSQL provisioned as the platform database.
Exit criteria: Web UI reachable over HTTPS on the VM, backed by a Postgres instance, via Docker Compose. Local-only state (targets.json, in-memory pipeline state) is not required to be migrated yet at this stage — that begins as each subsequent WP touches that data.
## WP2 — Dify integration
- Dify integrated as the conversational/orchestration layer.
- Knowledge Base introduced.
- RAG wired to the Knowledge Base.
## WP3 — Document processing
- Document Service: upload, preview, download.
- Document history recorded in the Database (see `03_PLATFORM_ARCHITECTURE.md` for the schema areas this touches).
## WP4 — Infrastructure Agent on the platform
- This project's Agent (`02_CURRENT_ARCHITECTURE.md` pipeline) becomes a platform capability invoked via the API instead of a local CLI process.
- Internet Tool introduced — **only invoked when the user explicitly requests it**, never automatically. This is a hard rule, not a default-on convenience; see `07_DEVELOPMENT_RULES.md`.
## WP5 — Desktop App
- Desktop App (Tauri or Electron) shipped, using the same API, Database, and accounts as the Web UI.
- No feature or data divergence between Web UI and Desktop App — differences are presentation only.
## Sequencing notes
- Each WP assumes the previous one's exit criteria are met. Do not start WP4's platform-Agent migration before WP1's Database/API exist — there is nowhere to persist Agent history otherwise.
- WP4 is where the current local Agent (this repository, as described in `02_CURRENT_ARCHITECTURE.md`) actually moves onto the platform. Everything before WP4 is platform scaffolding that the Agent does not yet depend on.
- The Internet Tool rule in WP4 (opt-in per request) is a permanent constraint, not a temporary rollout precaution — do not relax it in a later WP without a corresponding entry in `09_ARCHITECTURE_DECISIONS.md`.
