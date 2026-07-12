# 03 - Platform Architecture (Target, Future)
> Status: **not implemented**. This document describes where the system is going, not what exists. Check `08_PROJECT_STATE.md` before assuming any part of this is live.
## Trigger
This direction only applies once public VM access is available. Until then, the project stays on the local architecture described in `02_CURRENT_ARCHITECTURE.md`.
## Target shape
```
Internet
    │
   HTTPS
    │
    ▼
AI Platform (VM)
│
├── Web UI
├── API
├── Auth
├── Agent              ← this project's investigation pipeline (02_CURRENT_ARCHITECTURE.md),
│                          becomes one capability inside the platform, not the whole product
├── Dify
├── RAG
├── Document Service
└── Database
```
```
AI Platform
        ▲
        │ HTTPS
        ▼
Desktop App
```
## Components
**Web UI** — the browser client. Talks only to the API, never directly to the database or to individual services.
**API** — single entry point for both Web UI and Desktop App. Owns request auth, routing to Agent/Dify/RAG/Document Service, and persistence via the Database.
**Auth** — accounts, sessions/tokens. Every user, conversation, and job is scoped to an authenticated account. This is what makes "same data on every device" possible.
**Agent** — this project. The deterministic investigation pipeline (`05_EXECUTION_PIPELINE.md`) runs as a platform capability invoked through the API, not as a standalone local process. Its internal design (Code investigates, AI explains; Child Tools behind KnowledgeTool) does not change — only how it is invoked and where its output is stored changes.
**Dify** — chat/orchestration layer for general conversational use cases, separate from the deterministic Agent.
**RAG** — retrieval over a knowledge base, backing both Dify conversations and Agent assessments where relevant.
**Document Service** — upload, storage, preview, and download of files. Feeds RAG/Knowledge Base metadata into the Database.
**Database (PostgreSQL)** — the single source of truth for state that used to live only on a local disk:
- Users
- Conversations
- Uploaded files
- Document history
- Knowledge Base metadata
- Agent history
- Job queue
Nothing important is allowed to live only on one local machine once this is in place. A user should be able to start a task on one device and pick it up on another with nothing lost.
## Desktop App
A Tauri or Electron app, planned for WP5. It is a second client, not a second backend: same API, same database, same account as the Web UI. The only difference between Desktop App and Web UI is presentation. Example flow this must support: upload a document on the desktop app at work, open the web UI at home later, the file, the chat, and any still-running agent job are all present, unchanged.
## Infrastructure
- Reverse proxy in front of the API/Web UI, terminating HTTPS.
- Docker Compose to run the platform's services (API, Web UI, Database, and later Dify/RAG/Document Service) on the VM.
- PostgreSQL as the platform database.
## Non-goals for this document
This document intentionally does not cover Kubernetes, multi-VM scaling, or high availability. Those are out of scope until the single-VM Docker Compose setup (WP1) is running and stable. Do not over-design for scale that has no corresponding roadmap item yet — see `07_DEVELOPMENT_RULES.md` on avoiding unnecessary complexity.
## Relationship to the Agent's own rules
Becoming a platform capability does not relax the Agent's core rule that Internet access, when the Internet Tool exists (`04_ROADMAP.md`, WP4), is opt-in per request — never automatic, regardless of which client (Web UI or Desktop App) initiated the request.
