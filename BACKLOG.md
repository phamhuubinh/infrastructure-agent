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
| Status      | `✅ completed` / `🔄 in_progress` / `⬜ pending` / `🔴 blocked` |
| Title       | Short task name                                   |
| Description | Brief description of the task                     |

**Phases:**
- **Phase 0**: Diagnosis & Preparation
- **Phase 1**: Foundation (P0–P1)
- **Phase 2**: Quality & Technical Debt (P2)
- **Phase 3**: Polish & Governance (P3)

---

## Phase 0 — Diagnosis & Preparation

### Code Quality

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 0   | P0       | ✅      | Fix all ruff lint errors across codebase     | Fix all 132 ruff lint errors (E, F, I, UP, B rules) across the entire codebase using ruff check --fix and manual fixes where needed. |

---

## Phase 1 — Foundation (P0–P1)

### Core Architecture

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 1   | P0       | ✅      | Make ConversationStore Thread Safe           | ConversationStore sử dụng shared mutable state (`_mem`, `_dirty`, `_summary`) nhưng chưa có cơ chế đồng bộ khi nhiều request chạy đồng thời. |
| 3   | P0       | ✅      | Fix Execution Runtime Set Comparison         | Trong execution_runtime.py, hàm so sánh kết quả execution với expected đang dùng toán tử `==` để so sánh set. Cần thay bằng `set1 <= set2` hoặc `set1.issubset(set2)` vì thứ tự phần tử không quan trọng. Sau khi sửa, chạy pytest và benchmark để verify. |
| 4a  | P1       | 🔄      | Make Execution Runtime Thread Safe           | Shared state trong ThreadPoolExecutor chưa đảm bảo thread-safe. |
| 4b  | P0       | ✅      | Fix Thread Safety in ExecutionRuntime shared state | ExecutionRuntime uses shared mutable state (completed, collected_evidence) accessed from ThreadPoolExecutor callbacks without synchronization. |
| 5   | P1       | 🔄      | Refactor execute()                           | `execute()` quá lớn, khó bảo trì. |
| 6   | P1       | 🔄      | Refactor create_app()                        | `create_app()` đang đảm nhận quá nhiều trách nhiệm. |
| 7   | P1       | 🔄      | Optimize Evidence Serialization              | Không serialize toàn bộ evidence lớn lên frontend. |

### Security

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 16  | P0       | ✅      | Move Docker Secrets Out of Repository        | Không lưu plaintext secret trong repository. |
| 17  | P0       | 🔄      | Add API Authentication (Platform)            | Chuẩn bị API authentication cho production. |
| 18  | P1       | 🔄      | Make SSH Host Key Checking Configurable      | Cho phép bật/tắt StrictHostKeyChecking bằng cấu hình. |
| 19  | P1       | 🔄      | Prevent SSRF                                 | Ngăn InternetTool truy cập private network. |

### DevOps & CI/CD

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 33  | P0       | 🔄      | Fix Docker Build Dependencies                | Đảm bảo Docker image luôn build thành công, không phụ thuộc cấu hình local. |
| 34  | P1       | ✅      | Build Docker Images In CI                    | CI phải build được toàn bộ Docker image. |
| 35  | P1       | ✅      | Start Containers During CI                   | Start Docker containers during CI to verify they run correctly. Implement docker compose up in CI pipeline, wait for all services to be ready, run smoke tests to verify functionality, then tear down containers with docker compose down. |
| 36  | P1       | ✅      | Add Health Endpoint                          | Thêm endpoint kiểm tra trạng thái service. |
| 37  | P1       | ✅      | Add Docker Health Checks                     | Add Docker health checks to container definitions for proper orchestration. Implement health checks for the API service, Redis, and RAG service, and configure compose depends_on with health conditions. |
| 38  | P1       | ✅      | Publish Coverage Report                      | Publish coverage reports from CI to track test coverage. Run pytest with --cov to generate XML and HTML coverage reports, and upload them as CI artifacts for review. |
| 39  | P1       | ✅      | Add Security Scan                            | Add security scanning to CI pipeline. Integrate Bandit for static analysis, Safety for dependency vulnerability scanning, pip audit for package vulnerabilities, and fail the CI build if critical issues are found. |

