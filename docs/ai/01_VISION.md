# 01 - Product Purpose and Scope

Orion is an evidence-driven infrastructure investigation application with a
separate project document-analysis workspace.

Its governing principle is:

> **Code investigates. AI explains.**

The configured Agent v2 boundary is: **Model owns reasoning and next-action
selection. Harness owns authority, execution, evidence and completion.** The
model interprets the supplied bounded request context and selects one
structured next decision. The harness sets hard constraints, controls the
available capabilities and target/source authority, validates every typed
action, executes reviewed implementations, and releases one checked response.
The model has no arbitrary command, shell, or HTTP authority.

## Current product surfaces

- An interactive CLI for chat, target management, and model connection
  management.
- A local Web application for isolated chat sessions, model settings, API-key
  settings, and project-scoped document analysis.
- A FastAPI API used by the Web UI and the Electron desktop wrapper.
- A Docker Compose installation containing Nginx, API, SSR UI, PostgreSQL, and
  the internal RAG service.
- An Electron wrapper that serves the packaged UI and connects to an already
  running local Docker installation.

## Current investigation domains

- Linux hosts through local execution or registered SSH targets.
- Grafana through its HTTP API.
- Zabbix through its API.
- Public Internet sources through bounded search and fetch with SSRF controls.

Stable general questions and content generation use the configured model
without infrastructure collection. Requests for current public information or
explicit URLs use deterministic external verification when the relevant
Internet provider is configured. Infrastructure mutations are refused.

## Document analysis

RAG is an explicit, project-scoped Web workflow. Each project owns its
documents, dense collection, BM25 index, and analysis history. Chat does not
register or call the RAG service. RAG analysis uses the active Orion model and
does not expose a retrieval-only answer mode.

## Deployment scope

The supported runtime is local and single-operator. Source mode stores sessions
in SQLite. Docker Compose stores sessions in PostgreSQL and exposes the
application on loopback HTTP through Nginx. API-key authentication protects one
tenant; it is not an account or authorization system.
