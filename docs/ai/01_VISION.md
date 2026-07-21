# 01 - Vision
## What this is today
An **Infrastructure Investigation Agent**: a local, single-user tool that investigates infrastructure (via SSH, Grafana, Zabbix, Internet fetch, RAG) deterministically, collects evidence, and uses an LLM only to interpret that evidence and produce an assessment. It runs on one machine, has no accounts, with optional PostgreSQL persistence and optional API key auth, and no network exposure beyond outbound calls to targets/Grafana/Zabbix/LLM/Internet APIs.
Core principle (unchanged by anything below):
> **Code investigates. AI explains.**
Investigation steps (what evidence to collect, from where, how) are deterministic and written in code. The LLM is only used at the assessment step, to read the evidence already collected and explain what it means. This principle applies regardless of whether the project stays local or becomes a hosted platform — it is not up for revision by infrastructure changes.
## Where this is going
If public VM access is available, the long-term goal changes from "a local CLI/web tool" to **a shared AI Platform**: one backend, reachable over the internet, used from multiple devices (work PC, laptop, phone) with the same account, same conversations, same files, same agent history — everywhere.
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
├── Agent            (this project's investigation pipeline)
├── Dify
├── RAG
├── Document Service
└── Database
```
Key shift: **stop storing state on the local machine.** Users, conversations, uploaded files, document history, knowledge base metadata, agent history, and job queues all move to a central database (PostgreSQL). A user can start something on one device and continue it on another because nothing important lives only on disk on one machine.
A **Desktop App** (Tauri or Electron) is planned alongside the Web UI. Both talk to the same API, same database, same account — the only difference between them is presentation, not data or capability. Upload a file on the desktop app at work, open the web UI at home, the file, the chat, and the running agent job are all still there.
See `03_PLATFORM_ARCHITECTURE.md` for the target architecture in detail and `04_ROADMAP.md` for how the work is sequenced.
## What does not change
- Evidence-driven, deterministic-first investigation (`Code investigates. AI explains.`) stays the design center of the Agent component regardless of what platform it runs inside.
- The Agent's tools (SSH execution, Grafana, Zabbix, Internet fetch, RAG service) keep their current design contract (see `06_TOOL_AND_CAPABILITY_DESIGN.md`) — becoming a platform component does not change how a tool declares its capability.
- Internet access from the Agent is opt-in per request, never automatic (see `04_ROADMAP.md`). This is enforced by the pipeline — `InternetTool` is only invoked when the user explicitly requests it.
## What explicitly changes later, not now
- Local file-based state (targets.json, local config) → PostgreSQL-backed state, multi-user.
- Single local process → API server + separate clients (Web UI, Desktop App).
- No accounts → Auth.
- Agent-only → Agent as one integrated capability inside a platform that also does chat (Dify), knowledge base/RAG, and document handling.
Some of these (PostgreSQL session store, API key auth) are partially implemented. Check `08_PROJECT_STATE.md` before building against any of them.