### Testing & Quality Assurance

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 51  | P1       | ✅      | Increase Backend API Test Coverage           | Backend API hiện có ít integration test, chưa bao phủ đầy đủ endpoint mới. |
| 54  | P1       | ✅      | Regression Tests For Runtime Bugs            | Create regression tests for previously fixed runtime bugs. Add tests for set comparison in execution_runtime, capability resolver behavior, evidence merging logic, and execution graph processing to prevent regressions. |
| 55  | P1       | ⬜      | Thread Safety Tests                          | Create thread safety tests for concurrent components. Test multi-threaded access to ConversationStore, Execution Runtime, and Tool execution, and verify deterministic output under concurrent load. |

### Documentation & Project Governance

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 69  | P0       | 🔄      | Create ADR-0002                              | Tạo ADR mô tả quyết định chỉ sử dụng LLM cho Assessment Layer. |
| 70  | P0       | 🔄      | Create ADR-0003                              | Tạo ADR mô tả KnowledgeTool là entry point duy nhất. |
| 71  | P1       | ⬜      | Synchronize Architecture Decisions           | Synchronize all architecture decision records (ADRs) to ensure consistency. Check all ADR references across documentation, update cross-references between ADRs, fix broken links, and standardize ADR numbering. |
| 72  | P1       | ⬜      | Rewrite BACKLOG.md                           | Chuẩn hóa backlog theo format thống nhất. |
| 73  | P1       | ⬜      | Release CHANGELOG v0.1.0                     | Create the initial CHANGELOG for release v0.1.0. Move items from Unreleased section to the first release, follow Keep a Changelog format, and synchronize version numbers across the project. |

### Code Quality, Refactoring & Technical Debt

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 87  | P1       | ⬜      | Replace Broad Exception Handling             | Giảm việc sử dụng `except Exception:` để tránh che giấu lỗi. |
| 88  | P1       | ⬜      | Introduce Database Connection Pool           | Không tạo connection mới cho mỗi request. |
| 89  | P1       | ⬜      | Remove Duplicate Tool Execution Logic        | Các Tool đang có nhiều đoạn execute giống nhau. |
| 90  | P1       | ⬜      | Standardize Tool Interface                   | Standardize the Tool interface across all tool implementations. Normalize input parameters, output formats, error handling patterns, and metadata structure for consistent tool behavior. |

---

## Phase 2 — Quality & Technical Debt (P2)

### Core Architecture

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 8   | P2       | ⬜      | Improve Safe Data Serialization              | `_safe_data()` chưa xử lý tốt dữ liệu lồng nhau. |
| 9   | P2       | ⬜      | Add EvidencePlanner Fallback                 | Intent không có template sẽ không thu thập evidence. |
| 10  | P2       | ⬜      | Make Conversation Summary Threshold Configurable | Make the conversation summary threshold configurable instead of being hardcoded. Replace the current hardcoded value of 4 turns with a configurable setting, read from configuration (default 6-8 turns), and add tests to verify the configuration is respected. |
| 11  | P2       | ⬜      | Make Frontend Port Configurable              | Make the frontend port configurable instead of being hardcoded. Remove the hardcoded port 5173, read the port from environment variable, implement fallback logic if the port is busy, and ensure the application starts correctly on the configured port. |
| 12  | P2       | ⬜      | Remove Dead Code                             | Remove all dead code from the codebase to improve maintainability. Identify and delete unused wrappers, redundant helpers, obsolete code, and duplicate utility functions across the project. Ensure no functionality is broken after removal. |
| 14  | P2       | ⬜      | Cache Repeated /proc Reads                   | Cache repeated reads from the /proc filesystem to reduce I/O overhead. Avoid reading /proc multiple times within the same request by implementing a caching layer, and add benchmarks to verify performance improvement. |
| 15  | P2       | ⬜      | Hide Internal Error Details                  | Hide internal error details from API responses to prevent information leakage. Stop returning implementation details, available source information, and internal paths in error responses. Log the full error details server-side while returning only generic error messages to clients. Standardize the error response format. |

