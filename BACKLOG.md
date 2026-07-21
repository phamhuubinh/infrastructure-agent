# Orion — Backlog

> Consolidated backlog derived from `.workflow/state.json`.
> Tasks are grouped by Epic, sorted by ID, then by Phase.

Last updated: 2026-07-21

---

## Legend

| Column      | Meaning                                           |
|-------------|---------------------------------------------------|
| ID          | Unique task identifier                            |
| Priority    | P0=Critical, P1=High, P2=Medium, P3=Low          |
| Status      | `✅ completed` / `🔄 in_progress` / `⬜ pending` |
| Title       | Short task name                                   |
| Description | Brief description of the task                     |

**Phases:**
- **Phase 0**: Diagnosis & Preparation
- **Phase 1**: Foundation (P0/P1 — priority)
- **Phase 2**: Quality & Technical Debt (P2 — medium)
- **Phase 3**: Polish & Governance (P3 — low)

---

## Phase 0 — Diagnosis & Preparation

### Code Quality

| ID | Priority | Status | Title                                      | Description                                             |
|----|----------|--------|--------------------------------------------|---------------------------------------------------------|
| 0  | P0       | ✅     | Fix all ruff lint errors across codebase    | Resolve all ruff lint violations across the entire codebase |

---

## Phase 1 — Foundation (P0–P1)

### Core Architecture

| ID | Priority | Status | Title                                          | Description                                                       |
|----|----------|--------|------------------------------------------------|-------------------------------------------------------------------|
| 1  | P0       | ✅     | Make ConversationStore Thread Safe             | Add threading.Lock to shared mutable state                        |
| 3  | P0       | ✅     | Fix Execution Runtime Set Comparison           | Replace `==` with `issubset()` for set comparison                 |
| 4a | P0       | ✅     | Fix Thread Safety in ExecutionRuntime shared   | Protect shared state accessed from ThreadPoolExecutor callbacks   |
| 4b | P1       | ✅     | Make Execution Runtime Thread Safe             | Audit and lock shared mutable state in ThreadPoolExecutor         |
| 5  | P1       | ✅     | Refactor execute()                             | Split large execute() into smaller phases                         |
| 6  | P1       | ✅     | Refactor create_app()                          | Split responsibility-heavy create_app()                           |
| 7  | P1       | ✅     | Optimize Evidence Serialization                | Truncate large evidence payloads to frontend                      |

### Security

| ID | Priority | Status | Title                                      | Description                                             |
|----|----------|--------|--------------------------------------------|---------------------------------------------------------|
| 16 | P0       | ✅     | Move Docker Secrets Out of Repository       | Remove plaintext secrets from repo                      |
| 17 | P0       | ✅     | Add API Authentication (Platform)           | API Key middleware for production                       |
| 18 | P1       | 🔄     | Make SSH Host Key Checking Configurable     | Configurable StrictHostKeyChecking                      |
| 19 | P1       | 🔄     | Prevent SSRF                                | Block localhost, private IP, loopback in InternetTool   |

### DevOps & CI/CD

| ID | Priority | Status | Title                              | Description                                                    |
|----|----------|--------|------------------------------------|----------------------------------------------------------------|
| 33 | P0       | ✅     | Fix Docker Build Dependencies       | Ensure Docker builds succeed from clean repo                   |
| 34 | P1       | ✅     | Build Docker Images In CI           | Build API and UI images in CI pipeline                         |
| 35 | P1       | ✅     | Start Containers During CI          | docker compose up, smoke test, tear down                       |
| 36 | P1       | ✅     | Add Health Endpoint                 | GET /health with dependency checks                             |
| 37 | P1       | ✅     | Add Docker Health Checks            | Health checks for API, Redis, RAG services                     |
| 38 | P1       | ✅     | Publish Coverage Report             | pytest --cov with XML/HTML artifacts                           |
| 39 | P1       | ✅     | Add Security Scan                   | Bandit, Safety, pip audit in CI                                |

### Testing & Quality Assurance

