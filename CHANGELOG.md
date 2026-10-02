# Changelog

## 0.1.3

- Paired Windows/Linux model-free worker, isolated browser automation and authenticated Remote Desktop.
- Lightweight worker artifacts with native Linux/Windows CI and release smoke coverage.
- Zero-install portable Windows/Linux binaries, temporary in-memory credentials and explicit remembered mode.
- Remote Control downloads with exact-build checksums and endpoint-bound Device Chat on the canonical runtime.

## Unreleased — Local-first Chat + Project architecture

MCP v1 client/host integration:

- added explicit local stdio/Streamable HTTP server configuration and tool allowlists;
- registered namespaced MCP tools in the existing canonical runtime with local operation policy;
- retained conversation confirmation, server ceilings and scheduler forced-read-only behavior;
- added bounded results, secret redaction, protected inspection and owned async SDK cleanup;
- added deterministic official-SDK tests on Linux and native Windows.

Architecture and implementation alignment:

- redefined Orion as a local-first AI technical workbench;
- made Chat the base runtime;
- defined Project as Chat plus project-scoped knowledge/RAG;
- removed manual tool selection from Chat and Project;
- made every registered/configured ordinary tool discoverable to the model through the canonical registry;
- accepted direct registry-derived tool schemas on the first model turn in ADR 0007;
- kept semantic tool choice model-driven instead of Orion pre-routing;
- kept canonical registry validation, `ToolRunner`, `RuntimeScope`, and execution permissions independent of request-local schema exposure;
- removed product-level quota/rate-limit layers from the core tool architecture while retaining bounded failure/watchdog safety mechanisms;
- documented current Knowledge/RAG, calculator, Internet, Linux, Grafana, and Zabbix tool families;
- documented installation, model, RAG, testing, and troubleshooting flows;
- removed `.clinerules` from the documentation package.