### Security

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 20  | P2       | ⬜      | Sanitize Error Messages                      | Sanitize error messages to prevent leaking sensitive information. Ensure stacktraces, internal paths, and available source information are not returned to clients. Standardize error response format across all endpoints. |
| 21  | P2       | ⬜      | Validate Uploaded Files                      | Validate uploaded files to prevent security vulnerabilities. Implement restrictions on file extensions, enforce file size limits, validate filenames for malicious patterns, reject path traversal attempts, and add unit tests for all validation logic. |
| 22  | P2       | ⬜      | Prevent Path Traversal                       | Prevent path traversal attacks in file operations. Resolve all paths to absolute paths, verify they remain within the allowed directory, reject symbolic link escapes, and add regression tests to ensure protection is maintained. |
| 23  | P2       | ⬜      | Mask Sensitive Information in Logs           | Mask sensitive information in log output to prevent credential leakage. Implement masking for passwords, tokens, API keys, DSN strings, and Authorization headers before they are written to logs. |
| 24  | P2       | ⬜      | Remove Global Mutable Secret State           | Không lưu token trong global mutable variable. |
| 25  | P2       | ⬜      | Add Rate Limiting (Platform)                 | Add rate limiting middleware for the platform deployment. Configure requests per minute limits, implement different rate limits per endpoint, log rejected requests for monitoring, and document the rate limiting configuration. |
| 26  | P2       | ⬜      | Limit Upload Size                            | Limit upload size to prevent resource exhaustion. Implement a MAX_UPLOAD_SIZE configuration, return HTTP 413 (Payload Too Large) when the limit is exceeded, and document the upload size limit. |
| 27  | P2       | ⬜      | Restrict Local File Access                   | Restrict local file access to only allow reading files within a designated document root directory. Resolve paths to absolute form, reject any path that attempts to escape the document root, and add tests to verify the restriction. |
| 28  | P2       | ⬜      | Hide Database Credentials                    | Hide database credentials in logs to prevent credential leakage. Do not log full DSN strings, mask username and password portions, only log host and database name for debugging purposes. |
| 29  | P2       | ⬜      | Validate Session ID                          | Validate session IDs to prevent injection attacks. Validate session ID format and length, reject invalid characters and traversal strings (such as '../'), and ensure only properly formatted session IDs are accepted. |
| 32  | P2       | ⬜      | Security Regression Tests                    | Create security regression tests to ensure security fixes remain intact. Implement tests for upload attacks, path traversal, SSRF prevention, secret masking, and platform authentication to verify security measures continue to work. |

### DevOps & CI/CD

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 40  | P2       | ⬜      | Configure Dependabot                         | Configure Dependabot for automated dependency updates. Set up Dependabot to monitor Python dependencies, Docker images, and GitHub Actions for updates on a weekly schedule. |
| 41  | P2       | ⬜      | Graceful Shutdown                            | Implement graceful shutdown for the application server. Handle SIGTERM and SIGINT signals properly, close the database connection pool, and cleanly shut down all tools and resources to prevent data loss. |
| 42  | P2       | ⬜      | Add UI Test Stage                            | Add a UI test stage to the CI pipeline. Run npm ci to install frontend dependencies, execute npm test for unit/integration tests, upload test results as artifacts, and fail the CI build if any tests fail. |
| 43  | P2       | ⬜      | Improve Logging                              | Improve logging across the application. Implement structured logging, make log levels configurable, add request IDs for tracing, and add correlation IDs to track requests across services. |
| 44  | P2       | ⬜      | Improve Monitoring                           | Improve monitoring capabilities. Add a metrics endpoint, expose Prometheus metrics, create a Grafana dashboard, and define alert rules for system health monitoring. |