| ID | Priority | Status | Title                                      | Description                                             |
|----|----------|--------|--------------------------------------------|---------------------------------------------------------|
| 51 | P1       | ✅     | Increase Backend API Test Coverage          | Integration tests for all endpoints                     |
| 54 | P1       | ✅     | Regression Tests For Runtime Bugs           | Set comparison, capability resolver, evidence merge     |
| 55 | P1       | ✅     | Thread Safety Tests                         | Multi-thread ConversationStore, Runtime, Tool execution |

### Documentation & Project Governance

| ID | Priority | Status | Title                                      | Description                                             |
|----|----------|--------|--------------------------------------------|---------------------------------------------------------|
| 69 | P0       | ✅     | Create ADR-0002                            | LLM-only for Assessment Layer                           |
| 70 | P0       | ✅     | Create ADR-0003                            | KnowledgeTool as single entry point                     |
| 71 | P1       | ✅     | Synchronize Architecture Decisions         | Cross-reference, fix links, standardize numbering       |
| 72 | P1       | ✅     | Standardize Backlog Format                  | Rewrite BACKLOG.md with standardized format             |
| 73 | P1       | ⬜     | Release CHANGELOG v0.1.0                   | Keep a Changelog format                                 |

---

## Phase 2 — Quality & Technical Debt (P2)

### Core Architecture

| ID | Priority | Status | Title                                        | Description                                                     |
|----|----------|--------|----------------------------------------------|-----------------------------------------------------------------|
| 8  | P2       | ⬜     | Improve Safe Data Serialization              | Handle nested and non-serializable objects                      |
| 9  | P2       | ⬜     | Add EvidencePlanner Fallback                 | Fallback when intent has no template                            |
| 10 | P2       | ⬜     | Make Conversation Summary Threshold Configurable | Replace hardcoded value with config                          |
| 11 | P2       | ⬜     | Make Frontend Port Configurable              | Replace hardcoded port 5173 with env var                        |
| 12 | P2       | ⬜     | Remove Dead Code                             | Delete unused wrappers, helpers, duplicates                     |
| 13 | P3       | ⬜     | Standardize Naming Convention                | Normalize `_get_*`, `_read_*`, `_load_*` prefixes               |
| 14 | P2       | ⬜     | Cache Repeated /proc Reads                   | Reduce I/O overhead with caching                                |
| 15 | P2       | ⬜     | Hide Internal Error Details                  | Return generic errors, log full details server-side             |

### Security

| ID | Priority | Status | Title                                      | Description                                             |
|----|----------|--------|--------------------------------------------|---------------------------------------------------------|
| 20 | P2       | ⬜     | Sanitize Error Messages                    | No stacktrace/internal paths in client responses        |
| 21 | P2       | ⬜     | Validate Uploaded Files                    | Extension, size, filename validation                    |
| 22 | P2       | ⬜     | Prevent Path Traversal                     | Resolve paths, reject escapes                           |
| 23 | P2       | ⬜     | Mask Sensitive Information in Logs         | Mask passwords, tokens, API keys                        |
| 24 | P2       | ⬜     | Remove Global Mutable Secret State         | Read tokens from config, not globals                    |
| 25 | P2       | ⬜     | Add Rate Limiting (Platform)               | Rate limiting middleware                                 |
| 26 | P2       | ⬜     | Limit Upload Size                          | MAX_UPLOAD_SIZE config                                  |
| 27 | P2       | ⬜     | Restrict Local File Access                 | Only allow reading within document root                 |
| 28 | P2       | ⬜     | Hide Database Credentials                  | Mask credentials in logs                                |
| 29 | P2       | ⬜     | Validate Session ID                        | Format, length, character validation                    |
| 30 | P3       | ⬜     | Make Secret Path Configurable              | ORION_SECRETS_PATH env var                              |
| 31 | P3       | ⬜     | Improve Database Connection Security       | Connection pool, SSL support                            |
| 32 | P2       | ⬜     | Security Regression Tests                  | Ensure security fixes remain intact                     |

### DevOps & CI/CD