### Testing & Quality Assurance

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 52  | P2       | ⬜      | Create Shared Pytest Fixtures                | Tập trung toàn bộ fixture dùng chung vào `conftest.py`. |
| 53  | P2       | ⬜      | Convert Benchmark To Dataset                 | Không hardcode benchmark trong Python. |
| 56  | P2       | ⬜      | Serialization Tests                          | Create serialization tests for the safe data serializer. Test with nested dictionaries, nested lists, custom objects, large payloads, and circular references to ensure robust serialization. |
| 57  | P2       | ⬜      | Upload Validation Tests                      | Create upload validation tests for file upload functionality. Test with invalid file extensions, oversized files, path traversal attempts, empty files, and duplicate filenames. |
| 58  | P2       | ⬜      | Internet Tool Tests                          | Create tests for the Internet Tool covering network failure scenarios. Test invalid URLs, timeouts, DNS failures, retry logic, and blocked address handling. |
| 59  | P2       | ⬜      | Knowledge Tool Tests                         | Create tests for the Knowledge Tool covering capability management. Test capability lookup, evidence mapping, missing capability handling, duplicate capability detection, and invalid request handling. |
| 60  | P2       | ⬜      | Capability Library Tests                     | Create tests for the Capability Library covering registry operations. Test registry validation, duplicate detection, unknown capability handling, serialization, and loading from storage. |
| 62  | P2       | ⬜      | Performance Benchmarks                       | Create performance benchmarks for key system operations. Benchmark agent startup time, query latency, tool execution latency, memory usage, and CPU usage to track performance over time. |
| 63  | P2       | ⬜      | Memory Leak Tests                            | Create memory leak tests to detect resource leaks. Test long conversation sessions, repeated execution cycles, tool lifecycle management, and cache lifecycle to ensure no memory leaks occur. |
| 64  | P2       | ⬜      | Load Tests                                   | Create load tests to verify system behavior under concurrent usage. Test with 10 concurrent users, 50 concurrent users, 100 requests in quick succession, and long-running sessions. |
| 65  | P2       | ⬜      | Test Coverage Improvement                    | Improve overall test coverage across the codebase. Set target coverage goals, ensure no new modules lack tests, integrate coverage reporting in CI, and track coverage by module. |

### Documentation & Project Governance

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 74  | P2       | ⬜      | Expand CONTRIBUTING.md                       | Expand CONTRIBUTING.md with detailed contribution guidelines. Document branch strategy, commit message conventions, pull request workflow, code review checklist, and development workflow. |
| 75  | P2       | ⬜      | Improve SECURITY.md                          | Improve SECURITY.md with comprehensive security policies. Document the security reporting process, responsible disclosure policy, contact information for security issues, and security response SLA. |
| 76  | P2       | ⬜      | Create Security Issue Template               | Create issue templates for better issue tracking. Add templates for security issues, vulnerability reports, bug reports, and feature requests to standardize submissions. |
| 77  | P2       | ⬜      | Add Last Updated Metadata                    | Add 'Last Updated' metadata to all key documentation files. Update the Vision document, Roadmap, Project State, Architecture documentation, and Development Rules with last-updated timestamps. |
| 78  | P2       | ⬜      | Consolidate Benchmark Reports                | Consolidate benchmark reports into a single structured format. Merge multiple benchmark reports, keep only the latest results, create a summary view, and archive old benchmark data. |
| 79  | P2       | ⬜      | Standardize Documentation Structure          | Standardize documentation structure across all project docs. Normalize heading levels, numbering schemes, table formats, and terminology usage for consistency. |
| 80  | P2       | ⬜      | Improve Project Bootstrap Guide              | Improve the project bootstrap guide to help new developers get started quickly. Document local setup steps, Python environment setup, Docker setup instructions, and common troubleshooting solutions. |
| 81  | P2       | ⬜      | Update Development Rules                     | Update development rules documentation. Document coding conventions, code review checklists, testing requirements, and documentation standards for all contributors. |
| 82  | P2       | ⬜      | Update Project State                         | Update the project state document to reflect current implementation status. Synchronize the implementation status with actual progress, update the roadmap, list completed work, and document known issues. |

### Code Quality, Refactoring & Technical Debt

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 91  | P2       | ⬜      | Remove Hardcoded Configuration               | Remove hardcoded configuration values and move them to a config file. Extract hardcoded timeouts, retry counts, ports, file paths, cache sizes, and thresholds into the configuration system. |
| 92  | P2       | ⬜      | Standardize Configuration System             | Standardize the configuration system across the project. Audit all current configuration locations, consolidate into a single configuration source, eliminate duplicate config entries, and document all configuration options. |
| 93  | P2       | ⬜      | Improve Logging Consistency                  | Improve logging consistency across the codebase. Standardize logger initialization, normalize log level usage, unify message format, and ensure structured logging is used consistently. |
| 94  | P2       | ⬜      | Improve Error Handling Strategy              | Improve the error handling strategy across the project. Standardize the exception hierarchy, normalize error codes, create consistent API error responses, and unify internal error handling patterns. |
| 95  | P2       | ⬜      | Improve Runtime Performance                  | Improve runtime performance by profiling and optimizing bottlenecks. Profile the execution runtime to identify slow spots, eliminate bottlenecks, add appropriate caching, and re-benchmark to verify improvements. |
| 96  | P2       | ⬜      | Refactor Capability Resolution Flow          | Refactor the capability resolution flow to simplify logic. Review the capability resolution pipeline, simplify the logic flow, remove duplicate lookups, and improve overall maintainability. |
| 97  | P2       | ⬜      | Standardize Response Models                  | Standardize response models across all API endpoints. Normalize response schemas, serialization patterns, validation logic, and typing to ensure consistent API responses. |
| 98  | P2       | ⬜      | Improve Type Hints                           | Improve type hints across the codebase. Add missing type annotations, use TypedDict for dictionary types, use Protocol for structural typing, use Generic for generic types, and ensure all functions have return type annotations. |
| 99  | P2       | ⬜      | Remove Legacy Compatibility Code             | Remove legacy compatibility code that is no longer needed. Find and remove compatibility layers for deprecated APIs, clean up unused imports, and remove obsolete helper functions. |
| 100 | P2       | ⬜      | Standardize Project Structure                | Standardize the project structure for better organization. Review the folder structure, move modules to appropriate locations if needed, synchronize package organization, and remove unnecessary modules. |

---

## Phase 3 — Polish & Governance (P3)

### Core Architecture

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 13  | P3       | ⬜      | Standardize Naming Convention                | Standardize naming conventions across the entire project for consistency. Normalize methods using `_get_*`, `_read_*`, and `_load_*` prefixes, ensure naming patterns are consistent across all modules, and update all references to match the standardized naming. |

### Security

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 30  | P3       | ⬜      | Make Secret Path Configurable                | Make the secrets path configurable via environment variable. Add an ORION_SECRETS_PATH configuration option, support custom secret file locations, and document the configuration so users can place secrets outside the repository. |
| 31  | P3       | ⬜      | Improve Database Connection Security         | Improve database connection security by implementing connection pooling, adding SSL support for remote database connections, making SSL mode configurable, and updating documentation to reflect the security options. |

### DevOps & CI/CD

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 45  | P3       | ⬜      | Resource Limits (Platform)                   | Set resource limits for platform deployment containers. Configure CPU limits, memory limits, and container reservations, and document the resource requirements. |
| 46  | P3       | ⬜      | Deployment Pipeline (Platform)               | Create a deployment pipeline for the platform. Build release images, push to container registry, deploy to the server, verify deployment success, and implement a rollback strategy. |
| 47  | P3       | ⬜      | Release Automation                           | Automate the release process. Tag releases with version numbers, generate changelogs, publish build artifacts, and create release notes for each release. |
| 48  | P3       | ⬜      | CI Performance Optimization                  | Optimize CI pipeline performance. Cache pip and npm dependencies across runs, parallelize CI jobs where possible, and reduce overall workflow execution time. |
| 49  | P3       | ⬜      | Standardize Development Environment          | Standardize the development environment setup. Update the bootstrap script, verify virtual environment creation works correctly, ensure dependency installation succeeds, and verify the local startup process. |
| 50  | P3       | ⬜      | DevOps Documentation                         | Create comprehensive DevOps documentation covering the CI pipeline, Docker workflow, local development setup, and release workflow to help developers understand the infrastructure. |

### Testing & Quality Assurance

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 61  | P3       | ⬜      | Improve Benchmark Reports                    | Improve benchmark reports to provide better visibility. Aggregate benchmark results, display scores, show pass rates, and show execution times in an easy-to-read format. |
| 66  | P3       | ⬜      | Remove Duplicate Tests                       | Remove duplicate tests to reduce test maintenance burden. Find test cases that overlap, merge duplicate tests, standardize test naming conventions, and reorganize test folder structure. |
| 67  | P3       | ⬜      | Improve Test Documentation                   | Improve test documentation to help developers write better tests. Create guidelines for writing tests, mocking dependencies, running benchmarks, and maintaining regression tests. |
| 68  | P3       | ⬜      | Continuous Quality Monitoring                | Implement continuous quality monitoring. Track benchmark results over time, monitor test coverage trends, track performance metrics, and watch for regressions across releases. |