| ID | Priority | Status | Title                              | Description                                                    |
|----|----------|--------|------------------------------------|----------------------------------------------------------------|
| 40 | P2       | ⬜     | Configure Dependabot               | Automated dependency updates                                    |
| 41 | P2       | ⬜     | Graceful Shutdown                  | Handle SIGTERM/SIGINT, clean shutdown                           |
| 42 | P2       | ⬜     | Add UI Test Stage                  | npm ci, npm test in CI                                         |
| 43 | P2       | ⬜     | Improve Logging                    | Structured logging, request IDs                                 |
| 44 | P2       | ⬜     | Improve Monitoring                 | Metrics endpoint, Prometheus, Grafana                           |
| 45 | P3       | ⬜     | Resource Limits (Platform)         | CPU/memory limits for containers                                |
| 46 | P3       | ⬜     | Deployment Pipeline (Platform)     | Build, push, deploy, rollback                                   |
| 47 | P3       | ⬜     | Release Automation                 | Tag, changelog, artifacts, release notes                        |
| 48 | P3       | ⬜     | CI Performance Optimization        | Cache, parallelize, faster workflow                             |
| 49 | P3       | ⬜     | Standardize Development Environment | Bootstrap, venv, deps, startup                                 |
| 50 | P3       | ⬜     | DevOps Documentation               | CI, Docker, setup, release docs                                 |

### Testing & Quality Assurance

| ID | Priority | Status | Title                                      | Description                                             |
|----|----------|--------|--------------------------------------------|---------------------------------------------------------|
| 52 | P2       | ⬜     | Create Shared Pytest Fixtures              | Centralize fixtures in conftest.py                      |
| 53 | P2       | ⬜     | Convert Benchmark To Dataset               | JSON dataset, pytest parametrize                        |
| 56 | P2       | ⬜     | Serialization Tests                        | Nested dicts, custom objects, circular refs             |
| 57 | P2       | ⬜     | Upload Validation Tests                    | Invalid extension, large files, path traversal          |
| 58 | P2       | ⬜     | Internet Tool Tests                        | Invalid URLs, timeouts, DNS failures                    |
| 59 | P2       | ⬜     | Knowledge Tool Tests                       | Capability lookup, evidence mapping                     |
| 60 | P2       | ⬜     | Capability Library Tests                   | Registry validation, serialization                      |
| 61 | P3       | ⬜     | Improve Benchmark Reports                  | Aggregate, display scores, pass rates                   |
| 62 | P2       | ⬜     | Performance Benchmarks                     | Startup, latency, tool exec, memory, CPU                |
| 63 | P2       | ⬜     | Memory Leak Tests                          | Long sessions, repeated execution                       |
| 64 | P2       | ⬜     | Load Tests                                 | 10/50 concurrent users, burst requests                  |
| 65 | P2       | ⬜     | Test Coverage Improvement                  | Target coverage, CI reporting                           |
| 66 | P3       | ⬜     | Remove Duplicate Tests                     | Find, merge, standardize                                |
| 67 | P3       | ⬜     | Improve Test Documentation                 | Guidelines for writing tests                            |
| 68 | P3       | ⬜     | Continuous Quality Monitoring              | Track benchmark, coverage, performance over time        |

### Documentation & Project Governance

| ID | Priority | Status | Title                                      | Description                                             |
|----|----------|--------|--------------------------------------------|---------------------------------------------------------|
| 74 | P2       | ⬜     | Expand CONTRIBUTING.md                     | Branch strategy, commit conventions, PR workflow        |
| 75 | P2       | ⬜     | Improve SECURITY.md                        | Disclosure policy, contact, SLA                         |
| 76 | P2       | ⬜     | Create Security Issue Template             | Security, vulnerability, bug, feature templates         |
| 77 | P2       | ⬜     | Add Last Updated Metadata                  | Timestamps on all key docs                              |
| 78 | P2       | ⬜     | Consolidate Benchmark Reports              | Single structured format                                |
| 79 | P2       | ⬜     | Standardize Documentation Structure        | Headings, numbering, tables, terminology                |
| 80 | P2       | ⬜     | Improve Project Bootstrap Guide            | Local/Docker setup, troubleshooting                     |
| 81 | P2       | ⬜     | Update Development Rules                   | Coding conventions, review checklist                    |
| 82 | P2       | ⬜     | Update Project State                       | Sync status, roadmap, completed work                    |
| 83 | P3       | ⬜     | Improve Tool Documentation                 | Linux, Zabbix, Grafana, Internet, Knowledge tools      |
| 84 | P3       | ⬜     | Improve API Documentation                  | Endpoint descriptions, examples, error codes            |
| 85 | P3       | ⬜     | Improve Architecture Diagrams              | Pipeline, runtime, tool, component, sequence diagrams   |
| 86 | P3       | ⬜     | Documentation Consistency Review           | Terminology, duplicates, broken links                   |