### Documentation & Project Governance

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 83  | P3       | ⬜      | Improve Tool Documentation                   | Improve documentation for all tools in the system. Create or update docs for the Linux Tool, Zabbix Tool, Grafana Tool, Internet Tool, and Knowledge Tool with usage examples and configuration details. |
| 84  | P3       | ⬜      | Improve API Documentation                    | Improve API documentation for all endpoints. Add endpoint descriptions, request examples with curl commands, response examples, and error code documentation for better developer experience. |
| 85  | P3       | ⬜      | Improve Architecture Diagrams                | Improve architecture diagrams to visualize the system design. Create pipeline diagrams, runtime execution flow diagrams, tool interaction diagrams, component architecture diagrams, and sequence diagrams for key workflows. |
| 86  | P3       | ⬜      | Documentation Consistency Review             | Perform a comprehensive documentation consistency review. Check terminology usage across all docs, find and remove duplicate content, fix broken links, identify outdated documentation, and synchronize all documentation. |

### Code Quality, Refactoring & Technical Debt

| ID  | Priority | Status | Title | Description |
|-----|----------|--------|-------|-------------|
| 101 | P3       | ⬜      | Review Technical Debt                        | Review and catalog technical debt across the codebase. Search for TODO, FIXME, and XXX comments, categorize each item, and create a plan to address them systematically. |
| 102 | P3       | ⬜      | Remove Duplicate Utility Functions           | Remove duplicate utility functions across the project. Identify functions that serve the same purpose, consolidate them into a common module, refactor all call sites to use the shared implementation, and delete the old code. |
| 103 | P3       | ⬜      | Standardize Project Coding Style             | Standardize the project's coding style across all files. Normalize naming conventions, import ordering, code formatting, docstring style, and comment conventions to ensure consistent code style. |
| 104 | P3       | ⬜      | Final Architecture Cleanup                   | Thực hiện đợt cleanup cuối sau khi toàn bộ backlog đã hoàn thành. |

---

## Summary

| Phase | Epic | Total | ✅ Done | 🔄 In Progress | ⬜ Pending | 🔴 Blocked |
|-------|------|-------|--------|----------------|---------|----------|
| 0     | Code Quality                                 | 1     | 1      | 0            | 0       | 0        |
| 1     | Core Architecture                            | 7     | 3      | 4            | 0       | 0        |
| 1     | Security                                     | 4     | 1      | 3            | 0       | 0        |
| 1     | DevOps & CI/CD                               | 7     | 6      | 1            | 0       | 0        |
| 1     | Testing & Quality Assurance                  | 3     | 2      | 0            | 1       | 0        |
| 1     | Documentation & Project Governance           | 5     | 0      | 2            | 3       | 0        |
| 1     | Code Quality, Refactoring & Technical Debt   | 4     | 0      | 0            | 4       | 0        |
| 2     | Core Architecture                            | 7     | 0      | 0            | 7       | 0        |
| 2     | Security                                     | 11    | 0      | 0            | 11      | 0        |
| 2     | DevOps & CI/CD                               | 5     | 0      | 0            | 5       | 0        |
| 2     | Testing & Quality Assurance                  | 11    | 0      | 0            | 11      | 0        |
| 2     | Documentation & Project Governance           | 9     | 0      | 0            | 9       | 0        |
| 2     | Code Quality, Refactoring & Technical Debt   | 10    | 0      | 0            | 10      | 0        |
| 3     | Core Architecture                            | 1     | 0      | 0            | 1       | 0        |
| 3     | Security                                     | 2     | 0      | 0            | 2       | 0        |
| 3     | DevOps & CI/CD                               | 6     | 0      | 0            | 6       | 0        |
| 3     | Testing & Quality Assurance                  | 4     | 0      | 0            | 4       | 0        |
| 3     | Documentation & Project Governance           | 4     | 0      | 0            | 4       | 0        |
| 3     | Code Quality, Refactoring & Technical Debt   | 4     | 0      | 0            | 4       | 0        |
|       | **Total**                                     | **105** | **13** | **10** | **82** | **0** |

---

*Source: `.workflow/state.json` — this file is auto-generated for human readability.*