---

## Phase 3 — Polish & Governance (P3)

### Code Quality, Refactoring & Technical Debt

| ID  | Priority | Status | Title                                      | Description                                                    |
|-----|----------|--------|--------------------------------------------|----------------------------------------------------------------|
| 87  | P1       | ⬜     | Replace Broad Exception Handling           | Replace `except Exception:` with specific exceptions           |
| 88  | P1       | ⬜     | Introduce Database Connection Pool         | Reuse connections instead of creating per request               |
| 89  | P1       | ⬜     | Remove Duplicate Tool Execution Logic      | Share execute implementation across tools                      |
| 90  | P1       | ⬜     | Standardize Tool Interface                 | Normalize input, output, error, metadata                       |
| 91  | P2       | ⬜     | Remove Hardcoded Configuration             | Extract timeouts, retries, ports to config                     |
| 92  | P2       | ⬜     | Standardize Configuration System           | Single source, no duplicates                                   |
| 93  | P2       | ⬜     | Improve Logging Consistency                | Standardize logger init, levels, format                        |
| 94  | P2       | ⬜     | Improve Error Handling Strategy            | Exception hierarchy, error codes, API errors                   |
| 95  | P2       | ⬜     | Improve Runtime Performance                | Profile, cache, re-benchmark                                   |
| 96  | P2       | ⬜     | Refactor Capability Resolution Flow        | Simplify logic, remove duplicate lookups                       |
| 97  | P2       | ⬜     | Standardize Response Models                | Consistent schemas, serialization, typing                      |
| 98  | P2       | ⬜     | Improve Type Hints                         | TypedDict, Protocol, Generic, return types                     |
| 99  | P2       | ⬜     | Remove Legacy Compatibility Code           | Compatibility layers, unused imports                           |
| 100 | P2       | ⬜     | Standardize Project Structure              | Folder structure, package organization                         |
| 101 | P3       | ⬜     | Review Technical Debt                      | Catalog TODO, FIXME, XXX comments                              |
| 102 | P3       | ⬜     | Remove Duplicate Utility Functions         | Consolidate into common module                                 |
| 103 | P3       | ⬜     | Standardize Project Coding Style           | Naming, imports, formatting, docstrings                        |
| 104 | P3       | ⬜     | Final Architecture Cleanup                 | Dependency review, dead code, pre-release                      |

---

## Summary

| Phase | Epic                                          | Total | ✅ Done | 🔄 In Progress | ⬜ Pending |
|-------|-----------------------------------------------|-------|--------|----------------|------------|
| 0     | Code Quality                                  | 1     | 1      | 0              | 0          |
| 1     | Core Architecture                             | 7     | 7      | 0              | 0          |
| 1     | Security                                      | 4     | 2      | 2              | 0          |
| 1     | DevOps & CI/CD                                | 7     | 7      | 0              | 0          |
| 1     | Testing & Quality Assurance                   | 3     | 3      | 0              | 0          |
| 1     | Documentation & Project Governance            | 5     | 4      | 0              | 1          |
| 2     | Core Architecture                             | 8     | 0      | 0              | 8          |
| 2     | Security                                      | 13    | 0      | 0              | 13         |
| 2     | DevOps & CI/CD                                | 11    | 0      | 0              | 11         |
| 2     | Testing & Quality Assurance                   | 15    | 0      | 0              | 15         |
| 2     | Documentation & Project Governance            | 13    | 0      | 0              | 13         |
| 3     | Code Quality, Refactoring & Technical Debt    | 18    | 0      | 0              | 18         |
|       | **Total**                                     | **105** | **24** | **2**        | **79**     |

---

*Source: `.workflow/state.json` — this file is auto-generated for human readability.*
